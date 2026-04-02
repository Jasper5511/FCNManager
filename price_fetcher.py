"""
price_fetcher.py — 多來源股價抓取模組（15 來源層層備援）

報價/歷史/指數三大功能，每個功能依序嘗試所有可用來源，一個成功即回傳。

環境變數（有 Key 才會啟用該來源）：
  FINNHUB_API_KEY, TWELVEDATA_API_KEY, FMP_API_KEY, POLYGON_API_KEY,
  TIINGO_API_KEY, ALPHAVANTAGE_API_KEY, EODHD_API_KEY, STOCKDATA_API_KEY,
  NASDAQDATALINK_API_KEY, MARKETSTACK_API_KEY, TRADIER_API_KEY
"""
import os
import re
import logging
import time
from datetime import date, timedelta, datetime

import requests
import pandas as pd

log = logging.getLogger(__name__)

# ── Helpers ──────────────────────────────────────────────────────────────────

def _env(name):
    return os.environ.get(name, '')

def _get(url, headers=None, timeout=10):
    """HTTP GET → JSON or None"""
    try:
        r = requests.get(url, headers=headers, timeout=timeout)
        if r.ok:
            return r.json()
    except Exception:
        pass
    return None

def _ts(d):
    """date → UNIX timestamp"""
    return int(datetime.combine(d, datetime.min.time()).timestamp())

def _build_df(dates, closes, volumes=None):
    """建立標準 DataFrame（DatetimeIndex + Close + Volume）"""
    if not dates or not closes:
        return None
    df = pd.DataFrame({
        'Close': [float(c) for c in closes],
        'Volume': [float(v) for v in volumes] if volumes else [0] * len(closes),
    }, index=pd.to_datetime(dates))
    df.index.name = 'Date'
    df = df.sort_index()
    return df if not df.empty else None


# ════════════════════════════════════════════════════════════════════════════
#  QUOTES — fetch_quotes(tickers) → ({ticker: price}, price_date)
# ════════════════════════════════════════════════════════════════════════════

# ── 1. yfinance ──
def _q_yfinance(tickers, today):
    import yfinance as yf
    data = yf.download(tickers, period='5d', progress=False, threads=False)
    if data.empty:
        return {}, None
    close = data['Close']
    if isinstance(close, pd.Series):
        close = close.to_frame(tickers[0])
    prev = close[close.index.date < today]
    if prev.empty:
        prev = close
    pdate = prev.index[-1].date()
    prices = {}
    for t in tickers:
        if t in prev.columns:
            s = prev[t].dropna()
            if len(s):
                prices[t] = round(float(s.iloc[-1]), 2)
    return prices, pdate

# ── 2. Finnhub ──
def _q_finnhub(tickers, today):
    key = _env('FINNHUB_API_KEY')
    if not key:
        return {}, None
    prices = {}
    for t in tickers:
        d = _get(f'https://finnhub.io/api/v1/quote?symbol={t}&token={key}')
        if d and d.get('pc') and d['pc'] > 0:
            prices[t] = round(d['pc'], 2)
        time.sleep(0.15)
    return prices, today - timedelta(days=1) if prices else ({}, None)

# ── 3. Twelve Data ──
def _q_twelvedata(tickers, today):
    key = _env('TWELVEDATA_API_KEY')
    if not key:
        return {}, None
    prices = {}
    for t in tickers:
        d = _get(f'https://api.twelvedata.com/quote?symbol={t}&apikey={key}')
        if d and d.get('previous_close'):
            try:
                prices[t] = round(float(d['previous_close']), 2)
            except (ValueError, TypeError):
                pass
        time.sleep(0.5)
    return prices, today - timedelta(days=1) if prices else ({}, None)

# ── 4. FMP ──
def _q_fmp(tickers, today):
    key = _env('FMP_API_KEY')
    if not key:
        return {}, None
    syms = ','.join(tickers)
    d = _get(f'https://financialmodelingprep.com/api/v3/quote/{syms}?apikey={key}')
    if not d or not isinstance(d, list):
        return {}, None
    prices = {}
    for item in d:
        sym = item.get('symbol')
        pc = item.get('previousClose')
        if sym and pc:
            prices[sym] = round(float(pc), 2)
    return prices, today - timedelta(days=1) if prices else ({}, None)

