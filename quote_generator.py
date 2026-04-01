"""
報價圖片產生器 — 100% 對齊使用者指定排版
"""
import yfinance as yf
from datetime import date
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import os

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
    'MARA': '馬拉松', 'RIOT': '銳拓', 'SNAP': '閱後即焚', 'SHOP': '購物',
    'SQ': '布洛克', 'ROKU': '串流平台', 'CRWD': '群衆打擊', 'SNOW': '雪花',
    'NET': '雲端閃耀', 'DKNG': '夢幻體育', 'ABNB': '愛彼迎',
    'RIVN': '里維安', 'LCID': '路希德', 'MSTR': '微策略',
}

ISSUER_NAME = {
    'HSBC': '匯豐', 'DBS': '星展', 'MS': '摩根士丹利', 'SG': '法興',
    'BNP': '法巴', 'UBS': '瑞銀', 'GS': '高盛', 'JPM': '摩根大通',
    'CITI': '花旗', 'BARC': '巴克萊', 'DB': '德銀', 'Natixis': '納帝希',
    'NOM': '野村', 'MAC': '麥格理', 'CIT': '花旗',
}


def fetch_closing_prices(tickers):
    """抓取前一完整交易日收盤價（多種方式備援）"""
    # 方式1：yfinance
    prices, price_date = _fetch_yfinance(tickers)
    if prices:
        return prices, price_date

    # 方式2：Yahoo Finance API 直接請求
    prices, price_date = _fetch_yahoo_api(tickers)
    if prices:
        return prices, price_date

    return {}, None


def _fetch_yfinance(tickers):
    """用 yfinance 抓取"""
    try:
        today = date.today()
        data = yf.download(tickers, period='5d', progress=False, threads=False)
        if data.empty:
            return {}, None
        close = data['Close']
        prev_close = close[close.index.date < today]
        if prev_close.empty:
            prev_close = close
        price_date = prev_close.index[-1].date()
        prices = {}
        if len(tickers) == 1:
            series = prev_close.squeeze()
            if hasattr(series, 'iloc'):
                prices[tickers[0]] = round(float(series.iloc[-1]), 2)
            else:
                prices[tickers[0]] = round(float(series), 2)
        else:
            for t in tickers:
                if t in prev_close.columns:
                    val = prev_close[t].dropna()
                    if len(val) > 0:
                        prices[t] = round(float(val.iloc[-1]), 2)
        return prices, price_date
    except Exception as e:
        print(f'yfinance failed: {e}')
        return {}, None


def _fetch_yahoo_api(tickers):
    """直接用 Yahoo Finance API 抓取（備援）"""
    import requests
    prices = {}
    price_date = None
    today = date.today()

    for ticker in tickers:
        try:
            url = f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=5d&interval=1d'
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            r = requests.get(url, headers=headers, timeout=10)
            if r.ok:
                data = r.json()
                result = data['chart']['result'][0]
                closes = result['indicators']['quote'][0]['close']
                timestamps = result['timestamp']
                # 找前一交易日
                for i in range(len(timestamps) - 1, -1, -1):
                    from datetime import datetime
                    dt = datetime.fromtimestamp(timestamps[i]).date()
                    if dt < today and closes[i] is not None:
                        prices[ticker] = round(closes[i], 2)
                        price_date = dt
                        break
        except Exception as e:
            print(f'Yahoo API fetch {ticker} failed: {e}')

    return prices, price_date


