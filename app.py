import sys, io, os
os.environ['PYTHONIOENCODING'] = 'utf-8'

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from functools import wraps
from models import db, Client, Product, Underlying, Position, PriceHistory, AppUser
from config import config
from datetime import date
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config.from_object(config[os.environ.get('FLASK_ENV', 'default')])
if hasattr(config[os.environ.get('FLASK_ENV', 'default')], 'init_app'):
    config[os.environ.get('FLASK_ENV', 'default')].init_app(app)
db.init_app(app)

with app.app_context():
    db.create_all()

# ── 初始化 LINE Bot ──────────────────────────────────────────────────────────
from line_bot import init_line, is_configured as line_is_configured
init_line(app)

# ── 排程：每日自動發送市場日報 ───────────────────────────────────────────────
def _setup_scheduler():
    """設定排程（避免 gunicorn 多 worker 重複啟動）"""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler

        def _scheduled_daily_report():
            from line_bot import broadcast_text, is_configured
            if not is_configured():
                return
            with app.app_context():
                from daily_report import generate_market_report
                report = generate_market_report(app)
                broadcast_text(report)
                app.logger.info('每日市場日報已自動發送')

        scheduler = BackgroundScheduler()
        scheduler.add_job(_scheduled_daily_report, 'cron', hour=7, minute=30,
                          timezone='Asia/Taipei', id='daily_report')
        scheduler.start()
        return scheduler
    except Exception as e:
        app.logger.warning(f'排程啟動失敗: {e}')
        return None

scheduler = _setup_scheduler()

# ── 初始化預設帳號 ────────────────────────────────────────────────────────────
with app.app_context():
    if not AppUser.query.first():
        u = AppUser(username='admin', role='admin')
        u.set_password('fcn2026')
        db.session.add(u)
        db.session.commit()


# ── 登入驗證 ─────────────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = AppUser.query.filter_by(username=request.form['username']).first()
        if user and user.check_password(request.form['password']):
            session['logged_in'] = True
            session['user_id'] = user.id
            session['is_admin'] = user.is_admin
            return redirect(url_for('dashboard'))
        flash('帳號或密碼錯誤', 'danger')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))


@app.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        user = AppUser.query.get(session['user_id'])
        old_pw = request.form['old_password']
        new_pw = request.form['new_password']
        confirm_pw = request.form['confirm_password']
        if not user.check_password(old_pw):
            flash('舊密碼錯誤', 'danger')
        elif new_pw != confirm_pw:
            flash('新密碼與確認密碼不一致', 'danger')
        elif len(new_pw) < 4:
            flash('密碼至少 4 個字元', 'danger')
        else:
            user.set_password(new_pw)
            db.session.commit()
            flash('密碼已更新', 'success')
            return redirect(url_for('dashboard'))
    return render_template('change_password.html')


TICKER_NAME = {
    'NVDA': '輝達', 'AVGO': '博通', 'TSM': '台積電', 'AMD': '超微',
    'MU': '美光', 'ARM': '安謀', 'QCOM': '高通', 'INTC': '英特爾',
    'AAPL': '蘋果', 'MSFT': '微軟', 'GOOG': '谷歌', 'AMZN': '亞馬遜',
    'META': '臉書', 'TSLA': '特斯拉', 'ORCL': '甲骨文', 'CRM': '賽富時',
    'NFLX': '網飛', 'UBER': '優步', 'UNH': '聯合健康', 'JPM': '摩根大通',
    'GS': '高盛', 'BA': '波音', 'AAL': '美國航空', 'AA': '美國鋁業',
    'NKE': '耐吉', 'COIN': '幣安所', 'SMCI': '超微電腦', 'ASML': '艾司摩爾',
    'VST': '美國電力', 'F': '福特', 'DIS': '迪士尼', 'PYPL': '貝寶',
    'CCL': '嘉年華', 'X': '美國鋼鐵', 'SOFI': '索飛', 'PLTR': '帕蘭提爾',
    'MSTR': '微策略',
}

@app.context_processor
def inject_globals():
    return {'TICKER_NAME': TICKER_NAME, 'is_admin': session.get('is_admin', False)}


def current_uid():
    return session.get('user_id')


