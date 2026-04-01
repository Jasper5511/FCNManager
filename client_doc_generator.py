"""
客戶文件圖片產生器 — 完全對齊使用者手動製作的 DOCX 格式
"""
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from ts_parser import parse_ts_pdf, _date_to_slash
import re, os


# 彭博代碼 → 中文名稱 + 資產種類
TICKER_INFO = {
    'NVDA': ('輝達', '股票'), 'AMD': ('超微半導體公司', '股票'),
    'TSM': ('台積電ADR', '存託憑證'), 'MU': ('美光科技公司', '股票'),
    'AVGO': ('博通公司', '股票'), 'AAPL': ('蘋果公司', '股票'),
    'MSFT': ('微軟公司', '股票'), 'GOOG': ('谷歌公司', '股票'),
    'AMZN': ('亞馬遜公司', '股票'), 'META': ('Meta公司', '股票'),
    'TSLA': ('特斯拉公司', '股票'), 'INTC': ('英特爾公司', '股票'),
    'ARM': ('安謀公司', '股票'), 'QCOM': ('高通公司', '股票'),
    'UNH': ('聯合健康集團', '股票'), 'JPM': ('摩根大通公司', '股票'),
    'GS': ('高盛集團', '股票'), 'BA': ('波音公司', '股票'),
    'AAL': ('美國航空集團', '股票'), 'AA': ('美國鋁業公司', '股票'),
    'NKE': ('耐吉公司', '股票'), 'COIN': ('Coinbase公司', '股票'),
    'DIS': ('迪士尼公司', '股票'), 'NFLX': ('Netflix公司', '股票'),
    'CRM': ('賽富時公司', '股票'), 'ORCL': ('甲骨文公司', '股票'),
    'ASML': ('艾司摩爾公司', '股票'), 'SMCI': ('超微電腦公司', '股票'),
    'UBER': ('優步公司', '股票'), 'PYPL': ('PayPal公司', '股票'),
    'VST': ('Vistra公司', '股票'), 'PLTR': ('Palantir公司', '股票'),
    'F': ('福特汽車公司', '股票'), 'CCL': ('嘉年華公司', '股票'),
    'X': ('美國鋼鐵公司', '股票'), 'MSTR': ('微策略公司', '股票'),
}


def _load_fonts():
    from setup_fonts import get_font_paths
    fp, fb = get_font_paths()
    return {
        'title': ImageFont.truetype(fb, 16),
        'normal': ImageFont.truetype(fp, 12),
        'bold': ImageFont.truetype(fb, 12),
        'small': ImageFont.truetype(fp, 10),
        'th': ImageFont.truetype(fb, 10),
        'td': ImageFont.truetype(fp, 10),
    }