# ── 5. Polygon.io ──
def _q_polygon(tickers, today):
    key = _env('POLYGON_API_KEY')
    if not key:
        return {}, None
    prices = {}
    for t in tickers:
        d = _get(f'https://api.polygon.io/v2/aggs/ticker/{t}/prev?apiKey={key}')
        if d and d.get('results'):
            c = d['results'][0].get('c')
            if c:
                prices[t] = round(float(c), 2)
        time.sleep(12.5)  # 5次/分
    return prices, today - timedelta(days=1) if prices else ({}, None)

# ── 6. Tiingo ──
def _q_tiingo(tickers, today):
    key = _env('TIINGO_API_KEY')
    if not key:
        return {}, None
    headers = {'Authorization': f'Token {key}'}
    prices = {}
    for t in tickers:
        d = _get(f'https://api.tiingo.com/iex/{t}', headers=headers)
        if d and isinstance(d, list) and len(d) and d[0].get('prevClose'):
            prices[t] = round(float(d[0]['prevClose']), 2)
        time.sleep(0.2)
    return prices, today - timedelta(days=1) if prices else ({}, None)

# ── 7. Alpha Vantage ──
def _q_alphavantage(tickers, today):
    key = _env('ALPHAVANTAGE_API_KEY')
    if not key:
        return {}, None
    prices = {}
    for t in tickers:
        d = _get(f'https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={t}&apikey={key}')
        if d and 'Global Quote' in d:
            pc = d['Global Quote'].get('08. previous close')
            if pc:
                try:
                    prices[t] = round(float(pc), 2)
                except (ValueError, TypeError):
                    pass
        time.sleep(3)
    return prices, today - timedelta(days=1) if prices else ({}, None)

# ── 8. Stooq ──
def _q_stooq(tickers, today):
    prices = {}
    start = (today - timedelta(days=7)).strftime('%Y%m%d')
    end = today.strftime('%Y%m%d')
    for t in tickers:
        try:
            url = f'https://stooq.com/q/d/l/?s={t.lower()}.us&d1={start}&d2={end}&i=d'
            df = pd.read_csv(url)
            if not df.empty and 'Close' in df.columns:
                prices[t] = round(float(df['Close'].iloc[-1]), 2)
        except Exception:
            pass
        time.sleep(0.3)
    return prices, today - timedelta(days=1) if prices else ({}, None)

# ── 9. EODHD ──
def _q_eodhd(tickers, today):
    key = _env('EODHD_API_KEY')
    if not key:
        return {}, None
    prices = {}
    for t in tickers:
        d = _get(f'https://eodhd.com/api/real-time/{t}.US?api_token={key}&fmt=json')
        if d and d.get('previousClose'):
            try:
                prices[t] = round(float(d['previousClose']), 2)
            except (ValueError, TypeError):
                pass
        time.sleep(1)
    return prices, today - timedelta(days=1) if prices else ({}, None)

# ── 10. Stockdata.org ──
def _q_stockdata(tickers, today):
    key = _env('STOCKDATA_API_KEY')
    if not key:
        return {}, None
    syms = ','.join(tickers)
    d = _get(f'https://api.stockdata.org/v1/data/quote?symbols={syms}&api_token={key}')
    if not d or not d.get('data'):
        return {}, None
    prices = {}
    for item in d['data']:
        sym = item.get('ticker')
        pc = item.get('previous_close_price')
        if sym and pc:
            prices[sym] = round(float(pc), 2)
    return prices, today - timedelta(days=1) if prices else ({}, None)

# ── 11. Nasdaq Data Link ──
def _q_nasdaqdatalink(tickers, today):
    key = _env('NASDAQDATALINK_API_KEY')
    if not key:
        return {}, None
    prices = {}
    for t in tickers:
        d = _get(f'https://data.nasdaq.com/api/v3/datasets/WIKI/{t}/data.json?api_key={key}&limit=1&column_index=4')
        if d and d.get('dataset_data', {}).get('data'):
            row = d['dataset_data']['data'][0]
            if row and len(row) >= 2 and row[1]:
                prices[t] = round(float(row[1]), 2)
        time.sleep(0.5)
    return prices, today - timedelta(days=1) if prices else ({}, None)