# ── 使用者管理（僅管理員）─────────────────────────────────────────────────────
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('is_admin'):
            flash('需要管理員權限', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated


@app.route('/users')
@login_required
@admin_required
def users():
    all_users = AppUser.query.order_by(AppUser.created_at).all()
    return render_template('users.html', users=all_users)


@app.route('/users/add', methods=['POST'])
@login_required
@admin_required
def add_user():
    username = request.form['username'].strip()
    password = request.form['password'].strip()
    if not username or not password:
        flash('帳號和密碼不可空白', 'danger')
        return redirect(url_for('users'))
    if AppUser.query.filter_by(username=username).first():
        flash('此帳號已存在', 'warning')
        return redirect(url_for('users'))
    u = AppUser(username=username, role='user')
    u.set_password(password)
    db.session.add(u)
    db.session.commit()
    flash(f'已新增使用者：{username}', 'success')
    return redirect(url_for('users'))


@app.route('/users/<int:uid>/delete', methods=['POST'])
@login_required
@admin_required
def delete_user(uid):
    u = AppUser.query.get_or_404(uid)
    if u.is_admin:
        flash('無法刪除管理員帳號', 'danger')
    else:
        db.session.delete(u)
        db.session.commit()
        flash(f'已刪除使用者：{u.username}', 'success')
    return redirect(url_for('users'))


@app.route('/users/<int:uid>/reset', methods=['POST'])
@login_required
@admin_required
def reset_user_password(uid):
    u = AppUser.query.get_or_404(uid)
    new_pw = request.form['new_password'].strip()
    if not new_pw:
        flash('密碼不可空白', 'danger')
    else:
        u.set_password(new_pw)
        db.session.commit()
        flash(f'已重設 {u.username} 的密碼', 'success')
    return redirect(url_for('users'))


# ── 匯出 Excel ───────────────────────────────────────────────────────────────
@app.route('/export_excel')
@login_required
def export_excel():
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
    from io import BytesIO
    from flask import send_file

    wb = Workbook()
    thin = Border(
        left=Side(style='thin', color='B0B0B0'), right=Side(style='thin', color='B0B0B0'),
        top=Side(style='thin', color='B0B0B0'), bottom=Side(style='thin', color='B0B0B0'),
    )
    # 表頭：深橄欖綠 + 白字
    header_fill = PatternFill(start_color='4F6228', end_color='4F6228', fill_type='solid')
    header_font_white = Font(bold=True, color='FFFFFF', size=10)
    # 標的列 ticker 黃底
    yellow_fill = PatternFill(start_color='FFFF00', end_color='FFFF00', fill_type='solid')
    # KO 主資料行淺灰底
    info_fill = PatternFill(start_color='F2F2F2', end_color='F2F2F2', fill_type='solid')
    # 標籤欄底色（金橘色）
    label_fill = PatternFill(start_color='FFC000', end_color='FFC000', fill_type='solid')
    label_font = Font(bold=True, size=9, color='333333')
    # 交替底色
    alt_fill = PatternFill(start_color='DCE6F1', end_color='DCE6F1', fill_type='solid')  # 淺藍
    # 一般字型
    normal_font = Font(size=9)
    bold_font = Font(bold=True, size=9)
    pct_font = Font(size=9, color='C00000')
    pct_fmt = '0.00%'
    date_fmt = 'YYYY/M/D'

    col_widths = {'A':7, 'B':13.4, 'C':9.7, 'D':5.9, 'E':10, 'F':10.4,
                  'G':8.8, 'H':10.4, 'I':12.1, 'J':11.1, 'K':10.4,
                  'L':9.3, 'M':9.6, 'N':9.3, 'O':9.6, 'P':11.4,
                  'Q':13, 'R':13, 'S':10.6, 'T':12.3}

    def write_sheet(ws, products, is_ko_sheet=False):
        for col, w in col_widths.items():
            ws.column_dimensions[col].width = w

        # 表頭
        headers = ['END' if is_ko_sheet else '', '商品代碼', '類別', 'Tenor',
                   '交易營業員', '', '設定%', '(V/X)', 'Underlying 1',
                   '(V/X)', 'Underlying 2', '(V/X)', 'Underlying 3',
                   '(V/X)', 'Underlying 4', '訂價日', '比價日',
                   '期末訂價日', '年利率', '']
        for ci, h in enumerate(headers, 1):
            cell = ws.cell(row=1, column=ci, value=h)
            cell.font = header_font_white
            cell.fill = header_fill
            cell.border = thin
            cell.alignment = Alignment(horizontal='center')

        row = 2
        prod_idx = 0
        for p in products:
            uls = sorted(p.underlyings, key=lambda u: u.position_order or 0)
            clients = []
            for pos in p.positions:
                amt = ''
                if pos.investment_amount:
                    amt = str(int(pos.investment_amount / 10000)) + '萬'
                clients.append(pos.client.name_masked + amt)

            # 交替底色
            bg = alt_fill if prod_idx % 2 == 1 else None

            # 整個區塊先上底色
            if bg:
                for r in range(row, row + 5):
                    for col in range(1, 21):
                        ws.cell(row=r, column=col).fill = bg

            # ── Row 1: 標的 ──
            c = ws.cell(row=row, column=6, value='標的')
            c.border = thin; c.font = label_font; c.fill = label_fill
            for i, u in enumerate(uls[:4]):
                c = ws.cell(row=row, column=9 + i*2, value=u.ticker)
                c.border = thin; c.fill = yellow_fill; c.font = bold_font
            if len(clients) > 0:
                ws.cell(row=row, column=20, value=clients[0]).border = thin

            # ── Row 2: 期初價格 ──
            c = ws.cell(row=row+1, column=6, value='期初價格')
            c.border = thin; c.font = label_font; c.fill = label_fill
            for i, u in enumerate(uls[:4]):
                c = ws.cell(row=row+1, column=9 + i*2, value=u.initial_price)
                c.border = thin; c.font = normal_font
            if len(clients) > 1:
                ws.cell(row=row+1, column=20, value=clients[1]).border = thin

            # ── Row 3: KO（主資料行）──
            c = ws.cell(row=row+2, column=2, value=p.product_code)
            c.border = thin; c.font = bold_font
            c = ws.cell(row=row+2, column=3, value=p.product_type or 'FCN')
            c.border = thin; c.font = normal_font
            c = ws.cell(row=row+2, column=4, value=p.tenor_months)
            c.border = thin; c.font = normal_font
            c = ws.cell(row=row+2, column=6, value='KO')
            c.border = thin; c.font = label_font; c.fill = label_fill
            c = ws.cell(row=row+2, column=7, value=p.ko_pct)
            c.border = thin; c.number_format = pct_fmt; c.font = pct_font; c.fill = label_fill
            for i, u in enumerate(uls[:4]):
                c = ws.cell(row=row+2, column=8 + i*2, value='V' if u.ko_hit else '')
                c.border = thin; c.font = normal_font
                c = ws.cell(row=row+2, column=9 + i*2, value=u.ko_level)
                c.border = thin; c.font = normal_font
            if p.trade_date:
                c = ws.cell(row=row+2, column=16, value=p.trade_date)
                c.border = thin; c.number_format = date_fmt; c.font = normal_font
            if p.start_date:
                c = ws.cell(row=row+2, column=17, value=p.start_date)
                c.border = thin; c.number_format = date_fmt; c.font = normal_font
            if p.maturity_date:
                c = ws.cell(row=row+2, column=18, value=p.maturity_date)
                c.border = thin; c.number_format = date_fmt; c.font = normal_font
            if p.coupon_rate:
                c = ws.cell(row=row+2, column=19, value=p.coupon_rate)
                c.border = thin; c.number_format = pct_fmt; c.font = pct_font
            if len(clients) > 2:
                ws.cell(row=row+2, column=20, value=clients[2]).border = thin

            # ── Row 4: Strike ──
            c = ws.cell(row=row+3, column=6, value='Strike')
            c.border = thin; c.font = label_font; c.fill = label_fill
            c = ws.cell(row=row+3, column=7, value=p.strike_pct)
            c.border = thin; c.number_format = pct_fmt; c.font = pct_font; c.fill = label_fill
            for i, u in enumerate(uls[:4]):
                c = ws.cell(row=row+3, column=9 + i*2, value=u.strike_level)
                c.border = thin; c.font = normal_font
            if len(clients) > 3:
                ws.cell(row=row+3, column=20, value=clients[3]).border = thin

            # ── Row 5: EKI ──
            has_eki = p.eki_pct and p.eki_pct > 0
            c = ws.cell(row=row+4, column=6, value='EKI' if has_eki else '無EKI')
            c.border = thin; c.font = label_font; c.fill = label_fill
            c = ws.cell(row=row+4, column=7, value=p.eki_pct if has_eki else 0)
            c.border = thin; c.number_format = pct_fmt; c.font = pct_font; c.fill = label_fill
            for i, u in enumerate(uls[:4]):
                c = ws.cell(row=row+4, column=9 + i*2, value=u.eki_level if has_eki else 0)
                c.border = thin; c.font = normal_font

            row += 5
            prod_idx += 1

    # Sheet 1: 持倉
    ws1 = wb.active
    ws1.title = '持倉'
    active = Product.query.filter_by(status='active', user_id=current_uid()).order_by(Product.created_at).all()
    write_sheet(ws1, active)

    # Sheet 2: KO
    ws2 = wb.create_sheet('KO')
    ko = Product.query.filter_by(status='ko_exited', user_id=current_uid()).order_by(Product.created_at).all()
    write_sheet(ws2, ko, is_ko_sheet=True)

    # Sheet 3: 到期
    ws3 = wb.create_sheet('到期')
    matured = Product.query.filter_by(status='matured', user_id=current_uid()).order_by(Product.created_at).all()
    write_sheet(ws3, matured)

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf, download_name=f'SN記憶表格_{date.today().strftime("%Y%m%d")}.xlsx',
                     as_attachment=True,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


# ── 首頁：持倉總覽 ────────────────────────────────────────────────────────────
@app.route('/')
@login_required
def dashboard():
    active = Product.query.filter_by(status='active', user_id=current_uid()).order_by(Product.created_at).all()
    return render_template('dashboard.html', active=active, today=date.today())


# ── 已出場(KO)頁面 ───────────────────────────────────────────────────────────
@app.route('/ko')
@login_required
def ko_history():
    products = Product.query.filter_by(status='ko_exited', user_id=current_uid()).order_by(Product.maturity_date.desc()).all()
    return render_template('ko_history.html', products=products)


# ── 更新收盤價 ────────────────────────────────────────────────────────────────
@app.route('/fetch_prices')
@login_required
def fetch_prices():
    import yfinance as yf
    active = Product.query.filter_by(status='active', user_id=current_uid()).all()
    tickers = set()
    for p in active:
        for u in p.underlyings:
            if u.ticker:
                tickers.add(u.ticker)
    if not tickers:
        flash('沒有需要更新的標的', 'info')
        return redirect(url_for('dashboard'))

    try:
        today = date.today()
        # 先抓最新收盤價（前一完整交易日）
        data = yf.download(list(tickers), period='5d', progress=False)
        close = data['Close']
        prev_close = close[close.index.date < today]
        if prev_close.empty:
            prev_close = close
        price_date = prev_close.index[-1].date()

        updated = 0
        for p in active:
            for u in p.underlyings:
                if not u.ticker:
                    continue
                # 更新最新收盤價
                if u.ticker in prev_close.columns:
                    series = prev_close[u.ticker].dropna()
                    if len(series) > 0:
                        u.latest_price = round(float(series.iloc[-1]), 2)
                        u.price_date = price_date
                        updated += 1

                # 記憶式KO檢查：從比價日至今，是否曾收盤 >= KO水準
                if u.ko_level and not u.ko_hit and p.start_date:
                    hist = yf.download(u.ticker, start=p.start_date.isoformat(),
                                       end=today.isoformat(), progress=False)
                    if not hist.empty:
                        hist_close = hist['Close'].squeeze()
                        if (hist_close >= u.ko_level).any():
                            u.ko_hit = True

        db.session.commit()
        flash(f'已更新 {updated} 檔標的收盤價（{price_date.strftime("%Y/%m/%d")}）', 'success')
    except Exception as e:
        flash(f'更新失敗：{str(e)}', 'danger')

    return redirect(url_for('dashboard'))


# ── 客戶管理 ──────────────────────────────────────────────────────────────────
@app.route('/clients')
@login_required
def clients():
    all_clients = Client.query.filter_by(user_id=current_uid()).order_by(Client.name).all()
    return render_template('clients/index.html', clients=all_clients)


@app.route('/clients/add', methods=['GET', 'POST'])
@login_required
def add_client():
    if request.method == 'POST':
        name = request.form['name'].strip()
        if not name:
            flash('請輸入客戶姓名', 'danger')
            return redirect(url_for('add_client'))
        existing = Client.query.filter_by(name=name, user_id=current_uid()).first()
        if existing:
            flash('此客戶已存在', 'warning')
            return redirect(url_for('clients'))
        c = Client(name=name, name_masked=Client.mask_name(name), user_id=current_uid())
        db.session.add(c)
        db.session.commit()
        flash(f'已新增客戶：{name}', 'success')
        return redirect(url_for('clients'))
    return render_template('clients/add.html')


@app.route('/clients/<int:cid>/delete', methods=['POST'])
@login_required
def delete_client(cid):
    c = Client.query.get_or_404(cid)
    if c.positions:
        flash(f'{c.name_masked} 尚有部位紀錄，無法刪除', 'danger')
    else:
        db.session.delete(c)
        db.session.commit()
        flash(f'已刪除客戶 {c.name_masked}', 'success')
    return redirect(url_for('clients'))


# ── 商品管理 ──────────────────────────────────────────────────────────────────
@app.route('/products')
@login_required
def products():
    active = Product.query.filter_by(status='active', user_id=current_uid()).order_by(Product.created_at).all()
    ko_done = Product.query.filter_by(status='ko_exited', user_id=current_uid()).order_by(Product.created_at.desc()).all()
    matured = Product.query.filter_by(status='matured', user_id=current_uid()).order_by(Product.created_at.desc()).all()
    # 計算持倉總金額
    total_amount = sum(pos.investment_amount or 0 for p in active for pos in p.positions)
    return render_template('products/index.html', active=active, ko_done=ko_done,
                           matured=matured, total_amount=total_amount, today=date.today())


@app.route('/products/add', methods=['GET', 'POST'])
@login_required
def add_product():
    clients = Client.query.filter_by(user_id=current_uid()).order_by(Client.name).all()
    if request.method == 'POST':
        f = request.form
        # 建立商品
        p = Product(
            user_id       = current_uid(),
            product_code  = f['product_code'].strip(),
            issuer        = f.get('issuer', '').strip(),
            tenor_months  = int(f['tenor_months']) if f.get('tenor_months') else None,
            currency      = f.get('currency', 'USD'),
            coupon_rate   = float(f['coupon_rate']) / 100 if f.get('coupon_rate') else None,
            trade_date    = _parse_date(f.get('trade_date')),
            start_date    = _parse_date(f.get('start_date')),
            maturity_date = _parse_date(f.get('maturity_date')),
            ko_pct        = float(f['ko_pct']) / 100 if f.get('ko_pct') else None,
            strike_pct    = float(f['strike_pct']) / 100 if f.get('strike_pct') else None,
            eki_pct       = float(f['eki_pct']) / 100 if f.get('eki_pct') else None,
            ko_type       = f.get('ko_type', 'fixed'),
            special_notes = f.get('special_notes', '').strip(),
            status        = 'active',
        )
        db.session.add(p)
        db.session.flush()

        # 建立標的
        for i in range(1, 5):
            ticker = f.get(f'ticker_{i}', '').strip()
            if not ticker:
                continue
            init_p = float(f[f'init_price_{i}']) if f.get(f'init_price_{i}') else None
            u = Underlying(
                product_id    = p.id,
                ticker        = ticker.upper(),
                initial_price = init_p,
                ko_level      = round(init_p * p.ko_pct, 4) if init_p and p.ko_pct else None,
                strike_level  = round(init_p * p.strike_pct, 4) if init_p and p.strike_pct else None,
                eki_level     = round(init_p * p.eki_pct, 4) if init_p and p.eki_pct else None,
                ko_hit        = False,
                position_order= i,
            )
            db.session.add(u)

        # 建立部位
        client_id = f.get('client_id')
        amount    = f.get('investment_amount')
        if client_id and amount:
            pos = Position(
                client_id         = int(client_id),
                product_id        = p.id,
                investment_amount = float(amount),
                notes             = f.get('pos_notes', '').strip(),
            )
            db.session.add(pos)

        db.session.commit()
        flash(f'已新增商品：{p.product_code}', 'success')
        return redirect(url_for('dashboard'))

    return render_template('products/add.html', clients=clients)


@app.route('/products/<int:pid>')
@login_required
def product_detail(pid):
    p = Product.query.get_or_404(pid)
    return render_template('products/detail.html', product=p, today=date.today())


@app.route('/products/<int:pid>/ko_exit', methods=['POST'])
@login_required
def ko_exit(pid):
    p = Product.query.get_or_404(pid)
    p.status = 'ko_exited'
    db.session.commit()
    flash(f'{p.product_code} 已標記為提前出場', 'success')
    return redirect(url_for('dashboard'))


@app.route('/products/<int:pid>/reactivate', methods=['POST'])
@login_required
def reactivate(pid):
    p = Product.query.get_or_404(pid)
    p.status = 'active'
    db.session.commit()
    flash(f'{p.product_code} 已移回持倉中', 'success')
    return redirect(url_for('ko_history'))


@app.route('/products/<int:pid>/toggle_ko/<int:uid>', methods=['POST'])
@login_required
def toggle_ko(pid, uid):
    u = Underlying.query.get_or_404(uid)
    u.ko_hit = not u.ko_hit
    db.session.commit()
    return jsonify({'ko_hit': u.ko_hit})


# ── 編輯商品 ─────────────────────────────────────────────────────────────────
@app.route('/products/<int:pid>/edit', methods=['GET', 'POST'])
@login_required
def edit_product(pid):
    p = Product.query.get_or_404(pid)
    if request.method == 'POST':
        f = request.form
        p.product_code  = f['product_code'].strip()
        p.issuer        = f.get('issuer', '').strip()
        p.tenor_months  = int(f['tenor_months']) if f.get('tenor_months') else None
        p.currency      = f.get('currency', 'USD')
        p.coupon_rate   = float(f['coupon_rate']) / 100 if f.get('coupon_rate') else None
        p.trade_date    = _parse_date(f.get('trade_date'))
        p.start_date    = _parse_date(f.get('start_date'))
        p.maturity_date = _parse_date(f.get('maturity_date'))
        p.ko_pct        = float(f['ko_pct']) / 100 if f.get('ko_pct') else None
        p.strike_pct    = float(f['strike_pct']) / 100 if f.get('strike_pct') else None
        p.eki_pct       = float(f['eki_pct']) / 100 if f.get('eki_pct') else None
        p.ko_type       = f.get('ko_type', 'fixed')
        p.special_notes = f.get('special_notes', '').strip()

        # 更新標的
        existing = {u.id: u for u in p.underlyings}
        for i in range(1, 5):
            uid = f.get(f'underlying_id_{i}')
            ticker = f.get(f'ticker_{i}', '').strip()
            init_p = float(f[f'init_price_{i}']) if f.get(f'init_price_{i}') else None
            if uid and int(uid) in existing:
                u = existing[int(uid)]
                if not ticker:
                    db.session.delete(u)
                    continue
                u.ticker = ticker.upper()
                u.initial_price = init_p
                u.ko_level = round(init_p * p.ko_pct, 4) if init_p and p.ko_pct else None
                u.strike_level = round(init_p * p.strike_pct, 4) if init_p and p.strike_pct else None
                u.eki_level = round(init_p * p.eki_pct, 4) if init_p and p.eki_pct else None
            elif ticker:
                u = Underlying(
                    product_id=p.id, ticker=ticker.upper(), initial_price=init_p,
                    ko_level=round(init_p * p.ko_pct, 4) if init_p and p.ko_pct else None,
                    strike_level=round(init_p * p.strike_pct, 4) if init_p and p.strike_pct else None,
                    eki_level=round(init_p * p.eki_pct, 4) if init_p and p.eki_pct else None,
                    ko_hit=False, position_order=i,
                )
                db.session.add(u)

        db.session.commit()
        flash(f'{p.product_code} 已更新', 'success')
        if p.status == 'ko_exited':
            return redirect(url_for('ko_history'))
        return redirect(url_for('product_detail', pid=p.id))

    underlyings = sorted(p.underlyings, key=lambda u: u.position_order or 0)
    return render_template('products/edit.html', product=p, underlyings=underlyings)


# ── 部位管理（多客戶同一商品）────────────────────────────────────────────────
@app.route('/products/<int:pid>/add_position', methods=['POST'])
@login_required
def add_position(pid):
    f = request.form
    pos = Position(
        client_id         = int(f['client_id']),
        product_id        = pid,
        investment_amount = float(f['investment_amount']),
        notes             = f.get('notes', ''),
    )
    db.session.add(pos)
    db.session.commit()
    flash('已新增部位', 'success')
    return redirect(url_for('product_detail', pid=pid))


# ── API：新增客戶（AJAX）─────────────────────────────────────────────────────
@app.route('/api/clients', methods=['POST'])
@login_required
def api_add_client():
    data = request.get_json()
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': '請輸入客戶姓名'}), 400
    existing = Client.query.filter_by(name=name, user_id=current_uid()).first()
    if existing:
        return jsonify({'id': existing.id, 'name': existing.name_masked})
    c = Client(name=name, name_masked=Client.mask_name(name), user_id=current_uid())
    db.session.add(c)
    db.session.commit()
    return jsonify({'id': c.id, 'name': c.name_masked})


# ── 每日晨會快報 ─────────────────────────────────────────────────────────────
@app.route('/briefing')
@login_required
def briefing():
    from datetime import timedelta
    today = date.today()
    uid = current_uid()

    active = Product.query.filter_by(status='active', user_id=uid).order_by(Product.created_at).all()

    # 即將到期（30天內）
    expiring = [p for p in active if p.maturity_date and p.days_to_maturity is not None and 0 <= p.days_to_maturity <= 30]

    # 標的異動（漲跌超過3%）+ KO/Strike/EKI 警示
    alerts = []
    for p in active:
        for u in sorted(p.underlyings, key=lambda x: x.position_order or 0):
            if not u.latest_price or not u.initial_price:
                continue
            change_pct = (u.latest_price - u.initial_price) / u.initial_price
            alert = {
                'product_code': p.product_code,
                'ticker': u.ticker,
                'ticker_name': TICKER_NAME.get(u.ticker, ''),
                'latest_price': u.latest_price,
                'price_date': u.price_date,
                'change_pct': change_pct,
                'ko_dist': (u.latest_price / u.ko_level - 1) if u.ko_level else None,
                'strike_dist': (u.latest_price / u.strike_level - 1) if u.strike_level else None,
                'eki_dist': (u.latest_price / u.eki_level - 1) if u.eki_level else None,
                'ko_hit': u.ko_hit,
                'hit_strike': u.strike_level and u.latest_price <= u.strike_level,
                'hit_eki': u.eki_level and u.latest_price <= u.eki_level,
            }
            alerts.append(alert)

    # 市場指標（需付費方案才能抓）
    market = None
    try:
        import yfinance as yf
        indices = yf.download(['^GSPC', '^IXIC', '^DJI'], period='2d', progress=False)
        if not indices.empty:
            close = indices['Close']
            prev = close.iloc[-2] if len(close) >= 2 else close.iloc[-1]
            last = close.iloc[-1]
            market = {
                'sp500': {'price': round(float(last['^GSPC']), 2), 'chg': round(float((last['^GSPC']/prev['^GSPC']-1)*100), 2)},
                'nasdaq': {'price': round(float(last['^IXIC']), 2), 'chg': round(float((last['^IXIC']/prev['^IXIC']-1)*100), 2)},
                'dow': {'price': round(float(last['^DJI']), 2), 'chg': round(float((last['^DJI']/prev['^DJI']-1)*100), 2)},
            }
    except:
        market = None

    # Fear & Greed Index
    fear_greed = None
    try:
        import fear_greed as fg
        fgi = fg.get()
        fear_greed = {'score': round(fgi.score), 'rating': fgi.rating}
    except:
        try:
            import requests
            r = requests.get(f'https://production.dataviz.cnn.io/index/fearandgreed/graphdata/{today.isoformat()}',
                           headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
            if r.ok:
                data = r.json()
                if 'fear_and_greed' in data:
                    fg_data = data['fear_and_greed']
                    score = fg_data.get('score', 0)
                    rating = fg_data.get('rating', '')
                    fear_greed = {'score': round(score), 'rating': rating}
        except:
            fear_greed = None

    return render_template('briefing.html', today=today, active=active,
                           expiring=expiring, alerts=alerts, market=market,
                           fear_greed=fear_greed)


# ── 客戶 PDF 報告 ────────────────────────────────────────────────────────────
@app.route('/report/<int:cid>')
@login_required
def client_report(cid):
    from fpdf import FPDF
    from io import BytesIO
    from flask import send_file
    import platform

    import tempfile
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates

    client = Client.query.get_or_404(cid)
    positions = [pos for pos in client.positions if pos.product.user_id == current_uid()]
    today = date.today()

    class PDF(FPDF):
        def header(self):
            if self.page_no() > 1:
                self.set_font('chinese', '', 8)
                self.cell(0, 5, '持倉追蹤報告', align='R')
                self.ln(8)

        def footer(self):
            self.set_y(-15)
            self.set_font('chinese', '', 8)
            self.set_text_color(150, 150, 150)
            self.cell(0, 10, f'第 {self.page_no()} 頁', align='C')

    pdf = PDF()

    # 載入中文字型
    font_path = None
    if platform.system() == 'Windows':
        font_path = 'C:/Windows/Fonts/msjh.ttc'
    else:
        for p in ['/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc',
                  '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
                  '/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf',
                  '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc']:
            if os.path.exists(p):
                font_path = p
                break

    if font_path and os.path.exists(font_path):
        pdf.add_font('chinese', '', font_path, uni=True)
    else:
        pdf.add_font('chinese', '', uni=True)

    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    # ── 封面 ──
    pdf.set_font('chinese', '', 24)
    pdf.ln(30)
    pdf.cell(0, 15, '持倉追蹤報告', align='C', new_x='LMARGIN', new_y='NEXT')
    pdf.ln(5)
    pdf.set_font('chinese', '', 14)
    pdf.cell(0, 10, f'報告日期：{today.strftime("%Y/%m/%d")}', align='C', new_x='LMARGIN', new_y='NEXT')

    # 持倉摘要
    active_pos = [pos for pos in positions if pos.product.status == 'active']
    total_amount = sum(pos.investment_amount or 0 for pos in active_pos)
    total_monthly = sum(pos.monthly_coupon or 0 for pos in active_pos)

    pdf.ln(15)
    pdf.set_font('chinese', '', 12)
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(0, 10, f'持倉商品數：{len(active_pos)}    總投資金額：USD {total_amount:,.0f}    每月配息：USD {total_monthly:,.0f}',
             align='C', fill=True, new_x='LMARGIN', new_y='NEXT')

    # ── 圖表產生函數 ──
    def make_chart(ticker_symbol, product_code, ko_level, strike_level, eki_level):
        try:
            import yfinance as yf
            from datetime import timedelta
            start = (today - timedelta(days=365)).isoformat()
            data = yf.download(ticker_symbol, start=start, end=today.isoformat(), progress=False)
            if data.empty:
                return None
            close = data['Close'].squeeze()
            volume = data['Volume'].squeeze()

            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 4.5), height_ratios=[3, 1], sharex=True)
            fig.subplots_adjust(hspace=0.05)

            ax1.plot(close.index, close.values, color='#e74c3c', linewidth=2.5, label=ticker_symbol)
            if ko_level:
                ax1.axhline(y=ko_level, color='#e74c3c', linestyle='--', linewidth=1.5, label=f'KO ({ko_level:,.2f})')
            if strike_level:
                ax1.axhline(y=strike_level, color='#e67e22', linestyle='--', linewidth=1.5, label=f'Strike ({strike_level:,.2f})')
            if eki_level:
                ax1.axhline(y=eki_level, color='#8e44ad', linestyle='--', linewidth=1.5, label=f'EKI ({eki_level:,.2f})')

            last_price = close.iloc[-1]
            ax1.annotate(f'{last_price:.2f}', xy=(close.index[-1], last_price),
                        fontsize=10, fontweight='bold', color='#e74c3c',
                        xytext=(10, 5), textcoords='offset points')

            ax1.set_title(f'{ticker_symbol} - {product_code}', fontsize=13, fontweight='bold', pad=10)
            ax1.legend(loc='upper right', fontsize=8, framealpha=0.9)
            ax1.set_ylabel('Price (USD)', fontsize=9)
            ax1.grid(True, alpha=0.3)
            ax1.spines['top'].set_visible(False)
            ax1.spines['right'].set_visible(False)

            colors = ['#e74c3c' if i > 0 and close.iloc[i] < close.iloc[i-1] else '#27ae60' for i in range(len(close))]
            ax2.bar(volume.index, volume.values, color=colors, alpha=0.7, width=1)
            ax2.set_ylabel('Volume', fontsize=8)
            ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y/%m'))
            ax2.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
            ax2.grid(True, alpha=0.3)
            ax2.spines['top'].set_visible(False)
            ax2.spines['right'].set_visible(False)

            plt.tight_layout()
            tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
            plt.savefig(tmp.name, dpi=150)
            plt.close(fig)
            return tmp.name
        except:
            return None

    # ── 持倉明細 + 線圖 ──
    chart_files = []
    if active_pos:
        pdf.add_page()
        pdf.set_font('chinese', '', 16)
        pdf.cell(0, 12, '持倉明細', new_x='LMARGIN', new_y='NEXT')
        pdf.ln(3)

        for pos in active_pos:
            p = pos.product
            uls = sorted(p.underlyings, key=lambda u: u.position_order or 0)

            # 商品標題
            pdf.set_font('chinese', '', 11)
            pdf.set_fill_color(26, 26, 46)
            pdf.set_text_color(255, 255, 255)
            pdf.cell(0, 8, f'  {p.product_code}  |  {p.issuer or "-"}  |  {p.tenor_months}M  |  {"{:.1%}".format(p.coupon_rate) if p.coupon_rate else "-"}',
                     fill=True, new_x='LMARGIN', new_y='NEXT')
            pdf.set_text_color(0, 0, 0)

            # 基本資訊
            pdf.set_font('chinese', '', 9)
            days = p.days_to_maturity
            days_str = f'{days} 天' if days is not None else '-'
            pdf.cell(0, 6, f'投資金額：USD {pos.investment_amount:,.0f}    月配息：USD {pos.monthly_coupon:,.0f}    到期日：{p.maturity_date.strftime("%Y/%m/%d") if p.maturity_date else "-"}    剩餘：{days_str}',
                     new_x='LMARGIN', new_y='NEXT')

            # 標的表格
            pdf.set_font('chinese', '', 8)
            pdf.set_fill_color(220, 220, 220)
            col_w = [25, 25, 25, 25, 25, 25, 25, 15]
            headers = ['標的', '期初價格', 'KO水準', '執行價', 'EKI', '最新價', '距Strike', 'KO']
            for i, h in enumerate(headers):
                pdf.cell(col_w[i], 6, h, border=1, fill=True, align='C')
            pdf.ln()

            for u in uls:
                strike_dist = ''
                dist = 0
                if u.latest_price and u.strike_level:
                    dist = (u.latest_price / u.strike_level - 1) * 100
                    strike_dist = f'{dist:+.1f}%'

                vals = [
                    u.ticker,
                    f'{u.initial_price:,.2f}' if u.initial_price else '-',
                    f'{u.ko_level:,.2f}' if u.ko_level else '-',
                    f'{u.strike_level:,.2f}' if u.strike_level else '-',
                    f'{u.eki_level:,.2f}' if u.eki_level else '-',
                    f'{u.latest_price:,.2f}' if u.latest_price else '-',
                    strike_dist,
                    'V' if u.ko_hit else '',
                ]
                for i, v in enumerate(vals):
                    if i == 6 and strike_dist and dist < 0:
                        pdf.set_text_color(220, 50, 50)
                    elif i == 6 and strike_dist and dist > 0:
                        pdf.set_text_color(39, 174, 96)
                    pdf.cell(col_w[i], 5, v, border=1, align='C')
                    pdf.set_text_color(0, 0, 0)
                pdf.ln()

            pdf.ln(3)

            # 每個標的的線圖
            for u in uls:
                if not u.ticker:
                    continue
                chart_path = make_chart(u.ticker, p.product_code, u.ko_level, u.strike_level, u.eki_level)
                if chart_path:
                    chart_files.append(chart_path)
                    if pdf.get_y() > 160:
                        pdf.add_page()
                    pdf.image(chart_path, x=10, w=190)
                    pdf.ln(3)

            if pdf.get_y() > 200:
                pdf.add_page()

    # ── 風險提示 ──
    pdf.ln(5)
    pdf.set_font('chinese', '', 7)
    pdf.set_text_color(150, 150, 150)
    pdf.multi_cell(0, 4, '免責聲明：本報告僅供參考，不構成投資建議。結構型商品涉及本金風險，投資人應審慎評估自身風險承受能力。')

    buf = BytesIO()
    pdf.output(buf)
    buf.seek(0)

    # 清理暫存圖檔
    for f in chart_files:
        try:
            os.unlink(f)
        except:
            pass

    return send_file(buf, download_name=f'持倉追蹤_{today.strftime("%Y%m%d")}.pdf',
                     as_attachment=True, mimetype='application/pdf')


