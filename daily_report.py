"""
市場日報與商品出場提醒
- generate_market_report(): 純市場資訊（指數、VIX、板塊）
- generate_settlement_alert(): 商品異動提醒，沒事返回空字串
"""
import json
from datetime import date, datetime, timedelta

import yfinance as yf


# ════════════════════════════════════════════════════════════════
# 訊息 A：市場日報（純市場資訊）
# ════════════════════════════════════════════════════════════════
def generate_market_report(app=None, username='admin'):
    """產生市場日報文字（純市場，不含商品資訊）。
    app, username 參數保留是為了相容現有呼叫端，實際未使用。
    """
    today = date.today()
    sections = []

    sections.append(f'市場日報 {today.strftime("%Y/%m/%d")}')
    sections.append('=' * 20)

    # ── 三大指數 ──
    try:
        indices_data = _fetch_indices()
        if indices_data:
            sections.append('\n美股三大指數')
            for name, info in indices_data.items():
                arrow = '▲' if info['chg'] >= 0 else '▼'
                sections.append(f'{name}: {info["price"]:,.2f} {arrow}{abs(info["chg"]):.2f}%')
    except Exception:
        sections.append('\n指數資料取得失敗')

    # ── VIX 恐慌指數 ──
    try:
        vix = _fetch_vix()
        if vix:
            level = '低' if vix['price'] < 15 else '中' if vix['price'] < 25 else '高' if vix['price'] < 35 else '極高'
            sections.append(f'\nVIX 恐慌指數: {vix["price"]:.2f} ({level})')
    except Exception:
        pass

    # ── 板塊表現 ──
    try:
        sectors = _fetch_sectors()
        if sectors:
            sections.append('\n板塊表現')
            for name, chg in sectors:
                arrow = '▲' if chg >= 0 else '▼'
                sections.append(f'{name}: {arrow}{abs(chg):.2f}%')
    except Exception:
        pass

    return '\n'.join(sections)


# ════════════════════════════════════════════════════════════════
# 訊息 B：商品出場提醒（事件驅動，沒事返回空字串）
# ════════════════════════════════════════════════════════════════
def generate_settlement_alert(app, username='admin'):
    """產生商品出場/異動提醒，僅限指定帳號。沒事返回空字串。"""
    if not app:
        return ''

    last_td = _get_last_us_trading_day()

    sections = []
    sections.append(f'商品異動提醒 {date.today().strftime("%Y/%m/%d")}')
    sections.append('=' * 20)
    sections.append(f'（依 {last_td.strftime("%Y/%m/%d")} 美股收盤判定）')

    has_content = False

    with app.app_context():
        from models import Product, Underlying, AppUser
        user = AppUser.query.filter_by(username=username).first()
        if not user:
            return ''
        active = Product.query.filter_by(status='active', user_id=user.id).all()

        # ── 昨日達 KO ──
        ko_lines = _section_yesterday_ko(active, last_td)
        if ko_lines:
            has_content = True
            sections.append('\n【昨日達 KO】')
            sections.extend(ko_lines)

        # ── 昨日到期 ──
        mature_lines = _section_yesterday_matured(active, last_td)
        if mature_lines:
            has_content = True
            sections.append('\n【昨日到期】')
            sections.extend(mature_lines)

        # ── 接近 KO（≤3%，僅列「現在會比 KO」的商品）──
        near_lines = _section_near_ko(active)
        if near_lines:
            has_content = True
            sections.append('\n【接近 KO】')
            sections.extend(near_lines)

        # ── 即將到期 14 天內 ──
        expiring_lines = _section_expiring_soon(active)
        if expiring_lines:
            has_content = True
            sections.append('\n【即將到期】')
            sections.extend(expiring_lines)

        # ── 已逾期未結算 ──
        overdue_lines = _section_overdue(active)
        if overdue_lines:
            has_content = True
            sections.append('\n【未確認結算】')
            sections.extend(overdue_lines)

    return '\n'.join(sections) if has_content else ''


# ════════════════════════════════════════════════════════════════
# 市場資料抓取
# ════════════════════════════════════════════════════════════════
def _fetch_indices():
    tickers = {'^GSPC': 'S&P 500', '^IXIC': 'NASDAQ', '^DJI': '道瓊'}
    data = yf.download(list(tickers.keys()), period='5d', progress=False)
    if data.empty:
        return None

    close = data['Close']
    today = date.today()
    prev_close = close[close.index.date < today]
    if len(prev_close) < 2:
        prev_close = close
    if len(prev_close) < 2:
        return None

    last = prev_close.iloc[-1]
    prev = prev_close.iloc[-2]

    result = {}
    for ticker, name in tickers.items():
        try:
            price = float(last[ticker])
            chg = float((last[ticker] / prev[ticker] - 1) * 100)
            result[name] = {'price': price, 'chg': chg}
        except Exception:
            pass
    return result


