"""
TS (Term Sheet) PDF 解析器
支援 DBS、SG 等不同發行商格式
"""
import re
import fitz  # PyMuPDF


def parse_ts_pdf(pdf_path):
    """解析 TS PDF，回傳結構化資料"""
    doc = fitz.open(pdf_path)
    full_text = ''
    for page in doc:
        full_text += page.get_text() + '\n'
    doc.close()

    data = {}

    # ── 商品代號 ──
    m = re.search(r'受託或銷售機構商品代號[：:\s]*(\d{4}SN\d+)', full_text)
    if m:
        data['product_code'] = m.group(1)

    # ── 發行機構 ──
    issuer_map = {
        '星展': 'DBS', 'DBS Bank': 'DBS',
        'SG ISSUER': 'SG', '法興': 'SG', 'Societe Generale': 'SG',
        '匯豐': 'HSBC', 'HSBC': 'HSBC',
        '摩根士丹利': 'MS', 'Morgan Stanley': 'MS',
        '法巴': 'BNP', 'BNP': 'BNP',
        '瑞銀': 'UBS', 'UBS': 'UBS',
        '高盛': 'GS', 'Goldman': 'GS',
        '摩根大通': 'JPM', 'JPMorgan': 'JPM',
        '花旗': 'CITI', 'Citigroup': 'CITI', 'Citibank': 'CITI',
        '野村': 'NOM', 'Nomura': 'NOM',
        '納帝希': 'Natixis', 'Natixis': 'Natixis',
        '麥格理': 'MAC', 'Macquarie': 'MAC',
    }
    for key, code in issuer_map.items():
        if key in full_text[:2000]:
            data['issuer'] = code
            break

    # ── 天期 ──
    m = re.search(r'(\d+)\s*個月', full_text[:500])
    if m:
        months = int(m.group(1))
        data['tenor_months'] = months
        data['tenor'] = f'{months}M'
        data['tenor_desc'] = f'{months} 個月'

    # ── 計價幣別 ──
    if '美元' in full_text[:500]:
        data['currency'] = 'USD'
    elif '澳幣' in full_text[:500]:
        data['currency'] = 'AUD'
    elif '日圓' in full_text[:500]:
        data['currency'] = 'JPY'

    # ── 日期 ──
    data['trade_date'] = _find_date(r'交易日[：:]\s*(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)', full_text)
    if not data['trade_date']:
        # SG 格式：訂價日
        data['trade_date'] = _find_date(r'訂價日[：:]\s*(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)', full_text)

    data['issue_date'] = _find_date(r'發行日[：:]\s*(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)', full_text)
    if not data['issue_date']:
        data['issue_date'] = _find_date(r'發行日[／/]交割日[：:]\s*(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)', full_text)
    data['maturity_date'] = _find_date(r'到期日[：:].*?(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)', full_text)

    # ── Coupon ──
    # DBS 格式：最大利率值：...1.0000%（即12%/12）
    m = re.search(r'最大利率值[：:].*?(\d+\.?\d*)%.*?即\s*(\d+\.?\d*)%\s*/\s*12', full_text)
    if m:
        data['monthly_coupon_pct'] = f'{m.group(1)}%'
        data['coupon_rate'] = f'{m.group(2)}%'
    else:
        # SG 格式：配息率 ＝0.7500% (年率 9.0000%)
        m = re.search(r'配息率\s*[＝=]\s*(\d+\.?\d*)%\s*[（(]年率\s*(\d+\.?\d*)%[）)]', full_text)
        if m:
            data['monthly_coupon_pct'] = f'{m.group(1)}%'
            data['coupon_rate'] = f'{m.group(2)}%'
        else:
            # 備用
            m = re.search(r'固定.*?(\d+\.?\d*)%', full_text[:500])
            if m:
                rate = float(m.group(1))
                data['coupon_rate'] = f'{rate:.0f}%'

    # ── KO / Strike / EKI 百分比 ──
    # DBS 格式
    m = re.search(r'自動提前出場價格\s*[（(]期初價格的\s*(\d+\.?\d*)%[）)]', full_text)
    if m:
        data['ko_pct'] = m.group(1)
    else:
        # SG 格式
        m = re.search(r'自動提前出場價[：:]\s*連結標的之期初價格的\s*(\d+\.?\d*)%', full_text)
        if m:
            data['ko_pct'] = m.group(1)

    # Strike
    m = re.search(r'執行價格\s*[（(]期初價格的\s*(\d+\.?\d*)%[）)]', full_text)
    if m:
        data['strike_pct'] = m.group(1)
    else:
        m = re.search(r'執行價[：:]\s*連結標的期初價格的\s*(\d+\.?\d*)%', full_text)
        if m:
            data['strike_pct'] = m.group(1)

    # EKI
    m = re.search(r'下限觸發價格\s*[（(]期初價格的\s*(\d+\.?\d*)%[）)]', full_text)
    if m:
        data['ki_pct'] = m.group(1)

    # ── 自動出場日期 ──
    m = re.search(r'自動提前出場.*?(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)\s*[（(]含[）)].*?(?:期末評價日|最終評價日)\s*(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)', full_text)
    if m:
        data['autocall_start'] = m.group(1).strip()
        data['autocall_end'] = m.group(2).strip()
    else:
        # SG 格式：記憶事件觀察期間：自XXXX年X月X日（含）起至最終評價日（含）
        m = re.search(r'記憶事件觀察期間[：:]\s*自\s*(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)', full_text)
        if m:
            data['autocall_start'] = m.group(1).strip()
        # autocall_end = 到期日（SG 格式的最終評價日通常就是到期日前幾天，用到期日代替）
        if not data.get('autocall_end') and data.get('maturity_date'):
            data['autocall_end'] = data['maturity_date']
        # 嘗試找 最終評價日：XXXX年X月X日
        m2 = re.search(r'最終評價日[：:]\n?\s*(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)', full_text)
        if m2:
            data['autocall_end'] = m2.group(1).strip()

    # ── 觀察起始日 ──
    m = re.search(r'觀察起始日[：:]\s*(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)', full_text)
    if m:
        data['obs_start_date'] = m.group(1).strip()

    # ── 連結標的 ──
    data['underlyings'] = _parse_underlyings(full_text, data)
    data['has_eki'] = bool(data.get('ki_pct'))

    # ── 配息觀察期間 ──
    data['schedule'] = _parse_schedule(full_text, data)

    # ── 商品類型 ──
    data['product_type'] = '固定'

    return data