# ── 客戶報告列表 ─────────────────────────────────────────────────────────────
@app.route('/reports')
@login_required
def reports():
    all_clients = Client.query.filter_by(user_id=current_uid()).order_by(Client.name).all()
    return render_template('reports.html', clients=all_clients)


# ── 診斷（部署後可刪除）─────────────────────────────────────────────────────
@app.route('/debug_db')
@login_required
def debug_db():
    db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', 'NOT SET')
    # 隱藏密碼
    import re
    safe_uri = re.sub(r'://[^@]+@', '://***@', db_uri) if db_uri else 'NOT SET'
    uid = session.get('user_id')
    product_count = Product.query.filter_by(user_id=uid, status='active').count()
    client_count = Client.query.filter_by(user_id=uid).count()
    return jsonify({
        'db': safe_uri,
        'user_id': uid,
        'active_products': product_count,
        'clients': client_count,
    })


# ── 工具函數 ──────────────────────────────────────────────────────────────────
def _parse_date(s):
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except:
        return None


# ── 上傳 TS → 客戶文件圖片 ──────────────────────────────────────────────────
@app.route('/upload_ts', methods=['GET', 'POST'])
@login_required
def upload_ts():
    if request.method == 'POST':
        from client_doc_generator import generate_client_doc_image
        from flask import send_file
        import tempfile

        f = request.files.get('ts_file')
        if not f or not f.filename.endswith('.pdf'):
            flash('請上傳 PDF 檔案', 'danger')
            return redirect(url_for('upload_ts'))

        # 存暫存檔
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
        f.save(tmp.name)
        tmp.close()

        try:
            buf, data = generate_client_doc_image(tmp.name)
            product_code = data.get('product_code', 'unknown')
            filename = f'{product_code}_客戶文件.png'
            return send_file(buf, download_name=filename, as_attachment=True, mimetype='image/png')
        except Exception as e:
            flash(f'解析失敗：{str(e)}', 'danger')
            return redirect(url_for('upload_ts'))
        finally:
            os.unlink(tmp.name)

    return render_template('upload_ts.html')