# ── 12. Marketstack ──
def _q_marketstack(tickers, today):
    key = _env('MARKETSTACK_API_KEY')
    if not key:
        return {}, None
    syms = ','.join(tickers)
    d = _get(f'http://api.marketstack.com/v1/eod/latest?access_key={key}&symbols={syms}')
    if not d or not d.get('data'):
        return {}, None
    prices = {}
    pdate = None
    for item in d['data']:
        sym = item.get('symbol')
        c = item.get('close')
        if sym and c:
            prices[sym] = round(float(c), 2)
            if not pdate and item.get('date'):
                try:
                    pdate = datetime.strptime(item['date'][:10], '%Y-%m-%d').date()
                except Exception:
                    pass
    return prices, pdate or (today - timedelta(days=1)) if prices else ({}, None)

# ── 13. Yahoo Direct HTTP ──
def _q_yahoo_direct(tickers, today):
    prices = {}
    hdrs = {'User-Agent': 'Mozilla/5.0'}
    for t in tickers:
        d = _get(f'https://query1.finance.yahoo.com/v8/finance/chart/{t}?range=5d&interval=1d', headers=hdrs)
        if d and d.get('chart', {}).get('result'):
            result = d['chart']['result'][0]
            closes = result.get('indicators', {}).get('quote', [{}])[0].get('close', [])
            stamps = result.get('timestamp', [])
            valid = [(ts, c) for ts, c in zip(stamps, closes)
                     if c is not None and datetime.fromtimestamp(ts).date() < today]
            if valid:
                prices[t] = round(float(valid[-1][1]), 2)
        time.sleep(0.3)
    return prices, today - timedelta(days=1) if prices else ({}, None)

