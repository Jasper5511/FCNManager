"""
LINE Bot 整合模組
- 推播訊息給已訂閱用戶
- Webhook 接收用戶訊息
"""
import os
import json
from linebot.v3 import WebhookHandler
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi,
    PushMessageRequest, BroadcastRequest,
    TextMessage, FlexMessage, FlexContainer,
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent, FollowEvent, UnfollowEvent


# ── 設定 ─────────────────────────────────────────────────────────────────────
_config = None
_api = None
_handler = None


def init_line(app):
    """初始化 LINE Bot（在 Flask app 啟動時呼叫）"""
    global _config, _api, _handler

    secret = app.config.get('LINE_CHANNEL_SECRET') or os.environ.get('LINE_CHANNEL_SECRET', '')
    token = app.config.get('LINE_CHANNEL_ACCESS_TOKEN') or os.environ.get('LINE_CHANNEL_ACCESS_TOKEN', '')

    if not secret or not token:
        app.logger.warning('LINE Bot 未設定 (缺少 CHANNEL_SECRET 或 ACCESS_TOKEN)')
        return None

    _config = Configuration(access_token=token)
    _handler = WebhookHandler(secret)

    # 註冊事件處理器
    @_handler.add(FollowEvent)
    def handle_follow(event):
        """用戶加好友時，儲存 user_id"""
        user_id = event.source.user_id
        _save_subscriber(user_id, app)
        with ApiClient(_config) as client:
            api = MessagingApi(client)
            api.push_message(PushMessageRequest(
                to=user_id,
                messages=[TextMessage(text='歡迎訂閱市場日報！每個交易日早上會自動發送美股市場摘要。')]
            ))

    @_handler.add(UnfollowEvent)
    def handle_unfollow(event):
        """用戶封鎖時，移除訂閱"""
        _remove_subscriber(event.source.user_id, app)

    @_handler.add(MessageEvent, message=TextMessageContent)
    def handle_message(event):
        """回覆用戶訊息"""
        text = event.message.text.strip()
        reply = None

        if text in ('日報', '市場', '快報'):
            from daily_report import generate_market_report
            report = generate_market_report(app)
            reply = report
        elif text in ('異動', '出場', '提醒'):
            from daily_report import generate_settlement_alert
            alert = generate_settlement_alert(app)
            reply = alert if alert else '今日無商品異動'
        elif text in ('持倉', '部位'):
            reply = _get_position_summary(app, event.source.user_id)
        elif text == '幫助':
            reply = '可用指令：\n- 日報：市場資訊\n- 異動：商品出場/接近KO/到期提醒\n- 持倉：持倉摘要\n- 幫助：顯示此說明'
        else:
            reply = f'輸入「幫助」查看可用指令'

        with ApiClient(_config) as client:
            api = MessagingApi(client)
            from linebot.v3.messaging import ReplyMessageRequest
            api.reply_message(ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=reply)]
            ))

    return _handler


def get_handler():
    return _handler


def get_config():
    return _config


def is_configured():
    return _config is not None and _handler is not None


# ── 推播 ─────────────────────────────────────────────────────────────────────
def push_text(user_id, text):
    """推播文字訊息給指定用戶"""
    if not _config:
        return False
    try:
        with ApiClient(_config) as client:
            api = MessagingApi(client)
            api.push_message(PushMessageRequest(
                to=user_id,
                messages=[TextMessage(text=text)]
            ))
        return True
    except Exception as e:
        print(f'LINE 推播失敗: {e}')
        return False


def broadcast_text(text):
    """廣播文字訊息給所有好友"""
    if not _config:
        return False
    try:
        with ApiClient(_config) as client:
            api = MessagingApi(client)
            api.broadcast(BroadcastRequest(
                messages=[TextMessage(text=text)]
            ))
        return True
    except Exception as e:
        print(f'LINE 廣播失敗: {e}')
        return False


def push_to_all_subscribers(text, app):
    """推播給所有已訂閱用戶"""
    subscribers = _load_subscribers(app)
    success = 0
    for uid in subscribers:
        if push_text(uid, text):
            success += 1
    return success


# ── 訂閱者管理（JSON 檔案儲存）────────────────────────────────────────────────
def _subscribers_path(app):
    return os.path.join(app.instance_path, 'line_subscribers.json')


def _load_subscribers(app):
    path = _subscribers_path(app)
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []


def _save_subscriber(user_id, app):
    subscribers = _load_subscribers(app)
    if user_id not in subscribers:
        subscribers.append(user_id)
        os.makedirs(app.instance_path, exist_ok=True)
        with open(_subscribers_path(app), 'w', encoding='utf-8') as f:
            json.dump(subscribers, f)


def _remove_subscriber(user_id, app):
    subscribers = _load_subscribers(app)
    if user_id in subscribers:
        subscribers.remove(user_id)
        with open(_subscribers_path(app), 'w', encoding='utf-8') as f:
            json.dump(subscribers, f)


def get_subscriber_count(app):
    return len(_load_subscribers(app))


def get_real_follower_count(app):
    """從 LINE 平台抓真實好友數（呼叫 get_followers_ids 分頁累計）。
    抓失敗回傳 None，呼叫端可 fallback 到 get_subscriber_count。
    """
    if not _config:
        return None
    try:
        with ApiClient(_config) as client:
            api = MessagingApi(client)
            count = 0
            start = None
            while True:
                resp = api.get_followers_ids(start=start) if start \
                    else api.get_followers_ids()
                count += len(getattr(resp, 'user_ids', None) or [])
                start = getattr(resp, 'next', None)
                if not start:
                    break
            return count
    except Exception as e:
        try:
            app.logger.error(f'取得 LINE 好友數失敗: {e}')
        except Exception:
            pass
        return None


# ── 持倉摘要 ─────────────────────────────────────────────────────────────────
def _get_position_summary(app, line_user_id):
    """產生簡短的持倉文字摘要"""
    with app.app_context():
        from models import Product, Underlying
        # 取第一個用戶的 active 商品（單人使用）
        active = Product.query.filter_by(status='active').all()
        if not active:
            return '目前沒有進行中的商品。'

        lines = [f'持倉摘要（{len(active)} 檔商品）\n']
        for p in active:
            worst = None
            for u in p.underlyings:
                if u.latest_price and u.ko_level:
                    dist = (u.latest_price / u.ko_level - 1)
                    if worst is None or dist < worst:
                        worst = dist
            status = ''
            if worst is not None:
                if worst >= 0:
                    status = f' [距KO {worst:+.1%}]'
                else:
                    status = f' [距KO {worst:.1%}]'
            tickers = '/'.join(u.ticker for u in sorted(p.underlyings, key=lambda x: x.position_order or 0))
            lines.append(f'{p.product_code} {tickers}{status}')

        return '\n'.join(lines)
