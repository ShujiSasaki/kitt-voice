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