def _text_center(draw, x, y, w, h, text, font, fill):
    """在指定矩形內置中繪製文字"""
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text((x + (w - tw) // 2, y + (h - th) // 2), text, font=font, fill=fill)


def _text_right(draw, x, y, w, h, text, font, fill):
    """在指定矩形內靠右繪製文字"""
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text((x + w - tw - 8, y + (h - th) // 2), text, font=font, fill=fill)


def _text_left(draw, x, y, w, h, text, font, fill):
    """在指定矩形內靠左繪製文字"""
    bbox = draw.textbbox((0, 0), text, font=font)
    th = bbox[3] - bbox[1]
    draw.text((x + 8, y + (h - th) // 2), text, font=font, fill=fill)


def generate_quote_image(params):
    """產生報價圖片"""
    tickers = params['tickers']
    prices, price_date = fetch_closing_prices(tickers)
    price_date_str = price_date.strftime('%Y/%m/%d') if price_date else '---'

    # ── 字型 ──
    from setup_fonts import get_font_paths
    font_path, font_bold_path = get_font_paths()

    font = ImageFont.truetype(font_path, 16)
    font_bold = ImageFont.truetype(font_bold_path, 16)
    font_header = ImageFont.truetype(font_bold_path, 14)

    # ── 色彩 ──
    BLACK = (0, 0, 0)
    WHITE = (255, 255, 255)
    RED = (255, 0, 0)
    PINK = (252, 228, 225)             # 淺粉橘（帶點黃的粉紅）
    YELLOW_BG = (255, 255, 0)

    # ── 尺寸 ──
    row_h = 30

    # 計算欄位
    calc_cols = []
    if params.get('eki_pct') and isinstance(params['eki_pct'], (int, float)):
        calc_cols.append(('觸及生效價', params['eki_pct']))
    calc_cols.append(('預計執行價', params['strike_pct']))
    if isinstance(params.get('ko_pct'), (int, float)):
        calc_cols.append(('提前出場價', params['ko_pct']))
    n_calc = len(calc_cols)

    # 下半表欄寬
    btm_col0 = 130   # 連結標的
    btm_colN = 100    # 每個數值欄
    btm_total = btm_col0 + btm_colN * (1 + n_calc)  # 進場價 + calc欄

    # 上半表欄寬（總寬與下半表對齊）
    top_col1 = 110    # 英文
    top_col2 = 90     # 中文
    top_col3 = btm_total - top_col1 - top_col2  # 值欄（自動撐滿）

    total_w = btm_total
    btm_cols = [btm_col0] + [btm_colN] * (1 + n_calc)
    # 微調最後一欄對齊
    btm_actual = sum(btm_cols)
    if btm_actual != total_w:
        btm_cols[-1] += total_w - btm_actual

    margin = 15
    img_w = total_w + margin * 2

    # 高度：參數8行 + 發行機構1行 + 表頭2行 + 標的N行
    img_h = margin + 8 * row_h + row_h + 2 * row_h + len(tickers) * row_h + margin

    img = Image.new('RGB', (img_w, img_h), WHITE)
    draw = ImageDraw.Draw(img)

    x0 = margin
    y = margin

    # ── 上半部：商品參數（8行 x 3欄）──
    ko_display = params.get('ko_display', '')
    if not ko_display:
        ko_val = params.get('ko_pct', '')
        if isinstance(ko_val, (int, float)):
            ko_display = f'{ko_val:.0%}'
        else:
            ko_display = str(ko_val)

    strike_display = f'{params["strike_pct"]:.2%}' if isinstance(params['strike_pct'], (int, float)) else str(params['strike_pct'])
    coupon_display = f'{params["coupon"]:.2%}' if isinstance(params['coupon'], (int, float)) else str(params['coupon'])

    type_display = {
        'FCN': 'FCN(固定配息)',
        'FCN_stepdown': 'FCN(固定配息)-步階式',
        'BEN': 'Regular BEN',
    }.get(params['product_type'], params['product_type'])

    param_rows = [
        ('Type',       '類型',       type_display),
        ('Tenor',      '天期',       params['tenor']),
        ('Strike',     '預計執行價', strike_display),
        ('KO',         '出場價',     ko_display),
        ('Coupon',     '年化報酬率', coupon_display),
        ('KO Start',   '閉鎖',       params.get('ko_start', '1M')),
        ('Memory KO' if params.get('memory_ko') else 'KO', '記憶式' if params.get('memory_ko') else '非記憶式', 'YES'),
        ('Currency',   '幣別',       params.get('currency', 'USD')),
    ]

    for eng, chi, val in param_rows:
        x = x0
        # 英文標籤（淺粉紅底粗體靠左）
        draw.rectangle([x, y, x + top_col1, y + row_h], fill=PINK, outline=BLACK)
        _text_left(draw, x, y, top_col1, row_h, eng, font_bold, BLACK)
        x += top_col1
        # 中文標籤（淺粉紅底靠左）
        draw.rectangle([x, y, x + top_col2, y + row_h], fill=PINK, outline=BLACK)
        _text_left(draw, x, y, top_col2, row_h, chi, font, BLACK)
        x += top_col2
        # 值（深粉紅底，數字置中）
        draw.rectangle([x, y, x + top_col3, y + row_h], fill=WHITE, outline=BLACK)
        _text_center(draw, x, y, top_col3, row_h, str(val), font_bold, RED)
        y += row_h

    # ── 發行機構列（淺粉紅底紅字，與表格同寬）──
    issuer = params.get('issuer', '')
    issuer_display = f'發行機構  {issuer}'
    draw.rectangle([x0, y, x0 + total_w, y + row_h], fill=PINK, outline=BLACK)
    _text_left(draw, x0, y, total_w, row_h, issuer_display, font_bold, RED)
    y += row_h

    # ── 下半部：連結標的表頭（黑底白字，2行高）──
    header_row_h = row_h  # 每行高度
    # 第一行：標籤
    line1 = ['連結標的', '參考進場價']
    for label, pct in calc_cols:
        line1.append(label)
    # 第二行：數值
    today_str = date.today().strftime('%Y/%m/%d')
    line2 = ['', today_str]
    for label, pct in calc_cols:
        if isinstance(pct, (int, float)):
            line2.append(f'{pct:.2%}')
        else:
            line2.append('')

    # 繪製表頭（粉紅底，標籤與數值之間有分隔線）
    x = x0
    for i in range(len(line1)):
        w = btm_cols[i]
        if i == 0:
            # 連結標的：跨2行
            draw.rectangle([x, y, x + w, y + header_row_h * 2], fill=PINK, outline=BLACK)
            _text_center(draw, x, y, w, header_row_h * 2, line1[i], font_header, BLACK)
        else:
            # 上半格：標籤（有底線分隔）
            draw.rectangle([x, y, x + w, y + header_row_h], fill=PINK, outline=BLACK)
            _text_center(draw, x, y, w, header_row_h, line1[i], font_header, BLACK)
            # 下半格：數值（有頂線分隔）
            draw.rectangle([x, y + header_row_h, x + w, y + header_row_h * 2], fill=PINK, outline=BLACK)
            _text_center(draw, x, y + header_row_h, w, header_row_h, line2[i], font_header, BLACK)
        x += w
    y += header_row_h * 2

    # ── 標的資料行 ──
    for ticker in tickers:
        name = TICKER_NAME.get(ticker, '')
        display = f'{ticker}  {name}' if name else ticker
        price = prices.get(ticker)

        x = x0
        # 標的名稱（黃底靠左）
        w = btm_cols[0]
        draw.rectangle([x, y, x + w, y + row_h], fill=YELLOW_BG, outline=BLACK)
        _text_left(draw, x, y, w, row_h, display, font, BLACK)
        x += w

        # 收盤價（白底置中）
        w = btm_cols[1]
        draw.rectangle([x, y, x + w, y + row_h], fill=WHITE, outline=BLACK)
        price_str = f'{price:,.2f}' if price else 'N/A'
        _text_center(draw, x, y, w, row_h, price_str, font, BLACK)
        x += w

        # 計算欄（白底置中）
        for ci, (label, pct) in enumerate(calc_cols):
            w = btm_cols[2 + ci]
            draw.rectangle([x, y, x + w, y + row_h], fill=WHITE, outline=BLACK)
            if price and isinstance(pct, (int, float)):
                val_str = f'{price * pct:,.2f}'
            else:
                val_str = '---'
            _text_center(draw, x, y, w, row_h, val_str, font, BLACK)
            x += w

        y += row_h

    # 裁剪到實際高度
    img = img.crop((0, 0, img_w, y + margin))

    buf = BytesIO()
    img.save(buf, format='PNG', dpi=(300, 300))
    buf.seek(0)
    return buf, price_date