# ── 報價圖片產生器 ─────────────────────────────────────────────────────────────
@app.route('/quote')
@login_required
def quote():
    return render_template('quote.html')


@app.route('/quote/generate', methods=['POST'])
@login_required
def generate_quote():
    from quote_generator import generate_quote_image
    from flask import send_file

    from quote_generator import TICKER_NAME as QT_TICKER_NAME
    tickers = request.form.getlist('tickers')

    # 處理自訂標的
    custom_text = request.form.get('custom_tickers', '').strip()
    if custom_text:
        for line in custom_text.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split(None, 1)
            if parts:
                ticker = parts[0].upper()
                if ticker not in tickers:
                    tickers.append(ticker)
                if len(parts) > 1:
                    QT_TICKER_NAME[ticker] = parts[1]

    if not tickers:
        flash('請至少選擇一個連結標的', 'danger')
        return redirect(url_for('quote'))

    # 解析百分比（使用者輸入 72.05 → 0.7205）
    def parse_pct(val):
        if not val:
            return None
        try:
            v = float(val)
            if v > 1:
                return v / 100
            return v
        except:
            return None

    params = {
        'product_type': request.form.get('product_type', 'FCN'),
        'tenor': request.form.get('tenor', '6M'),
        'strike_pct': parse_pct(request.form.get('strike_pct')),
        'ko_pct': parse_pct(request.form.get('ko_pct')),
        'coupon': parse_pct(request.form.get('coupon')),
        'eki_pct': parse_pct(request.form.get('eki_pct')),
        'ko_start': request.form.get('ko_start', '1M'),
        'memory_ko': request.form.get('memory_ko') == '1',
        'currency': request.form.get('currency', 'USD'),
        'issuer': request.form.get('issuer', ''),
        'tickers': tickers,
    }

    if not params['strike_pct'] or not params['coupon']:
        flash('Strike 和 Coupon 為必填', 'danger')
        return redirect(url_for('quote'))

    try:
        buf, price_date = generate_quote_image(params)
        filename = f'報價_{date.today().strftime("%Y%m%d")}.png'
        return send_file(buf, download_name=filename, as_attachment=True, mimetype='image/png')
    except Exception as e:
        flash(f'產生失敗：{str(e)}', 'danger')
        return redirect(url_for('quote'))


