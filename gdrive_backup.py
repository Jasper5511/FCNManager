"""
Google Drive 自動備份模組
- 每日更新收盤價後自動備份資料庫到 Google Drive FCN_Backup 資料夾
- 保留最近 30 天，超過自動刪除
- 使用 OAuth2 用戶憑證（非服務帳戶）
"""

import os
import json
import tempfile
from datetime import datetime, date, timedelta

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ['https://www.googleapis.com/auth/drive']
BACKUP_FOLDER_NAME = 'FCN_Backup'
KEEP_DAYS = 30

BASE_DIR = os.path.dirname(__file__)
OAUTH_CREDS_FILE = os.path.join(BASE_DIR, 'oauth_credentials.json')
TOKEN_FILE = os.path.join(BASE_DIR, 'gdrive_token.json')


def _get_credentials():
    """取得 OAuth2 憑證，自動刷新 token"""
    creds = None

    # 嘗試從環境變數載入 token（Render 雲端用）
    token_json = os.environ.get('GOOGLE_DRIVE_TOKEN')
    if token_json:
        info = json.loads(token_json)
        creds = Credentials.from_authorized_user_info(info, SCOPES)

    # 嘗試從本地檔案載入 token
    if not creds and os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    # 如果 token 過期，嘗試刷新
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        # 更新本地 token 檔
        with open(TOKEN_FILE, 'w') as f:
            f.write(creds.to_json())

    # 如果沒有有效 token，執行首次授權流程（僅本機需要）
    if not creds or not creds.valid:
        if not os.path.exists(OAUTH_CREDS_FILE):
            raise FileNotFoundError('找不到 OAuth 憑證檔 oauth_credentials.json')
        flow = InstalledAppFlow.from_client_secrets_file(OAUTH_CREDS_FILE, SCOPES)
        creds = flow.run_local_server(port=0)
        # 儲存 token 供下次使用
        with open(TOKEN_FILE, 'w') as f:
            f.write(creds.to_json())

    return creds


def _find_folder(service):
    """找到 FCN_Backup 資料夾的 ID"""
    q = f"name='{BACKUP_FOLDER_NAME}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    results = service.files().list(q=q, spaces='drive', fields='files(id, name)').execute()
    files = results.get('files', [])
    if files:
        return files[0]['id']
    return None


def _export_db_to_json(app):
    """匯出所有資料表為 JSON"""
    from models import db, AppUser, Client, Product, Underlying, Position, PriceHistory, ActivityLog

    data = {'backup_time': datetime.now().isoformat(), 'tables': {}}

    with app.app_context():
        # AppUser
        data['tables']['app_users'] = [
            {'id': u.id, 'username': u.username, 'password': u.password,
             'role': u.role, 'created_at': u.created_at.isoformat() if u.created_at else None}
            for u in AppUser.query.all()
        ]

        # Client
        data['tables']['clients'] = [
            {'id': c.id, 'user_id': c.user_id, 'name': c.name,
             'name_masked': c.name_masked, 'created_at': c.created_at.isoformat() if c.created_at else None}
            for c in Client.query.all()
        ]

        # Product
        data['tables']['products'] = [
            {'id': p.id, 'user_id': p.user_id, 'product_code': p.product_code,
             'issuer': p.issuer, 'product_type': p.product_type, 'tenor_months': p.tenor_months,
             'currency': p.currency, 'coupon_rate': p.coupon_rate,
             'trade_date': p.trade_date.isoformat() if p.trade_date else None,
             'start_date': p.start_date.isoformat() if p.start_date else None,
             'maturity_date': p.maturity_date.isoformat() if p.maturity_date else None,
             'ko_pct': p.ko_pct, 'strike_pct': p.strike_pct, 'eki_pct': p.eki_pct,
             'ko_type': p.ko_type, 'ko_lockout': p.ko_lockout,
             'special_notes': p.special_notes, 'status': p.status,
             'created_at': p.created_at.isoformat() if p.created_at else None}
            for p in Product.query.all()
        ]

        # Underlying
        data['tables']['underlyings'] = [
            {'id': u.id, 'product_id': u.product_id, 'ticker': u.ticker,
             'initial_price': u.initial_price, 'ko_level': u.ko_level,
             'strike_level': u.strike_level, 'eki_level': u.eki_level,
             'ko_hit': u.ko_hit, 'latest_price': u.latest_price,
             'price_date': u.price_date.isoformat() if u.price_date else None,
             'position_order': u.position_order}
            for u in Underlying.query.all()
        ]

        # Position
        data['tables']['positions'] = [
            {'id': p.id, 'client_id': p.client_id, 'product_id': p.product_id,
             'investment_amount': p.investment_amount, 'notes': p.notes,
             'created_at': p.created_at.isoformat() if p.created_at else None}
            for p in Position.query.all()
        ]

        # PriceHistory
        data['tables']['price_history'] = [
            {'id': h.id, 'underlying_id': h.underlying_id,
             'price_date': h.price_date.isoformat() if h.price_date else None,
             'closing_price': h.closing_price, 'ko_triggered': h.ko_triggered}
            for h in PriceHistory.query.all()
        ]

        # ActivityLog
        data['tables']['activity_logs'] = [
            {'id': a.id, 'user_id': a.user_id, 'username': a.username,
             'action': a.action, 'ip': a.ip,
             'created_at': a.created_at.isoformat() if a.created_at else None}
            for a in ActivityLog.query.all()
        ]

    return data


def _cleanup_old_backups(service, folder_id):
    """刪除超過 30 天的備份檔"""
    cutoff = (datetime.now() - timedelta(days=KEEP_DAYS)).isoformat() + 'Z'
    q = (f"'{folder_id}' in parents and trashed=false "
         f"and createdTime < '{cutoff}' and name contains 'fcn_backup_'")
    results = service.files().list(q=q, spaces='drive', fields='files(id, name)').execute()
    for f in results.get('files', []):
        service.files().delete(fileId=f['id']).execute()
    return len(results.get('files', []))


def backup_to_drive(app):
    """主函式：匯出資料庫 → 上傳 Google Drive → 清理舊備份"""
    try:
        creds = _get_credentials()
        service = build('drive', 'v3', credentials=creds)

        folder_id = _find_folder(service)
        if not folder_id:
            app.logger.error('Google Drive 找不到 FCN_Backup 資料夾')
            return False

        # 匯出資料
        data = _export_db_to_json(app)
        today_str = date.today().strftime('%Y-%m-%d')
        filename = f'fcn_backup_{today_str}.json'

        # 寫入暫存檔
        tmp_path = os.path.join(tempfile.gettempdir(), filename)
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        # 上傳
        try:
            file_metadata = {'name': filename, 'parents': [folder_id]}
            media = MediaFileUpload(tmp_path, mimetype='application/json')
            service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass

        # 清理舊備份
        deleted = _cleanup_old_backups(service, folder_id)

        table_counts = {k: len(v) for k, v in data['tables'].items()}
        app.logger.info(f'備份完成: {filename}, 資料: {table_counts}, 刪除舊備份: {deleted} 個')
        return True

    except Exception as e:
        app.logger.error(f'Google Drive 備份失敗: {e}')
        return False