def _center(draw, x, y, w, h, text, font, fill):
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th2 = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text((x + (w - tw) // 2, y + (h - th2) // 2), text, font=font, fill=fill)


def _left(draw, x, y, w, h, text, font, fill):
    bbox = draw.textbbox((0, 0), text, font=font)
    th2 = bbox[3] - bbox[1]
    draw.text((x + 4, y + (h - th2) // 2), text, font=font, fill=fill)


def generate_client_doc_image(pdf_path):
    """從 TS PDF 產生客戶文件圖片"""
    data = parse_ts_pdf(pdf_path)

    # 從 TS 再抽取中文公司名（如果解析器沒有的話）
    _enrich_underlyings(pdf_path, data)

    return _render_image(data), data


def generate_client_doc_image_from_data(data):
    return _render_image(data)


def _enrich_underlyings(pdf_path, data):
    """從 TS PDF 提取中文公司名和資產種類"""
    import fitz
    doc = fitz.open(pdf_path)
    full_text = ''
    for page in doc:
        full_text += page.get_text() + '\n'
    doc.close()

    for u in data.get('underlyings', []):
        ticker_raw = u['ticker'].split()[0]  # e.g. 'NVDA'
        # 從 TICKER_INFO 查
        if ticker_raw in TICKER_INFO:
            u['cn_name'] = TICKER_INFO[ticker_raw][0]
            u['asset_type'] = TICKER_INFO[ticker_raw][1]
        else:
            u['cn_name'] = ticker_raw
            u['asset_type'] = '股票'

        # 嘗試從 TS 中抓更精確的中文名
        pattern = rf'k=\d+\n(.+?)\n{ticker_raw}'
        m = re.search(pattern, full_text)
        if m:
            cn = m.group(1).strip()
            if len(cn) > 1 and not cn.startswith('k='):
                u['cn_name'] = cn


def _render_image(data):
    fonts = _load_fonts()

    BLACK = (0, 0, 0)
    WHITE = (255, 255, 255)
    RED = (192, 0, 0)
    DARK_BLUE = (31, 56, 100)
    GRAY_BG = (217, 217, 217)

    rh = 22  # 行高
    margin = 20
    img_w = 750

    # 預估高度（加大避免不夠）
    n_u = len(data.get('underlyings', []))
    n_s = len(data.get('schedule', []))
    est_h = margin + 50 + 100 + (n_u + 2) * rh + 200 + (n_s + 2) * rh + 100 + margin
    img = Image.new('RGB', (img_w, max(est_h, 1200)), WHITE)
    draw = ImageDraw.Draw(img)
    y = margin
    cw = img_w - margin * 2

    # ── 格式化數字 ──
    coupon = data.get('coupon_rate', '')
    try:
        c = float(coupon.replace('%', ''))
        coupon = f'{c:g}%'
    except:
        pass

    ko = data.get('ko_pct', '')
    strike = data.get('strike_pct', '')
    ki = data.get('ki_pct', '')

    monthly = data.get('monthly_coupon_pct', '')
    try:
        mc = float(monthly.replace('%', ''))
        monthly = f'{mc:g}%'
    except:
        pass

    # ── 標題（紅色）──
    title = f'(固定){data.get("product_code","")}最終商品文件<{data.get("issuer","")}  {data.get("tenor","")}> {coupon}'
    draw.text((margin, y), title, font=fonts['title'], fill=RED)
    y += 28

    # ── 定義區 ──
    def draw_rich(y, parts):
        x = margin
        for text, font_key, color in parts:
            f = fonts[font_key]
            bbox = draw.textbbox((0, 0), text, font=f)
            tw = bbox[2] - bbox[0]
            draw.text((x, y), text, font=f, fill=color)
            x += tw
        return y + 17

    y = draw_rich(y, [('期初價', 'bold', BLACK), ('：對任一連結標的而言，其交易日之價格。', 'normal', BLACK)])
    y = draw_rich(y, [
        ('記憶式自動提前出場價：', 'bold', BLACK),
        ('對任一連結標的而言，其', 'normal', BLACK),
        ('期初價', 'bold', BLACK),
        (f'{ko}%。', 'normal', BLACK),
    ])
    y = draw_rich(y, [
        ('執行價(轉換價)：', 'bold', BLACK),
        ('對任一連結標的而言，其期初價之', 'normal', BLACK),
        (f'{strike}%', 'normal', RED),
        ('。', 'normal', BLACK),
    ])
    if ki:
        y = draw_rich(y, [
            ('下限價格(EKI)：', 'bold', BLACK),
            ('對任一連結標的而言，其期初價之', 'normal', BLACK),
            (f'{ki}%', 'normal', RED),
            ('。', 'normal', BLACK),
        ])

    y += 8

    # ── 連結標的表 ──
    draw.text((margin, y), '連結標的：', font=fonts['bold'], fill=BLACK)
    y += 20

    underlyings = data.get('underlyings', [])
    has_eki = data.get('has_eki', False)

    # SG 格式表頭（7欄）
    if has_eki:
        headers = ['連結\n標的(k)', '連結標的資產', '彭博\n代碼', '連結\n標的資\n產種類', '期初價格', '自動提前出場價', f'執行價', '下限觸發價格']
        col_ws = [50, 110, 55, 50, 100, 100, 100, 100]
    else:
        headers = ['連結\n標的(k)', '連結標的資產', '彭博\n代碼', '連結\n標的資\n產種類', '期初價格', '自動提前出場價', '執行價']
        col_ws = [50, 120, 60, 55, 105, 110, 105]

    total = sum(col_ws)
    if total > cw:
        r = cw / total
        col_ws = [int(w * r) for w in col_ws]

    hdr_h = rh + 8

    # 表頭
    x = margin
    for i, h in enumerate(headers):
        w = col_ws[i]
        draw.rectangle([x, y, x + w, y + hdr_h], fill=GRAY_BG, outline=BLACK)
        _center(draw, x, y, w, hdr_h, h.replace('\n', ''), fonts['th'], BLACK)
        x += w
    y += hdr_h

    # 資料行
    for idx, u in enumerate(underlyings):
        x = margin
        ticker_raw = u['ticker'].split()[0]
        cn_name = u.get('cn_name', ticker_raw)
        asset_type = u.get('asset_type', '股票')

        vals = [
            f'k={idx+1}',
            cn_name,
            u['ticker'],
            asset_type,
            f'{u["initial_price"]}美元',
            f'{u.get("ko_level", "")}美元',
            f'{u.get("strike_level", "")}美元',
        ]
        if has_eki:
            vals.append(f'{u.get("ki_level", "")}美元' if u.get('ki_level') else '')

        for i, val in enumerate(vals):
            w = col_ws[i]
            draw.rectangle([x, y, x + w, y + rh], fill=WHITE, outline=BLACK)
            if i <= 1:
                _left(draw, x, y, w, rh, val, fonts['td'], BLACK)
            else:
                _center(draw, x, y, w, rh, val, fonts['td'], BLACK)
            x += w
        y += rh

    y += 12

    # ── 商品基本資料 ──
    trade = data.get('trade_date', '') or ''
    issue = data.get('issue_date', '') or ''
    maturity = data.get('maturity_date', '') or ''
    ac_start = data.get('autocall_start', '') or ''
    ac_end = data.get('autocall_end', '') or ''

    y = draw_rich(y, [('商品年期：', 'bold', BLACK), (f'{data.get("tenor_desc","")}(本商品發生記憶式自動提前出場事件除外)', 'normal', BLACK)])
    y = draw_rich(y, [('交易日：', 'bold', BLACK), (trade, 'normal', BLACK)])
    y = draw_rich(y, [('發行日：', 'bold', BLACK), (issue, 'normal', BLACK)])
    y = draw_rich(y, [('到期日：', 'bold', BLACK), (maturity, 'normal', BLACK)])

    if ac_start:
        # SG 用「最終評價日」，DBS 用「期末評價日」
        eval_label = '最終評價日' if data.get('issuer') == 'SG' else '期末評價日'
        y = draw_rich(y, [
            ('記憶式自動提前出場事件：', 'bold', BLACK),
            (f'{ac_start}(含)', 'bold', RED),
            (f'起至{eval_label}', 'normal', BLACK),
            (f'{ac_end}(含)', 'bold', DARK_BLUE),
        ])

    y = draw_rich(y, [('當所有連結標的之收盤價都曾經大於或等於其自動出場觸發水準，', 'normal', BLACK)])
    y = draw_rich(y, [('則本商品滿足記憶式自動提前出場條款。', 'normal', BLACK)])

    y += 8

    # ── 配息 ──
    y = draw_rich(y, [('每月固定配息：', 'normal', BLACK), ('於各交割日，發行機構將依下列計算公式以美元為計價單位給付：', 'normal', BLACK)])
    y = draw_rich(y, [
        ('每月配息金額', 'bold', BLACK),
        (' = ', 'bold', BLACK),
        ('商品面額 × ', 'normal', BLACK),
        (monthly, 'bold', RED),
    ])

    y += 8

    # ── 配息觀察期間表 ──
    draw.text((margin, y), '配息觀察期間及配息交割日：', font=fonts['bold'], fill=BLACK)
    y += 20

    schedule = data.get('schedule', [])
    if schedule:
        s_headers = ['配息週期(i)', '配息週期起始日(不含)', '配息週期終止日(含)', '配息日']
        s_cols = [80, 170, 170, 130]
        s_total = sum(s_cols)
        if s_total > cw:
            r = cw / s_total
            s_cols = [int(w * r) for w in s_cols]

        # 表頭
        x = margin
        for i, h in enumerate(s_headers):
            w = s_cols[i]
            draw.rectangle([x, y, x + w, y + rh], fill=GRAY_BG, outline=BLACK)
            _center(draw, x, y, w, rh, h, fonts['th'], BLACK)
            x += w
        y += rh

        # 資料
        for s in schedule:
            x = margin
            start = s.get('start_date', '')
            end = s.get('end_date', '')
            pay = s.get('payment_date', '')

            # 轉回中文日期格式
            start_cn = _slash_to_cn(start) if start else '不適用'
            end_cn = _slash_to_cn(end) if end else '不適用'
            pay_cn = _slash_to_cn(pay)

            vals = [f'i={s["period"]}', start_cn, end_cn, pay_cn]
            for i, val in enumerate(vals):
                w = s_cols[i]
                draw.rectangle([x, y, x + w, y + rh], fill=WHITE, outline=BLACK)
                _center(draw, x, y, w, rh, val, fonts['td'], BLACK)
                x += w
            y += rh

    y += 12

    # ── 備註（上下分隔線 + 深藍文字）──
    draw.line([(margin, y), (margin + cw, y)], fill=BLACK, width=1)
    y += 6
    note = '上述資料均節錄自附件「中文產品說明書」，僅供投資人參閱使用。'
    bbox = draw.textbbox((0, 0), note, font=fonts['small'])
    tw = bbox[2] - bbox[0]
    draw.text((margin + (cw - tw) // 2, y), note, font=fonts['small'], fill=DARK_BLUE)
    y += 16
    draw.line([(margin, y), (margin + cw, y)], fill=BLACK, width=1)
    y += 10

    img = img.crop((0, 0, img_w, y + margin))

    buf = BytesIO()
    img.save(buf, format='PNG', dpi=(300, 300))
    buf.seek(0)
    return buf


def _slash_to_cn(date_slash):
    """'2025/09/19' → '2025年09月19日'"""
    if not date_slash or date_slash == '不適用':
        return date_slash
    try:
        parts = date_slash.split('/')
        return f'{parts[0]}年{parts[1]}月{parts[2]}日'
    except:
        return date_slash