# ── LINE Webhook ─────────────────────────────────────────────────────────────
@app.route('/line/webhook', methods=['POST'])
def line_webhook():
    from line_bot import get_handler
    handler = get_handler()
    if not handler:
        return 'LINE Bot not configured', 503
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except Exception as e:
        app.logger.error(f'LINE Webhook error: {e}')
        return 'Error', 400
    return 'OK', 200


# ── 市場日報（網頁預覽 + LINE 推播）─────────────────────────────────────────
@app.route('/daily_report')
@login_required
def daily_report():
    from daily_report import generate_market_report
    from line_bot import is_configured
    report = generate_market_report(app)
    return render_template('daily_report.html', report=report, configured=is_configured())


@app.route('/daily_report/send', methods=['POST'])
@login_required
def send_daily_report():
    from daily_report import generate_market_report
    from line_bot import broadcast_text, is_configured, get_subscriber_count
    if not is_configured():
        flash('LINE Bot 尚未設定，請先設定 Channel Secret 和 Access Token', 'danger')
        return redirect(url_for('line_settings'))
    report = generate_market_report(app)
    success = broadcast_text(report)
    if success:
        count = get_subscriber_count(app)
        flash(f'日報已透過 LINE 廣播發送（訂閱人數：{count}）', 'success')
    else:
        flash('LINE 推播失敗，請檢查設定', 'danger')
    return redirect(url_for('daily_report'))