# ── 14. Google Finance ──
def _q_google(tickers, today):
    prices = {}
    for t in tickers:
        for exch in ['NASDAQ', 'NYSE', 'NYSEARCA']:
            try:
                r = requests.get(f'https://www.google.com/finance/quote/{t}:{exch}',
                                 headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
                if r.ok:
                    m = re.search(r'data-last-price="([\d.]+)"', r.text)
                    if m:
                        prices[t] = round(float(m.group(1)), 2)
                        break
            except Exception:
                pass
        time.sleep(0.5)
    return prices, today if prices else ({}, None)

# ── 15. Tradier Sandbox ──
def _q_tradier(tickers, today):
    key = _env('TRADIER_API_KEY')
    if not key:
        return {}, None
    syms = ','.join(tickers)
    headers = {'Authorization': f'Bearer {key}', 'Accept': 'application/json'}
    d = _get(f'https://sandbox.tradier.com/v1/markets/quotes?symbols={syms}', headers=headers)
    if not d or not d.get('quotes', {}).get('quote'):
        return {}, None
    quotes = d['quotes']['quote']
    if isinstance(quotes, dict):
        quotes = [quotes]
    prices = {}
    for q in quotes:
        sym = q.get('symbol')
        pc = q.get('prevclose')
        if sym and pc:
            prices[sym] = round(float(pc), 2)
    return prices, today - timedelta(days=1) if prices else ({}, None)


# ── 主函數 ──
_QUOTE_SOURCES = [
    _q_yfinance, _q_finnhub, _q_twelvedata, _q_fmp, _q_polygon,
    _q_tiingo, _q_alphavantage, _q_stooq, _q_eodhd, _q_stockdata,
    _q_nasdaqdatalink, _q_marketstack, _q_yahoo_direct, _q_google, _q_tradier,
]

def fetch_quotes(tickers):
    """抓取前收盤價（15 來源備援）→ ({ticker: price}, price_date)"""
    tickers = list(set(tickers))
    today = date.today()
    for fn in _QUOTE_SOURCES:
        try:
            prices, pdate = fn(tickers, today)
            if prices:
                log.info(f'[quotes] {fn.__name__}: {len(prices)}/{len(tickers)} tickers')
                return prices, pdate
        except Exception as e:
            log.debug(f'[quotes] {fn.__name__}: {e}')
    return {}, None


# ════════════════════════════════════════════════════════════════════════════
#  HISTORY — fetch_history(ticker, start, end) → DataFrame(Close, Volume)
# ════════════════════════════════════════════════════════════════════════════

# ── 1. yfinance ──
def _h_yfinance(ticker, start, end):
    import yfinance as yf
    data = yf.download(ticker, start=start.isoformat(), end=end.isoformat(),
                       progress=False, threads=False)
    if data.empty:
        return None
    close = data['Close'].squeeze()
    volume = data['Volume'].squeeze() if 'Volume' in data.columns else pd.Series(0, index=close.index)
    df = pd.DataFrame({'Close': close, 'Volume': volume})
    return df if not df.empty else None

# ── 2. Finnhub ──
def _h_finnhub(ticker, start, end):
    key = _env('FINNHUB_API_KEY')
    if not key:
        return None
    d = _get(f'https://finnhub.io/api/v1/stock/candle?symbol={ticker}&resolution=D'
             f'&from={_ts(start)}&to={_ts(end)}&token={key}')
    if not d or d.get('s') != 'ok':
        return None
    dates = [datetime.fromtimestamp(t) for t in d['t']]
    return _build_df(dates, d['c'], d.get('v'))

# ── 3. Twelve Data ──
def _h_twelvedata(ticker, start, end):
    key = _env('TWELVEDATA_API_KEY')
    if not key:
        return None
    d = _get(f'https://api.twelvedata.com/time_series?symbol={ticker}&interval=1day'
             f'&start_date={start}&end_date={end}&outputsize=5000&apikey={key}')
    if not d or not d.get('values'):
        return None
    dates = [v['datetime'] for v in d['values']]
    closes = [v['close'] for v in d['values']]
    volumes = [v.get('volume', 0) for v in d['values']]
    return _build_df(dates, closes, volumes)

# ── 4. FMP ──
def _h_fmp(ticker, start, end):
    key = _env('FMP_API_KEY')
    if not key:
        return None
    d = _get(f'https://financialmodelingprep.com/api/v3/historical-price-full/{ticker}'
             f'?from={start}&to={end}&apikey={key}')
    if not d or not d.get('historical'):
        return None
    hist = d['historical']
    dates = [h['date'] for h in hist]
    closes = [h['close'] for h in hist]
    volumes = [h.get('volume', 0) for h in hist]
    return _build_df(dates, closes, volumes)

# ── 5. Polygon.io ──
def _h_polygon(ticker, start, end):
    key = _env('POLYGON_API_KEY')
    if not key:
        return None
    d = _get(f'https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/'
             f'{start}/{end}?adjusted=true&sort=asc&apiKey={key}')
    if not d or not d.get('results'):
        return None
    dates = [datetime.fromtimestamp(r['t'] / 1000) for r in d['results']]
    closes = [r['c'] for r in d['results']]
    volumes = [r.get('v', 0) for r in d['results']]
    return _build_df(dates, closes, volumes)

# ── 6. Tiingo ──
def _h_tiingo(ticker, start, end):
    key = _env('TIINGO_API_KEY')
    if not key:
        return None
    headers = {'Authorization': f'Token {key}'}
    d = _get(f'https://api.tiingo.com/tiingo/daily/{ticker}/prices'
             f'?startDate={start}&endDate={end}', headers=headers)
    if not d or not isinstance(d, list):
        return None
    dates = [item['date'][:10] for item in d]
    closes = [item['close'] for item in d]
    volumes = [item.get('volume', 0) for item in d]
    return _build_df(dates, closes, volumes)

# ── 7. Alpha Vantage ──
def _h_alphavantage(ticker, start, end):
    key = _env('ALPHAVANTAGE_API_KEY')
    if not key:
        return None
    d = _get(f'https://www.alphavantage.co/query?function=TIME_SERIES_DAILY'
             f'&symbol={ticker}&outputsize=full&apikey={key}')
    if not d or 'Time Series (Daily)' not in d:
        return None
    ts = d['Time Series (Daily)']
    dates, closes, volumes = [], [], []
    for dt_str, vals in ts.items():
        dt = datetime.strptime(dt_str, '%Y-%m-%d').date()
        if start <= dt <= end:
            dates.append(dt_str)
            closes.append(vals['4. close'])
            volumes.append(vals.get('5. volume', 0))
    return _build_df(dates, closes, volumes)

# ── 8. Stooq ──
def _h_stooq(ticker, start, end):
    try:
        d1 = start.strftime('%Y%m%d')
        d2 = end.strftime('%Y%m%d')
        url = f'https://stooq.com/q/d/l/?s={ticker.lower()}.us&d1={d1}&d2={d2}&i=d'
        df = pd.read_csv(url, parse_dates=['Date'], index_col='Date')
        if df.empty or 'Close' not in df.columns:
            return None
        result = pd.DataFrame({'Close': df['Close']})
        if 'Volume' in df.columns:
            result['Volume'] = df['Volume']
        else:
            result['Volume'] = 0
        return result.sort_index()
    except Exception:
        return None

# ── 9. EODHD ──
def _h_eodhd(ticker, start, end):
    key = _env('EODHD_API_KEY')
    if not key:
        return None
    d = _get(f'https://eodhd.com/api/eod/{ticker}.US?from={start}&to={end}'
             f'&api_token={key}&fmt=json')
    if not d or not isinstance(d, list):
        return None
    dates = [item['date'] for item in d]
    closes = [item['close'] for item in d]
    volumes = [item.get('volume', 0) for item in d]
    return _build_df(dates, closes, volumes)

# ── 10. Nasdaq Data Link ──
def _h_nasdaqdatalink(ticker, start, end):
    key = _env('NASDAQDATALINK_API_KEY')
    if not key:
        return None
    d = _get(f'https://data.nasdaq.com/api/v3/datasets/WIKI/{ticker}/data.json'
             f'?api_key={key}&start_date={start}&end_date={end}')
    if not d or not d.get('dataset_data', {}).get('data'):
        return None
    rows = d['dataset_data']['data']
    cols = d['dataset_data'].get('column_names', [])
    close_idx = cols.index('Close') if 'Close' in cols else 4
    vol_idx = cols.index('Volume') if 'Volume' in cols else 5
    dates = [r[0] for r in rows]
    closes = [r[close_idx] for r in rows if len(r) > close_idx]
    volumes = [r[vol_idx] if len(r) > vol_idx else 0 for r in rows]
    return _build_df(dates, closes, volumes)

# ── 11. Marketstack ──
def _h_marketstack(ticker, start, end):
    key = _env('MARKETSTACK_API_KEY')
    if not key:
        return None
    d = _get(f'http://api.marketstack.com/v1/eod?access_key={key}'
             f'&symbols={ticker}&date_from={start}&date_to={end}&limit=1000')
    if not d or not d.get('data'):
        return None
    dates = [item['date'][:10] for item in d['data']]
    closes = [item['close'] for item in d['data']]
    volumes = [item.get('volume', 0) for item in d['data']]
    return _build_df(dates, closes, volumes)

# ── 12. Yahoo Direct HTTP ──
def _h_yahoo_direct(ticker, start, end):
    hdrs = {'User-Agent': 'Mozilla/5.0'}
    p1, p2 = _ts(start), _ts(end)
    d = _get(f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}'
             f'?period1={p1}&period2={p2}&interval=1d', headers=hdrs)
    if not d or not d.get('chart', {}).get('result'):
        return None
    result = d['chart']['result'][0]
    stamps = result.get('timestamp', [])
    quote = result.get('indicators', {}).get('quote', [{}])[0]
    closes = quote.get('close', [])
    volumes = quote.get('volume', [])
    if not stamps or not closes:
        return None
    dates = [datetime.fromtimestamp(ts) for ts in stamps]
    volumes = [v if v else 0 for v in volumes]
    closes_clean = [c if c else None for c in closes]
    return _build_df(dates, closes_clean, volumes)

