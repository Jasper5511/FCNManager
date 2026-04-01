"""
市場日報產生器
- 美股三大指數漲跌
- 主要板塊表現
- VIX 恐慌指數
- 重大財經新聞摘要
- 持倉標的異動警示
"""
import yfinance as yf
from datetime import date, timedelta


def generate_market_report(app=None):
    """產生市場日報文字（適合 LINE 發送）"""
    today = date.today()
    sections = []

    # ── 標題 ──
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
    except Exception as e:
        sections.append(f'\n指數資料取得失敗')

    # ── VIX 恐慌指數 ──
    try:
        vix = _fetch_vix()
        if vix:
            level = '低' if vix['price'] < 15 else '中' if vix['price'] < 25 else '高' if vix['price'] < 35 else '極高'
            sections.append(f'\nVIX 恐慌指數: {vix["price"]:.2f} ({level})')
    except:
        pass

    # ── 板塊表現 ──
    try:
        sectors = _fetch_sectors()
        if sectors:
            sections.append('\n板塊表現')
            for name, chg in sectors:
                arrow = '▲' if chg >= 0 else '▼'
                sections.append(f'{name}: {arrow}{abs(chg):.2f}%')
    except:
        pass

    # ── 持倉標的異動 ──
    if app:
        try:
            alerts = _check_position_alerts(app)
            if alerts:
                sections.append('\n持倉標的異動')
                for alert in alerts:
                    sections.append(alert)
        except:
            pass

    # ── 注意事項 ──
    try:
        warnings = _check_expiring(app) if app else []
        if warnings:
            sections.append('\n注意事項')
            for w in warnings:
                sections.append(w)
    except:
        pass

    return '\n'.join(sections)


def _fetch_indices():
    """抓取三大指數"""
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
        except:
            pass
    return result


def _fetch_vix():
    """抓取 VIX 恐慌指數"""
    data = yf.download('^VIX', period='2d', progress=False)
    if data.empty:
        return None
    close = data['Close'].squeeze()
    return {'price': float(close.iloc[-1])}


def _fetch_sectors():
    """抓取主要板塊 ETF 表現"""
    sector_etfs = {
        'XLK': '科技',
        'XLF': '金融',
        'XLE': '能源',
        'XLV': '醫療',
        'XLY': '消費',
        'XLI': '工業',
        'SOXX': '半導體',
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
        except:
            pass

    # 依漲跌幅排序
    results.sort(key=lambda x: x[1], reverse=True)
    return results


def _check_position_alerts(app):
    """檢查持倉標的異動"""
    alerts = []
    with app.app_context():
        from models import Product, Underlying
        active = Product.query.filter_by(status='active').all()
        for p in active:
            for u in sorted(p.underlyings, key=lambda x: x.position_order or 0):
                if not u.latest_price or not u.initial_price:
                    continue

                # KO 距離警示
                if u.ko_level:
                    ko_dist = (u.latest_price / u.ko_level - 1)
                    if ko_dist >= -0.03 and ko_dist < 0:
                        alerts.append(f'  {u.ticker} 接近KO！距離僅 {ko_dist:.1%}')
                    elif ko_dist >= 0:
                        alerts.append(f'  {u.ticker} 已達KO水準！({u.latest_price:.2f} >= {u.ko_level:.2f})')

                # Strike 距離警示
                if u.strike_level and u.latest_price <= u.strike_level:
                    alerts.append(f'  {u.ticker} 已跌破Strike！({u.latest_price:.2f} <= {u.strike_level:.2f})')

                # EKI 距離警示
                if u.eki_level and u.latest_price <= u.eki_level:
                    alerts.append(f'  {u.ticker} 已跌破EKI！({u.latest_price:.2f} <= {u.eki_level:.2f})')

    return alerts


def _check_expiring(app):
    """檢查即將到期商品"""
    warnings = []
    with app.app_context():
        from models import Product
        active = Product.query.filter_by(status='active').all()
        for p in active:
            if p.maturity_date and p.days_to_maturity is not None:
                if 0 <= p.days_to_maturity <= 14:
                    warnings.append(f'  {p.product_code} 將於 {p.days_to_maturity} 天後到期 ({p.maturity_date.strftime("%m/%d")})')
                elif p.days_to_maturity < 0:
                    warnings.append(f'  {p.product_code} 已到期，請確認是否結算')
    return warnings