# ── LINE 設定頁 ──────────────────────────────────────────────────────────────
@app.route('/line_settings', methods=['GET', 'POST'])
@login_required
@admin_required
def line_settings():
    from line_bot import is_configured, get_subscriber_count
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if request.method == 'POST':
        secret = request.form.get('channel_secret', '').strip()
        token = request.form.get('access_token', '').strip()
        if secret and token:
            # 寫入 .env 檔
            env_lines = []
            if os.path.exists(env_path):
                with open(env_path, 'r', encoding='utf-8') as f:
                    env_lines = f.readlines()
            # 更新或新增
            new_lines = []
            found_secret = False
            found_token = False
            for line in env_lines:
                if line.startswith('LINE_CHANNEL_SECRET='):
                    new_lines.append(f'LINE_CHANNEL_SECRET={secret}\n')
                    found_secret = True
                elif line.startswith('LINE_CHANNEL_ACCESS_TOKEN='):
                    new_lines.append(f'LINE_CHANNEL_ACCESS_TOKEN={token}\n')
                    found_token = True
                else:
                    new_lines.append(line)
            if not found_secret:
                new_lines.append(f'LINE_CHANNEL_SECRET={secret}\n')
            if not found_token:
                new_lines.append(f'LINE_CHANNEL_ACCESS_TOKEN={token}\n')
            with open(env_path, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
            # 重新載入環境變數並初始化
            os.environ['LINE_CHANNEL_SECRET'] = secret
            os.environ['LINE_CHANNEL_ACCESS_TOKEN'] = token
            init_line(app)
            flash('LINE Bot 設定已更新，請重新啟動伺服器以完整生效', 'success')
        else:
            flash('請填寫完整的 Channel Secret 和 Access Token', 'danger')
        return redirect(url_for('line_settings'))

    current_secret = os.environ.get('LINE_CHANNEL_SECRET', '')
    current_token = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN', '')
    configured = is_configured()
    sub_count = get_subscriber_count(app) if configured else 0
    return render_template('line_settings.html',
                           configured=configured,
                           current_secret=current_secret,
                           current_token=current_token,
                           subscriber_count=sub_count)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', debug=(os.environ.get('FLASK_ENV') != 'production'), port=port)