# ── 13. Tradier ──
def _h_tradier(ticker, start, end):
    key = _env('TRADIER_API_KEY')
    if not key:
        return None
    headers = {'Authorization': f'Bearer {key}', 'Accept': 'application/json'}
    d = _get(f'https://sandbox.tradier.com/v1/markets/history'
             f'?symbol={ticker}&interval=daily&start={start}&end={end}', headers=headers)
    if not d or not d.get('history', {}).get('day'):
        return None
    days = d['history']['day']
    if isinstance(days, dict):
        days = [days]
    dates = [item['date'] for item in days]
    closes = [item['close'] for item in days]
    volumes = [item.get('volume', 0) for item in days]
    return _build_df(dates, closes, volumes)


# ── 主函數 ──
_HISTORY_SOURCES = [
    _h_yfinance, _h_finnhub, _h_twelvedata, _h_fmp, _h_polygon,
    _h_tiingo, _h_alphavantage, _h_stooq, _h_eodhd,
    _h_nasdaqdatalink, _h_marketstack, _h_yahoo_direct, _h_tradier,
]

def fetch_history(ticker, start_date, end_date):
    """抓取歷史日K線（13 來源備援）→ DataFrame(Close, Volume) or None"""
    for fn in _HISTORY_SOURCES:
        try:
            df = fn(ticker, start_date, end_date)
            if df is not None and not df.empty:
                log.info(f'[history] {fn.__name__}: {ticker} got {len(df)} rows')
                return df
        except Exception as e:
            log.debug(f'[history] {fn.__name__}: {ticker}: {e}')
    return None