def _find_date(pattern, text):
    m = re.search(pattern, text)
    if m:
        return m.group(1).strip()
    return None


def _parse_underlyings(full_text, data):
    """解析連結標的表格（支援多種格式）"""
    underlyings = []

    # === 方式1：DBS 格式（表1，分欄） ===
    m = re.search(r'表1\s*\n\s*彭博代碼', full_text)
    if m:
        block = full_text[m.start():m.start() + 1500]
        tickers = _extract_unique_tickers(block)
        prices = re.findall(r'美元\s*([\d,]+\.?\d*)', block)
        n = len(tickers)
        has_eki = bool(data.get('ki_pct'))
        cols = 4 if has_eki else 3
        if n > 0 and len(prices) >= n * cols:
            for i in range(n):
                u = {
                    'ticker': tickers[i],
                    'initial_price': prices[i],
                    'strike_level': prices[n + i],
                    'ko_level': prices[n * 2 + i],
                    'ki_level': prices[n * 3 + i] if has_eki and n * 3 + i < len(prices) else None,
                }
                underlyings.append(u)
            return underlyings

    # === 方式2：SG 格式（k=1, k=2... 分行排列） ===
    # 格式：k=1\n中文名\nTICKER\nUW\n股票\n價格美元\n價格美元\n價格美元
    # 多種分行組合
    sg_patterns = [
        # TICKER\nUW（分行）
        r'k=(\d+)\n.+?\n([A-Z]{1,6})\n(UW|UN)\n(?:股票|存託\n?憑證)\n([\d,.]+)美元\n([\d,.]+)美元\n([\d,.]+)美元',
        # TICKER UW（同行）
        r'k=(\d+)\n.+?\n([A-Z]{1,6})\s(UW|UN)\n(?:股票|存託\n?憑證)\n([\d,.]+)美元\n([\d,.]+)美元\n([\d,.]+)美元',
        # TICKER\nUW 中間有空白
        r'k=(\d+)\n.+?\n([A-Z]{1,6})\s*\n\s*(UW|UN)\n(?:股票|存託\s*\n?\s*憑證)\n([\d,.]+)美元\n([\d,.]+)美元\n([\d,.]+)美元',
    ]
    matches = []
    for pat in sg_patterns:
        found = list(re.finditer(pat, full_text))
        for fm in found:
            ticker = fm.group(2)
            if not any(x['ticker'].startswith(ticker) for x in underlyings):
                matches.append(fm)
    if matches:
        for m in matches:
            ticker = m.group(2)
            suffix = m.group(3)
            u = {
                'ticker': f'{ticker} {suffix}',
                'initial_price': m.group(4),
                'ko_level': m.group(5),      # 自動提前出場價
                'strike_level': m.group(6),   # 執行價
                'ki_level': None,
            }
            if not any(x['ticker'] == u['ticker'] for x in underlyings):
                underlyings.append(u)
        return underlyings

    # === 方式3：更寬鬆的匹配 ===
    # 找 "XXX UW" 或 "XXX UN" 後面跟著美元價格
    block_match = re.search(r'期初價格.*?(?:表|連結標的)', full_text)
    if not block_match:
        # 找包含多個 ticker 的區塊
        ticker_pattern = r'([A-Z]{2,6})\s*\n\s*(?:UW|UN)'
        ticker_matches = list(re.finditer(ticker_pattern, full_text))
        if ticker_matches:
            # 在 ticker 附近找價格
            for tm in ticker_matches:
                ticker = tm.group(1)
                # 在後面 500 字元找美元價格
                nearby = full_text[tm.start():tm.start() + 500]
                prices = re.findall(r'([\d,]+\.?\d*)美元', nearby)
                if len(prices) >= 3:
                    u = {
                        'ticker': f'{ticker} UW',
                        'initial_price': prices[0],
                        'ko_level': prices[1],
                        'strike_level': prices[2],
                        'ki_level': prices[3] if len(prices) > 3 else None,
                    }
                    if not any(x['ticker'] == u['ticker'] for x in underlyings):
                        underlyings.append(u)

    return underlyings


