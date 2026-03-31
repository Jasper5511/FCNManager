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
    'AAPL': '蘋果', 'MSFT': '微軟', 'GOOG': 'Google', 'AMZN': '亞馬遜',
    'META': 'Meta', 'TSLA': '特斯拉', 'ORCL': '甲骨文', 'CRM': 'Salesforce',
    'NFLX': 'Netflix', 'UBER': 'Uber', 'UNH': '聯合健康', 'JPM': '摩根大通',
    'GS': '高盛', 'BA': '波音', 'AAL': '美國航空', 'AA': '美國鋁業',
    'NKE': 'Nike', 'COIN': 'Coinbase',
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


# ── 工具函數 ──────────────────────────────────────────────────────────────────
def _parse_date(s):
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except:
        return None


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', debug=(os.environ.get('FLASK_ENV') != 'production'), port=port)