def _fetch_vix():
    data = yf.download('^VIX', period='2d', progress=False)
    if data.empty:
        return None
    close = data['Close'].squeeze()
    return {'price': float(close.iloc[-1])}


def _fetch_sectors():
    sector_etfs = {
        'XLK': '科技', 'XLF': '金融', 'XLE': '能源',
        'XLV': '醫療', 'XLY': '消費', 'XLI': '工業', 'SOXX': '半導體',
    }
    tickers = list(sector_etfs.keys())
    data = yf.download(tickers, period='5d', progress=False)
    if data.empty:
        return None

    close = data['Close']
    today = date.today()
    prev_close = close[close.index.date < today]
    if len(prev_close) < 2:
        prev_close = close
    if len(prev_close) < 2:
        return None

    last = prev_close.iloc[-1]
    prev = prev_close.iloc[-2]

    results = []
    for ticker, name in sector_etfs.items():
        try:
            chg = float((last[ticker] / prev[ticker] - 1) * 100)
            results.append((name, chg))
        except Exception:
            pass
    results.sort(key=lambda x: x[1], reverse=True)
    return results


def _get_last_us_trading_day():
    """取得最近一個美股交易日（以 S&P 500 收盤資料為準）"""
    try:
        data = yf.download('^GSPC', period='5d', progress=False)
        if not data.empty:
            return data.index[-1].date()
    except Exception:
        pass
    return date.today() - timedelta(days=1)


# ════════════════════════════════════════════════════════════════
# 商品異動分區
# ════════════════════════════════════════════════════════════════
def _section_yesterday_ko(active_products, last_td):
    """昨日新達 KO 的標的（ko_hit_date == 最近交易日）"""
    lines = []
    for p in active_products:
        code = p.product_code or '?'
        for u in sorted(p.underlyings, key=lambda x: x.position_order or 0):
            if u.ko_hit_date == last_td and u.ko_hit:
                price_str = f'{u.latest_price:.2f}' if u.latest_price else '-'
                ko_str = f'{u.ko_level:.2f}' if u.ko_level else '-'
                lines.append(f'  [{code}] {u.ticker} 達 KO（{price_str} ≥ {ko_str}）')
    return lines


def _section_yesterday_matured(active_products, last_td):
    """昨日到期的商品（maturity_date == 最近交易日）"""
    lines = []
    for p in active_products:
        if p.maturity_date == last_td:
            code = p.product_code or '?'
            lines.append(f'  [{code}] 已到期，請確認結算')
    return lines


def _section_near_ko(active_products):
    """接近 KO（距離 ≤3% 且尚未鎖定）。僅列「現在會比 KO」的商品。"""
    lines = []
    for p in active_products:
        if not _is_ko_relevant_today(p):
            continue
        code = p.product_code or '?'
        for u in sorted(p.underlyings, key=lambda x: x.position_order or 0):
            if not u.latest_price or not u.ko_level:
                continue
            if u.ko_hit:
                continue
            ko_dist = (u.latest_price / u.ko_level - 1)
            if -0.03 <= ko_dist < 0:
                lines.append(f'  [{code}] {u.ticker} 距離 KO 僅 {ko_dist:.1%}')
    return lines


def _is_ko_relevant_today(p):
    """此商品今天是否會比 KO（fixed/stepdown 各自判定）。"""
    if p.ko_type == 'stepdown':
        return _stepdown_obs_within(p, days=7)
    # fixed FCN：start_date 之後每天比 KO
    return bool(p.is_ko_observing)


def _stepdown_obs_within(p, days=7):
    """stepdown FCN 的下一個 observation_date 是否在 days 天內。"""
    if not p.observation_dates:
        return False
    try:
        obs_list = json.loads(p.observation_dates)
    except Exception:
        return False
    today = date.today()
    threshold = today + timedelta(days=days)
    for s in obs_list:
        try:
            d = datetime.strptime(s, '%Y-%m-%d').date()
        except Exception:
            continue
        if d >= today:
            return d <= threshold
    return False


def _section_expiring_soon(active_products):
    """即將到期 1-14 天"""
    lines = []
    for p in active_products:
        if p.maturity_date and p.days_to_maturity is not None:
            if 1 <= p.days_to_maturity <= 14:
                code = p.product_code or '?'
                lines.append(f'  [{code}] 將於 {p.days_to_maturity} 天後到期 ({p.maturity_date.strftime("%m/%d")})')
    return lines


def _section_overdue(active_products):
    """已逾期未結算"""
    lines = []
    for p in active_products:
        if p.maturity_date and p.days_to_maturity is not None and p.days_to_maturity < 0:
            code = p.product_code or '?'
            lines.append(f'  [{code}] 已過到期日 {abs(p.days_to_maturity)} 天，請確認是否結算')
    return lines