# ════════════════════════════════════════════════════════════════════════════
#  INDICES — fetch_indices() → {sp500: {price, chg}, nasdaq: ..., dow: ...}
# ════════════════════════════════════════════════════════════════════════════

def _pct(last, prev):
    if prev and prev != 0:
        return round((last / prev - 1) * 100, 2)
    return 0.0

# ── 1. yfinance ──
def _i_yfinance():
    import yfinance as yf
    data = yf.download(['^GSPC', '^IXIC', '^DJI'], period='2d', progress=False, threads=False)
    if data.empty:
        return None
    close = data['Close']
    if len(close) < 2:
        return None
    prev, last = close.iloc[-2], close.iloc[-1]
    return {
        'sp500':  {'price': round(float(last['^GSPC']), 2), 'chg': _pct(last['^GSPC'], prev['^GSPC'])},
        'nasdaq': {'price': round(float(last['^IXIC']), 2), 'chg': _pct(last['^IXIC'], prev['^IXIC'])},
        'dow':    {'price': round(float(last['^DJI']), 2),  'chg': _pct(last['^DJI'], prev['^DJI'])},
    }

# ── 2. Twelve Data ──
def _i_twelvedata():
    key = _env('TWELVEDATA_API_KEY')
    if not key:
        return None
    syms = {'SPX': 'sp500', 'IXIC': 'nasdaq', 'DJI': 'dow'}
    result = {}
    for sym, name in syms.items():
        d = _get(f'https://api.twelvedata.com/quote?symbol={sym}&apikey={key}')
        if d and d.get('close') and d.get('previous_close'):
            try:
                last = float(d['close'])
                prev = float(d['previous_close'])
                result[name] = {'price': round(last, 2), 'chg': _pct(last, prev)}
            except (ValueError, TypeError):
                pass
        time.sleep(0.5)
    return result if len(result) == 3 else None

# ── 3. FMP ──
def _i_fmp():
    key = _env('FMP_API_KEY')
    if not key:
        return None
    d = _get(f'https://financialmodelingprep.com/api/v3/quote/%5EGSPC,%5EIXIC,%5EDJI?apikey={key}')
    if not d or not isinstance(d, list):
        return None
    mapping = {'^GSPC': 'sp500', '^IXIC': 'nasdaq', '^DJI': 'dow'}
    result = {}
    for item in d:
        sym = item.get('symbol')
        if sym in mapping:
            pc = item.get('previousClose', 0)
            price = item.get('price', 0)
            result[mapping[sym]] = {'price': round(float(price), 2), 'chg': _pct(price, pc)}
    return result if len(result) == 3 else None

