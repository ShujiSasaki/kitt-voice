"""BTC局面検出: trend / range / rally / crash

3者合意 (2026-06-24) のdanjer手法に近い局面判定。
ロジック:
- rally: 直近4hの変動率が大きく、 価格が +5%以上 / 6h
- crash: 同条件で -5%以下 / 6h
- trend: 4h EMA20 > 4h EMA50 (上昇) or 逆 (下降)
- range: 上記以外
"""
from __future__ import annotations


def _ema(values: list[float], period: int) -> float:
    """指数移動平均 (Exponential Moving Average)"""
    if len(values) < period:
        return sum(values) / len(values) if values else 0.0
    alpha = 2.0 / (period + 1)
    ema = values[0]
    for v in values[1:]:
        ema = alpha * v + (1 - alpha) * ema
    return ema


def _atr(candles: list[dict], period: int = 14) -> float:
    """Average True Range (ボラティリティ)"""
    if len(candles) < 2:
        return 0.0
    trs = []
    for i in range(1, len(candles)):
        h = candles[i]['high']
        l = candles[i]['low']
        prev_close = candles[i-1]['close']
        tr = max(h - l, abs(h - prev_close), abs(l - prev_close))
        trs.append(tr)
    if not trs:
        return 0.0
    n = min(period, len(trs))
    return sum(trs[-n:]) / n


def _price_change_pct(candles: list[dict], hours: int) -> float:
    """直近 N時間 の価格変動率 (%)"""
    if len(candles) < hours + 1:
        hours = len(candles) - 1
    if hours <= 0:
        return 0.0
    start = candles[-hours - 1]['close']
    end = candles[-1]['close']
    return (end - start) / start * 100


def detect_regime(candles: list[dict]) -> str:
    """局面検出

    Args:
        candles: list[dict] (最低30本以上推奨、 1時間足)

    Returns:
        'trend' | 'range' | 'rally' | 'crash'
    """
    if len(candles) < 20:
        return 'range'  # データ不足は range 扱い

    # 直近の価格変動率 (6h)
    change_6h = _price_change_pct(candles, hours=6)

    # ATR (直近4h vs 全体)
    recent_atr = _atr(candles[-4:], period=4)
    long_atr = _atr(candles, period=min(30 * 24, len(candles)))  # 30日相当 or 全体
    atr_ratio = recent_atr / long_atr if long_atr > 0 else 1.0

    # rally: 急騰 (+5%以上 / 6h、 ATR増大)
    if change_6h >= 5.0 and atr_ratio > 2.0:
        return 'rally'
    # crash: 急落 (-5%以下 / 6h、 ATR増大)
    if change_6h <= -5.0 and atr_ratio > 2.0:
        return 'crash'

    # EMA20 vs EMA50 (トレンド判定)
    closes = [c['close'] for c in candles]
    ema20 = _ema(closes, 20)
    ema50 = _ema(closes, 50) if len(closes) >= 50 else ema20
    diff_pct = (ema20 - ema50) / ema50 * 100 if ema50 > 0 else 0

    if abs(diff_pct) >= 1.0:
        return 'trend'  # 上昇 or 下降トレンド (どちらも trend として扱う)

    return 'range'


def extract_materials(candles: list[dict], regime: str) -> list[str]:
    """局面に応じた「材料」リスト生成 (LoRA入力用)

    danjer学習データの format に合わせる:
    「【今わたし(danjer)が見ている材料】 - <m1> - <m2> ...」
    """
    if len(candles) < 5:
        return ['データ不足']

    latest = candles[-1]
    close = latest['close']
    high = latest['high']
    low = latest['low']
    volume = latest['volume']

    # 過去24h平均volume
    n = min(24, len(candles))
    avg_volume = sum(c['volume'] for c in candles[-n:]) / n
    volume_ratio = volume / avg_volume if avg_volume > 0 else 1.0

    # 過去 ATR
    atr = _atr(candles, period=14)

    materials = []

    if regime == 'rally':
        materials.append('急騰中')
        if volume_ratio > 1.5:
            materials.append('出来高伴う')
        else:
            materials.append('出来高伴わず')
        materials.append('損切根拠の探索')
    elif regime == 'crash':
        materials.append('暴落中')
        if volume_ratio > 1.5:
            materials.append('出来高急増')
        materials.append('反発取れる背の検討')
    elif regime == 'trend':
        materials.append('トレンド継続')
        change_6h = _price_change_pct(candles, hours=6)
        if change_6h > 0:
            materials.append('上昇継続')
        else:
            materials.append('下降継続')
        materials.append('押し目/戻り高値の確認')
    else:  # range
        materials.append('レンジ相場')
        materials.append('上下限の確認')
        materials.append('ブレイクの根拠待ち')

    return materials


if __name__ == "__main__":
    # 動作確認 (yfinance使う)
    print("=== regime_detector.py 動作確認 ===")
    try:
        from data_source import fetch_btc_ohlcv, get_recent_candles
        df = fetch_btc_ohlcv(period="60d", interval="1h")
        candles = get_recent_candles(df, n=240)  # 10日分
        regime = detect_regime(candles)
        materials = extract_materials(candles, regime)
        print(f"判定: regime={regime}")
        print(f"材料: {materials}")
        print(f"最新close: ${candles[-1]['close']:.2f}")
    except Exception as e:
        print(f"失敗: {type(e).__name__}: {e}")