def _extract_unique_tickers(block):
    """從文字區塊中提取唯一的 ticker 列表"""
    tickers = re.findall(r'([A-Z]{1,6})\s+(?:UW|UN)\s', block)
    seen = set()
    unique = []
    for t in tickers:
        key = f'{t} UW'
        if t not in seen:
            seen.add(t)
            unique.append(key)
    return unique


def _parse_schedule(full_text, data):
    """解析配息觀察期間表"""
    schedule = []

    # 找表A 或觀察期間表
    m = re.search(r'表A', full_text)
    if not m:
        # SG 格式
        m = re.search(r'配息週期起始日', full_text)
    if not m:
        return schedule

    block = full_text[m.start():m.start() + 3000]

    # === SG 格式：i=N 配息週期起始日 配息週期終止日 配息日 ===
    sg_schedule = re.findall(
        r'i=(\d+)\n(\d{4}年\d{1,2}月\d{1,2}日|不適用)\n(\d{4}年\d{1,2}月\d{1,2}日|不適用)\n(\d{4}年\d{1,2}月\d{1,2}日)',
        full_text
    )
    if sg_schedule:
        for period, start, end, payment in sg_schedule:
            start_slash = _date_to_slash(start) if start != '不適用' else ''
            end_slash = _date_to_slash(end) if end != '不適用' else ''
            payment_slash = _date_to_slash(payment)
            schedule.append({
                'period': period,
                'start_date': start_slash,
                'end_date': end_slash,
                'payment_date': payment_slash,
            })
        return schedule

    # 找所有日期
    dates = re.findall(r'(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日', block)
    date_strs = [f'{y}/{int(mo):02d}/{int(d):02d}' for y, mo, d in dates]

    if not date_strs:
        return schedule

    tenor = data.get('tenor_months', 0)
    if tenor and len(date_strs) >= tenor * 2:
        n = tenor
        for i in range(n):
            end_date = date_strs[i]
            payment_date = date_strs[n + i] if n + i < len(date_strs) else ''
            schedule.append({
                'period': str(i + 1),
                'end_date': end_date,
                'payment_date': payment_date,
            })
    elif len(date_strs) >= 2:
        # 嘗試每2個日期一組
        for i in range(0, len(date_strs) - 1, 2):
            schedule.append({
                'period': str(len(schedule) + 1),
                'end_date': date_strs[i],
                'payment_date': date_strs[i + 1],
            })

    # 補開始日
    if schedule and data.get('obs_start_date'):
        obs_start = _date_to_slash(data['obs_start_date'])
        schedule[0]['start_date'] = obs_start
        for i in range(1, len(schedule)):
            schedule[i]['start_date'] = _next_day(schedule[i-1]['end_date'])

    return schedule


def _date_to_slash(date_str):
    m = re.match(r'(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日', date_str)
    if m:
        return f'{m.group(1)}/{int(m.group(2)):02d}/{int(m.group(3)):02d}'
    return date_str


def _next_day(date_slash):
    try:
        from datetime import datetime, timedelta
        dt = datetime.strptime(date_slash, '%Y/%m/%d')
        return (dt + timedelta(days=1)).strftime('%Y/%m/%d')
    except:
        return date_slash