# ── 4. Yahoo Direct ──
def _i_yahoo_direct():
    hdrs = {'User-Agent': 'Mozilla/5.0'}
    mapping = {'^GSPC': 'sp500', '^IXIC': 'nasdaq', '^DJI': 'dow'}
    result = {}
    for sym, name in mapping.items():
        d = _get(f'https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=2d&interval=1d',
                 headers=hdrs)
        if d and d.get('chart', {}).get('result'):
            r = d['chart']['result'][0]
            closes = r.get('indicators', {}).get('quote', [{}])[0].get('close', [])
            if len(closes) >= 2 and closes[-1] and closes[-2]:
                result[name] = {
                    'price': round(float(closes[-1]), 2),
                    'chg': _pct(closes[-1], closes[-2]),
                }
        time.sleep(0.2)
    return result if len(result) == 3 else None

# ── 5. Polygon.io ──
def _i_polygon():
    key = _env('POLYGON_API_KEY')
    if not key:
        return None
    mapping = {'I:SPX': 'sp500', 'I:COMP': 'nasdaq', 'I:DJI': 'dow'}
    result = {}
    for sym, name in mapping.items():
        d = _get(f'https://api.polygon.io/v2/aggs/ticker/{sym}/prev?apiKey={key}')
        if d and d.get('results'):
            r = d['results'][0]
            c, o = r.get('c'), r.get('o')
            if c:
                result[name] = {'price': round(float(c), 2), 'chg': _pct(c, o) if o else 0.0}
        time.sleep(12.5)
    return result if len(result) == 3 else None

# ── 6. Stooq ──
def _i_stooq():
    mapping = {'^spx': 'sp500', '^ndq': 'nasdaq', '^dji': 'dow'}
    today = date.today()
    start = (today - timedelta(days=7)).strftime('%Y%m%d')
    end = today.strftime('%Y%m%d')
    result = {}
    for sym, name in mapping.items():
        try:
            url = f'https://stooq.com/q/d/l/?s={sym}&d1={start}&d2={end}&i=d'
            df = pd.read_csv(url)
            if not df.empty and 'Close' in df.columns and len(df) >= 2:
                last = float(df['Close'].iloc[-1])
                prev = float(df['Close'].iloc[-2])
                result[name] = {'price': round(last, 2), 'chg': _pct(last, prev)}
        except Exception:
            pass
        time.sleep(0.3)
    return result if len(result) == 3 else None

# ── 7. EODHD ──
def _i_eodhd():
    key = _env('EODHD_API_KEY')
    if not key:
        return None
    mapping = {'GSPC.INDX': 'sp500', 'IXIC.INDX': 'nasdaq', 'DJI.INDX': 'dow'}
    result = {}
    for sym, name in mapping.items():
        d = _get(f'https://eodhd.com/api/real-time/{sym}?api_token={key}&fmt=json')
        if d and d.get('close') and d.get('previousClose'):
            try:
                last = float(d['close'])
                prev = float(d['previousClose'])
                result[name] = {'price': round(last, 2), 'chg': _pct(last, prev)}
            except (ValueError, TypeError):
                pass
        time.sleep(1)
    return result if len(result) == 3 else None


# ── 主函數 ──
_INDICES_SOURCES = [
    _i_yfinance, _i_twelvedata, _i_fmp, _i_yahoo_direct,
    _i_polygon, _i_stooq, _i_eodhd,
]

def fetch_indices():
    """抓取三大指數（7 來源備援）→ {sp500: {price, chg}, nasdaq: ..., dow: ...} or None"""
    for fn in _INDICES_SOURCES:
        try:
            result = fn()
            if result:
                log.info(f'[indices] {fn.__name__}: OK')
                return result
        except Exception as e:
            log.debug(f'[indices] {fn.__name__}: {e}')
    return None
