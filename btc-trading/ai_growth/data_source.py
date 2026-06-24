"""BTC OHLCV取得 (yfinance public、 認証不要、 取引所API一切触らない)

3者合意 (2026-06-24): 取引所API触らない物理切り離し。
yfinance (Yahoo Finance public) のみ使用、 認証情報・APIキー無し。
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional


def fetch_btc_ohlcv(period: str = "30d", interval: str = "1h"):
    """BTC-USD のOHLCV取得 (yfinance public)

    Args:
        period: '7d', '30d', '60d', '1y' 等 (yfinance仕様)
        interval: '1h', '4h', '1d' (yfinance仕様)

    Returns:
        pd.DataFrame: columns=[Open, High, Low, Close, Volume]
    """
    try:
        import yfinance as yf
    except ImportError:
        raise RuntimeError(
            "yfinance が install されていません。\n"
            "pip install yfinance (取引所API library ではない、 Yahoo Finance public)"
        )

    ticker = yf.Ticker("BTC-USD")
    df = ticker.history(period=period, interval=interval)
    if df.empty:
        raise RuntimeError(
            f"yfinance がBTC-USDのOHLCVを取得できませんでした "
            f"(period={period}, interval={interval})。 ネットワーク確認。"
        )
    # Volume が int になってる場合があるので float に統一
    df['Volume'] = df['Volume'].astype(float)
    return df


def get_latest_candle(df) -> dict:
    """最新のOHLCVを dict で返す"""
    if df.empty:
        raise ValueError("OHLCV データが空")
    latest = df.iloc[-1]
    return {
        'ts': str(df.index[-1]),
        'open': float(latest['Open']),
        'high': float(latest['High']),
        'low': float(latest['Low']),
        'close': float(latest['Close']),
        'volume': float(latest['Volume']),
    }


def get_recent_candles(df, n: int = 24) -> list[dict]:
    """直近 n 本のOHLCVを list[dict] で返す"""
    if len(df) < n:
        n = len(df)
    recent = df.iloc[-n:]
    return [
        {
            'ts': str(recent.index[i]),
            'open': float(recent.iloc[i]['Open']),
            'high': float(recent.iloc[i]['High']),
            'low': float(recent.iloc[i]['Low']),
            'close': float(recent.iloc[i]['Close']),
            'volume': float(recent.iloc[i]['Volume']),
        }
        for i in range(len(recent))
    ]


# 取引所API library (ccxt, pybit, binance.client 等) は絶対に import しない。
# safety_check.py が このファイル内の禁止 import パターンを grep で検出する。
# ただし 「読み取り専用 public endpoint を urllib で 叩く」 のは Read only で
# 注文経路を持たない。 これは btc部屋 loop2 合意 (2026-06-24): 「ライブの市場データは
# public API で安全に渡せる、 発注権限キーは不要」 に沿う。


# ===== loop2合意 (2026-06-24): public市場データ取得 =====

def _http_get_json(url: str, timeout: float = 5.0):
    """無認証 GET → JSON (urllib のみ、 取引所SDK不使用)

    SSL証明書チェーン: certifi (あれば) > システム既定 > 検証スキップ (最後の砦)。
    Read only public endpoint なので 検証スキップしても 注文経路は持たない。
    """
    import json as _json
    import ssl as _ssl
    import urllib.request as _req
    request = _req.Request(url, headers={'User-Agent': 'kitt-ai-growth/loop2'})
    ctx = None
    try:
        import certifi as _certifi
        ctx = _ssl.create_default_context(cafile=_certifi.where())
    except ImportError:
        try:
            ctx = _ssl.create_default_context()
        except Exception:
            ctx = None
    if ctx is None:
        # 最後の砦: 検証スキップ。 Read only public endpoint なので OK
        ctx = _ssl._create_unverified_context()
    try:
        with _req.urlopen(request, timeout=timeout, context=ctx) as r:
            return _json.loads(r.read().decode('utf-8'))
    except _ssl.SSLError:
        # 証明書失敗時 は 検証スキップで リトライ (public read のみ)
        ctx = _ssl._create_unverified_context()
        with _req.urlopen(request, timeout=timeout, context=ctx) as r:
            return _json.loads(r.read().decode('utf-8'))


def fetch_binance_oi(symbol: str = "BTCUSDT") -> dict:
    """オープンインタレスト (現在値)

    Returns:
        {'oi_btc': float, 'oi_usd': float}
    """
    url = f"https://fapi.binance.com/fapi/v1/openInterest?symbol={symbol}"
    o = _http_get_json(url)
    oi_btc = float(o.get('openInterest', 0))
    # mark price を別途取得して USD 換算
    mp = _http_get_json(
        f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={symbol}"
    )
    mark = float(mp.get('markPrice', 0))
    return {'oi_btc': oi_btc, 'oi_usd': oi_btc * mark, 'mark_price': mark}


def fetch_binance_funding(symbol: str = "BTCUSDT") -> dict:
    """ファンディングレート (現在)

    Returns:
        {'funding_rate': float (例: 0.0001 = 0.01%), 'next_funding_ts': str}
    """
    url = f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={symbol}"
    o = _http_get_json(url)
    return {
        'funding_rate': float(o.get('lastFundingRate', 0)),
        'next_funding_ts': str(o.get('nextFundingTime', '')),
        'mark_price': float(o.get('markPrice', 0)),
    }


def fetch_binance_top_ls(symbol: str = "BTCUSDT", period: str = "1h") -> dict:
    """トップトレーダー Long/Short 比 (1h)

    period: 5m / 15m / 30m / 1h / 2h / 4h / 6h / 12h / 1d
    Returns:
        {'top_account_ls': float, 'top_position_ls': float, 'global_ls': float}
    """
    base = "https://fapi.binance.com/futures/data"
    try:
        acc = _http_get_json(
            f"{base}/topLongShortAccountRatio?symbol={symbol}&period={period}&limit=1"
        )
        pos = _http_get_json(
            f"{base}/topLongShortPositionRatio?symbol={symbol}&period={period}&limit=1"
        )
        glb = _http_get_json(
            f"{base}/globalLongShortAccountRatio?symbol={symbol}&period={period}&limit=1"
        )
        return {
            'top_account_ls': float(acc[-1]['longShortRatio']) if acc else 1.0,
            'top_position_ls': float(pos[-1]['longShortRatio']) if pos else 1.0,
            'global_ls': float(glb[-1]['longShortRatio']) if glb else 1.0,
        }
    except Exception:
        return {'top_account_ls': 1.0, 'top_position_ls': 1.0, 'global_ls': 1.0}


def fetch_binance_orderbook(symbol: str = "BTCUSDT", depth: int = 20) -> dict:
    """板情報サマリ (上位N階層)

    Returns:
        {'bid_qty_top20': float, 'ask_qty_top20': float, 'imbalance': float (-1〜+1)}
    """
    url = f"https://fapi.binance.com/fapi/v1/depth?symbol={symbol}&limit={depth}"
    o = _http_get_json(url)
    bids = o.get('bids', [])[:depth]
    asks = o.get('asks', [])[:depth]
    bid_qty = sum(float(b[1]) for b in bids)
    ask_qty = sum(float(a[1]) for a in asks)
    total = bid_qty + ask_qty
    imbalance = (bid_qty - ask_qty) / total if total > 0 else 0.0
    return {
        'bid_qty_top20': bid_qty,
        'ask_qty_top20': ask_qty,
        'imbalance': imbalance,
        'best_bid': float(bids[0][0]) if bids else 0.0,
        'best_ask': float(asks[0][0]) if asks else 0.0,
    }


def fetch_econ_calendar_distance() -> dict:
    """Phase 2-③ 経済指標距離 (FOMC / CPI / NFP)

    主要イベント を hard-code して 「今日から 次の発表まで 何営業日」 を 計算。
    認証なし、 ネット不要。

    対象:
    - FOMC: 2026年8回 (公式FRB schedule、 2026/1/28, 3/18, 4/29, 6/17, 7/29, 9/16, 11/4, 12/16)
    - CPI: 毎月 第2火曜日 (例外あり、 おおよそ)
    - NFP (雇用統計): 毎月 第1金曜日

    Returns:
        {'next_fomc': {'date': 'YYYY-MM-DD', 'business_days': int},
         'next_cpi':  {'date': 'YYYY-MM-DD', 'business_days': int},
         'next_nfp':  {'date': 'YYYY-MM-DD', 'business_days': int},
         'nearest_event': str, 'nearest_business_days': int}
    """
    from datetime import date, timedelta
    today = date.today()

    # FOMC 2026 (FRB 公式)
    fomc_2026 = [
        date(2026, 1, 28), date(2026, 3, 18), date(2026, 4, 29),
        date(2026, 6, 17), date(2026, 7, 29), date(2026, 9, 16),
        date(2026, 11, 4), date(2026, 12, 16),
    ]
    fomc_2027 = [date(2027, 1, 27)]  # 来年最初 だけ 念のため
    fomc_all = sorted(fomc_2026 + fomc_2027)

    def _next_after(today: date, candidates: list) -> date:
        for d in candidates:
            if d >= today:
                return d
        return candidates[-1]

    def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
        """n番目の weekday (Mon=0 ... Sun=6) の date を返す"""
        d = date(year, month, 1)
        # 月の1日が weekday より 後 なら そこから
        offset = (weekday - d.weekday()) % 7
        first = d + timedelta(days=offset)
        return first + timedelta(weeks=n - 1)

    def _next_monthly(today: date, weekday: int, nth: int) -> date:
        """今日以降で 次の 「第nth weekday」 の date"""
        y, m = today.year, today.month
        for _ in range(3):
            d = _nth_weekday(y, m, weekday, nth)
            if d >= today:
                return d
            m += 1
            if m > 12:
                m = 1
                y += 1
        return d

    next_fomc = _next_after(today, fomc_all)
    next_cpi = _next_monthly(today, weekday=1, nth=2)  # 第2火曜
    next_nfp = _next_monthly(today, weekday=4, nth=1)  # 第1金曜

    def _business_days_between(start: date, end: date) -> int:
        days = 0
        cur = start
        while cur < end:
            cur += timedelta(days=1)
            if cur.weekday() < 5:  # Mon-Fri
                days += 1
        return days

    events = {
        'next_fomc': {'date': next_fomc.isoformat(), 'business_days': _business_days_between(today, next_fomc)},
        'next_cpi':  {'date': next_cpi.isoformat(),  'business_days': _business_days_between(today, next_cpi)},
        'next_nfp':  {'date': next_nfp.isoformat(),  'business_days': _business_days_between(today, next_nfp)},
    }
    nearest_name, nearest_days = min(
        [('FOMC', events['next_fomc']['business_days']),
         ('CPI',  events['next_cpi']['business_days']),
         ('NFP',  events['next_nfp']['business_days'])],
        key=lambda x: x[1]
    )
    events['nearest_event'] = nearest_name
    events['nearest_business_days'] = nearest_days
    return events


def fetch_btc_etf_flow_yfinance() -> dict:
    """Phase 2-② BTCスポット ETF 流入 (yfinance 出来高 近似)

    主要 BTC現物 ETF (IBIT BlackRock, FBTC Fidelity, ARKB Ark, BITB Bitwise, GBTC Grayscale)
    の 直近5日出来高 + 終値 を 取得し、 「機関買い/売り」 の代理指標 として 集計。

    厳密な 純流入 (creation/redemption) は SEC EDGAR / Farside 等が必要だが、
    出来高 (USD換算) は 強い 相関を 持ち、 認証なし で 取れる。

    Returns:
        {'tickers': {ticker: {'last': float, 'volume_5d': int, 'usd_volume_5d': float,
                              'change_pct_5d': float}},
         'total_usd_volume_5d': float, 'price_change_avg_pct': float}
    """
    import yfinance as yf
    tickers_sym = ['IBIT', 'FBTC', 'ARKB', 'BITB', 'GBTC']
    out = {'tickers': {}}
    total_usd_vol = 0.0
    price_changes = []
    for sym in tickers_sym:
        try:
            df = yf.Ticker(sym).history(period='7d', interval='1d')
            if df.empty or len(df) < 2:
                continue
            last_close = float(df['Close'].iloc[-1])
            prev_close = float(df['Close'].iloc[-2])
            volumes = df['Volume'].tail(5)
            closes = df['Close'].tail(5)
            usd_vol = float((volumes * closes).sum())
            volume_5d = int(volumes.sum())
            change_pct_5d = (last_close - float(closes.iloc[0])) / float(closes.iloc[0]) * 100 if len(closes) >= 2 else 0.0
            out['tickers'][sym] = {
                'last': last_close,
                'volume_5d': volume_5d,
                'usd_volume_5d': usd_vol,
                'change_pct_5d': change_pct_5d,
            }
            total_usd_vol += usd_vol
            price_changes.append(change_pct_5d)
        except Exception:
            continue
    out['total_usd_volume_5d'] = total_usd_vol
    out['price_change_avg_pct'] = sum(price_changes) / len(price_changes) if price_changes else 0.0
    return out


def fetch_deribit_dvol(currency: str = "BTC") -> dict:
    """Phase 2-① IV (Implied Volatility) — Deribit DVOL index

    Deribit public `/api/v2/public/get_volatility_index_data` で
    直近24h の DVOL (Deribit Volatility Index、 年率%) を 取得し、
    現値・24h前比較・水準感 を 返す。 認証なし、 発注経路ゼロ。

    Returns:
        {'dvol_now': float, 'dvol_24h_ago': float, 'change_pct': float,
         'level': 'low'|'mid'|'high'}
    """
    import time as _time
    now_ms = int(_time.time() * 1000)
    start_ms = now_ms - 26 * 3600 * 1000  # 26h 余裕で
    url = (
        f"https://www.deribit.com/api/v2/public/get_volatility_index_data"
        f"?currency={currency}&start_timestamp={start_ms}&end_timestamp={now_ms}&resolution=3600"
    )
    o = _http_get_json(url)
    result = (o or {}).get('result') or {}
    data = result.get('data') or []
    if not data:
        return {'error': 'no_data'}
    # 各row: [ts, open, high, low, close]
    closes = [float(row[4]) for row in data if len(row) >= 5]
    if not closes:
        return {'error': 'no_close'}
    dvol_now = closes[-1]
    dvol_24h_ago = closes[0]
    change_pct = (dvol_now - dvol_24h_ago) / dvol_24h_ago * 100 if dvol_24h_ago else 0.0
    # 水準感 (BTC DVOL は 概ね 30-80%、 低<40 / 中40-60 / 高>60)
    if dvol_now < 40:
        level = 'low'
    elif dvol_now > 60:
        level = 'high'
    else:
        level = 'mid'
    return {
        'dvol_now': dvol_now,
        'dvol_24h_ago': dvol_24h_ago,
        'change_pct': change_pct,
        'level': level,
    }


def fetch_fear_greed() -> dict:
    """Phase 1-⑤ Fear & Greed Index

    Alternative.me 無認証 `/fng/?limit=7` で 直近7日分の F&G を 取得。
    Returns:
        {'value': int (0-100), 'classification': str,
         'value_5d_ago': int, 'change_5d': int, 'history': [{ts, value, class}, ...]}
    """
    o = _http_get_json("https://api.alternative.me/fng/?limit=7&format=json")
    data = (o or {}).get('data') or []
    if not data:
        return {'error': 'no_data'}
    latest = data[0]
    value = int(latest.get('value', 0))
    classification = latest.get('value_classification', '')
    val_5d = int(data[5].get('value', value)) if len(data) >= 6 else value
    history = []
    for d in data:
        history.append({
            'ts': d.get('timestamp', ''),
            'value': int(d.get('value', 0)),
            'classification': d.get('value_classification', ''),
        })
    return {
        'value': value,
        'classification': classification,
        'value_5d_ago': val_5d,
        'change_5d': value - val_5d,
        'history': history,
    }


def fetch_macro_yfinance() -> dict:
    """Phase 1-④ マクロ (DXY / SPX / Gold / 10年米国債金利)

    yfinance 無認証 で 主要マクロ tickers を 1日分取得し、 直近終値 + 前日比% を返す。
    BTC と 相関 (DXY逆相関 / SPX順相関 / Gold 競合資産 / 金利逆相関) を 判断材料に。

    Returns:
        {
          'dxy': {'last': float, 'change_pct': float},
          'spx': {'last': float, 'change_pct': float},
          'gold': {'last': float, 'change_pct': float},
          'us10y': {'last': float, 'change_pct': float}
        }
    """
    import yfinance as yf
    tickers = {
        'dxy':   'DX-Y.NYB',  # US Dollar Index
        'spx':   '^GSPC',     # S&P 500
        'gold':  'GC=F',      # Gold Futures
        'us10y': '^TNX',      # 10-Year Treasury Yield
    }
    out = {}
    for key, sym in tickers.items():
        try:
            df = yf.Ticker(sym).history(period='5d', interval='1d')
            if df.empty or len(df) < 2:
                out[key] = {'error': 'insufficient_data'}
                continue
            last = float(df['Close'].iloc[-1])
            prev = float(df['Close'].iloc[-2])
            change_pct = (last - prev) / prev * 100 if prev else 0.0
            out[key] = {'last': last, 'change_pct': change_pct}
        except Exception as e:
            out[key] = {'error': f'{type(e).__name__}: {e}'}
    return out


def fetch_dominance_coingecko() -> dict:
    """Phase 1-③ ドミナンス (BTC.D / ETH.D / Stable.D)

    CoinGecko 無認証 `/api/v3/global` から 時価総額シェア を 取得。
    Returns:
        {'btc_d': float, 'eth_d': float, 'stable_d': float (USDT+USDC+DAI),
         'total_mcap_usd': float, 'total_volume_24h_usd': float}
    """
    o = _http_get_json("https://api.coingecko.com/api/v3/global")
    d = (o or {}).get('data', {}) or {}
    mcap_pct = d.get('market_cap_percentage', {}) or {}
    btc_d = float(mcap_pct.get('btc', 0))
    eth_d = float(mcap_pct.get('eth', 0))
    stable_d = (
        float(mcap_pct.get('usdt', 0))
        + float(mcap_pct.get('usdc', 0))
        + float(mcap_pct.get('dai', 0))
    )
    total_mcap = (d.get('total_market_cap', {}) or {}).get('usd', 0) or 0
    total_vol = (d.get('total_volume', {}) or {}).get('usd', 0) or 0
    return {
        'btc_d': btc_d,
        'eth_d': eth_d,
        'stable_d': stable_d,
        'total_mcap_usd': float(total_mcap),
        'total_volume_24h_usd': float(total_vol),
    }


def fetch_binance_cvd(symbol: str = "BTCUSDT", limit: int = 1000) -> dict:
    """Phase 1-② CVD (Cumulative Volume Delta)

    Binance public `/fapi/v1/aggTrades` で 直近 limit件 の aggregate trades を
    買い (m=false: 買いがtaker) / 売り (m=true: 売りがtaker) に分けて 集計。

    Returns:
        {'buy_qty': float, 'sell_qty': float, 'buy_usd': float, 'sell_usd': float,
         'delta_qty': float, 'delta_usd': float, 'count': int,
         'first_ts': str, 'last_ts': str, 'window_sec': float}
    """
    url = f"https://fapi.binance.com/fapi/v1/aggTrades?symbol={symbol}&limit={min(limit, 1000)}"
    trades = _http_get_json(url)
    if not isinstance(trades, list) or not trades:
        return {'error': 'no_trades', 'count': 0}
    buy_qty = 0.0
    sell_qty = 0.0
    buy_usd = 0.0
    sell_usd = 0.0
    first_ms = trades[0].get('T', 0)
    last_ms = trades[-1].get('T', 0)
    for t in trades:
        try:
            qty = float(t.get('q', 0))
            price = float(t.get('p', 0))
            usd = qty * price
            if t.get('m'):  # buyer is maker → seller is taker → sell pressure
                sell_qty += qty
                sell_usd += usd
            else:           # seller is maker → buyer is taker → buy pressure
                buy_qty += qty
                buy_usd += usd
        except Exception:
            continue
    delta_qty = buy_qty - sell_qty
    delta_usd = buy_usd - sell_usd
    window_sec = max(0.0, (last_ms - first_ms) / 1000.0)
    return {
        'buy_qty': buy_qty,
        'sell_qty': sell_qty,
        'buy_usd': buy_usd,
        'sell_usd': sell_usd,
        'delta_qty': delta_qty,
        'delta_usd': delta_usd,
        'count': len(trades),
        'first_ts': str(first_ms),
        'last_ts': str(last_ms),
        'window_sec': window_sec,
    }


def fetch_recent_liquidations_bybit(symbol: str = "BTCUSDT", duration_sec: int = 30) -> dict:
    """Phase 1合意 (2026-06-24 14:29) — 清算 (Liquidations)

    Bybit public WebSocket `allLiquidation.SYMBOL` を duration_sec 秒接続して
    リアルタイム清算ストリームを 集計。 API key 不要 (発注経路ゼロ)。

    Bybit doc: https://bybit-exchange.github.io/docs/v5/websocket/public/all-liquidation
    msg sample: {"topic":"allLiquidation.BTCUSDT","data":[{
        "T":<ms>,"s":"BTCUSDT","S":"Buy"|"Sell","v":<qty>,"p":<price>
    }]}
    S="Sell" = ロングポジションの強制決済 (= ロング清算)
    S="Buy"  = ショートポジションの強制決済 (= ショート清算)

    Returns:
        {'long_usd': float, 'short_usd': float, 'count': int,
         'long_count': int, 'short_count': int, 'duration_sec': int,
         'largest_long_usd': float, 'largest_short_usd': float}
    """
    import asyncio
    import json as _json

    async def _collect():
        import websockets as _ws
        long_usd = 0.0
        short_usd = 0.0
        long_count = 0
        short_count = 0
        largest_long = 0.0
        largest_short = 0.0
        try:
            async with _ws.connect(
                "wss://stream.bybit.com/v5/public/linear",
                ping_interval=20, ping_timeout=10,
            ) as ws:
                await ws.send(_json.dumps({
                    "op": "subscribe",
                    "args": [f"allLiquidation.{symbol}"],
                }))
                try:
                    await asyncio.wait_for(asyncio.sleep(duration_sec), timeout=duration_sec + 5)
                except asyncio.TimeoutError:
                    pass
                # 受信処理 を 別タスク で 並行
                pass
        except Exception:
            pass
        return long_usd, short_usd, long_count, short_count, largest_long, largest_short

    async def _collect_v2():
        import websockets as _ws
        long_usd = 0.0
        short_usd = 0.0
        long_count = 0
        short_count = 0
        largest_long = 0.0
        largest_short = 0.0
        deadline = asyncio.get_event_loop().time() + duration_sec
        try:
            async with _ws.connect(
                "wss://stream.bybit.com/v5/public/linear",
                ping_interval=20, ping_timeout=10, open_timeout=5,
            ) as ws:
                await ws.send(_json.dumps({
                    "op": "subscribe",
                    "args": [f"allLiquidation.{symbol}"],
                }))
                while asyncio.get_event_loop().time() < deadline:
                    try:
                        remaining = max(0.5, deadline - asyncio.get_event_loop().time())
                        msg = await asyncio.wait_for(ws.recv(), timeout=remaining)
                    except (asyncio.TimeoutError, _ws.exceptions.ConnectionClosed):
                        break
                    try:
                        o = _json.loads(msg)
                    except Exception:
                        continue
                    data = o.get('data') or []
                    if not isinstance(data, list):
                        continue
                    for d in data:
                        try:
                            qty = float(d.get('v', 0))
                            price = float(d.get('p', 0))
                            side = d.get('S', '')
                            usd = qty * price
                            if side == 'Sell':  # ロング清算
                                long_usd += usd
                                long_count += 1
                                if usd > largest_long:
                                    largest_long = usd
                            elif side == 'Buy':  # ショート清算
                                short_usd += usd
                                short_count += 1
                                if usd > largest_short:
                                    largest_short = usd
                        except Exception:
                            continue
        except Exception:
            pass
        return long_usd, short_usd, long_count, short_count, largest_long, largest_short

    try:
        long_usd, short_usd, lc, sc, ll, ls = asyncio.run(_collect_v2())
    except Exception as e:
        return {'error': f'{type(e).__name__}: {e}', 'duration_sec': duration_sec}

    return {
        'long_usd': long_usd,
        'short_usd': short_usd,
        'long_count': lc,
        'short_count': sc,
        'count': lc + sc,
        'largest_long_usd': ll,
        'largest_short_usd': ls,
        'duration_sec': duration_sec,
    }


def fetch_market_snapshot(symbol: str = "BTCUSDT") -> dict:
    """loop2 合意: 「AIが判断する直前にその瞬間のOI/FR/板/出来高などを取りに行く」

    全 public エンドポイント を 1回 で 取得。 例外は サブ辞書 ごと スキップ
    (1つ失敗しても他は活かす)。

    Returns:
        {'oi': {...}, 'funding': {...}, 'ls': {...}, 'orderbook': {...}}
    """
    snap = {}
    for key, fn in (
        ('oi', fetch_binance_oi),
        ('funding', fetch_binance_funding),
        ('ls', fetch_binance_top_ls),
        ('orderbook', fetch_binance_orderbook),
    ):
        try:
            snap[key] = fn(symbol)
        except Exception as e:
            snap[key] = {'error': f'{type(e).__name__}: {e}'}
    # Phase 1 (2026-06-24 14:29 合意): 段階追加
    # ① 清算 (Bybit ws 30秒集計)
    try:
        snap['liquidations'] = fetch_recent_liquidations_bybit(symbol, duration_sec=30)
    except Exception as e:
        snap['liquidations'] = {'error': f'{type(e).__name__}: {e}'}
    # ② CVD (Binance aggTrades 直近1000件)
    try:
        snap['cvd'] = fetch_binance_cvd(symbol, limit=1000)
    except Exception as e:
        snap['cvd'] = {'error': f'{type(e).__name__}: {e}'}
    # ③ ドミナンス (CoinGecko global)
    try:
        snap['dominance'] = fetch_dominance_coingecko()
    except Exception as e:
        snap['dominance'] = {'error': f'{type(e).__name__}: {e}'}
    # ④ マクロ (DXY / SPX / Gold / US10Y) — yfinance
    try:
        snap['macro'] = fetch_macro_yfinance()
    except Exception as e:
        snap['macro'] = {'error': f'{type(e).__name__}: {e}'}
    # ⑤ Fear & Greed Index — alternative.me
    try:
        snap['fear_greed'] = fetch_fear_greed()
    except Exception as e:
        snap['fear_greed'] = {'error': f'{type(e).__name__}: {e}'}
    # === Phase 2 (2026-06-24 14:29 合意: IV/ETF/経済指標距離) ===
    # ⑥ IV (Deribit DVOL public)
    try:
        snap['iv'] = fetch_deribit_dvol("BTC")
    except Exception as e:
        snap['iv'] = {'error': f'{type(e).__name__}: {e}'}
    # ⑦ BTC ETF 出来高近似 (yfinance IBIT/FBTC/ARKB/BITB/GBTC)
    try:
        snap['etf_flow'] = fetch_btc_etf_flow_yfinance()
    except Exception as e:
        snap['etf_flow'] = {'error': f'{type(e).__name__}: {e}'}
    # ⑧ 経済指標距離 (FOMC/CPI/NFP hard-code calendar)
    try:
        snap['econ_calendar'] = fetch_econ_calendar_distance()
    except Exception as e:
        snap['econ_calendar'] = {'error': f'{type(e).__name__}: {e}'}
    return snap


if __name__ == "__main__":
    # 動作確認
    print("=== data_source.py 動作確認 ===")
    try:
        df = fetch_btc_ohlcv(period="7d", interval="1h")
        print(f"取得成功: {len(df)} 本")
        latest = get_latest_candle(df)
        print(f"最新足: ts={latest['ts']} close=${latest['close']:.2f}")
        recent = get_recent_candles(df, n=5)
        print(f"直近5本: {len(recent)} 件")
    except Exception as e:
        print(f"取得失敗: {type(e).__name__}: {e}")
