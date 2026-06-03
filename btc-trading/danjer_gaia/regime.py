"""
Project danjer-GAIA — Regime Detection (相場の4つの顔)
================================================================
3者会議 Phase 1 合意:
- レジーム判定 = 2x2 (ATR × Slope)
- 動的閾値: ローリング過去30日 (or 90日) パーセンタイル (Appendix-B)
- 4象限: 凪×上昇 / 嵐×上昇 / 凪×下降 / 嵐×下降
- HMM/Bayesian Change Point Detection は Phase 2以降

Gemini Round 9 「致命的脆弱性 2: ATR/Slopeの境界線を静的固定すると、
BTC価格が10倍になった瞬間に意味を成さない」 → ローリング・パーセンタイルで対応
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal, Optional
import math


RegimeLabel = Literal[
    "calm_up",      # 凪 × 上昇 (慎重ロング)
    "calm_down",    # 凪 × 下降 (反転待ち)
    "storm_up",     # 嵐 × 上昇 (一気踏み込み or 警戒)
    "storm_down",   # 嵐 × 下降 (退避 or 即ショート)
    "unknown",      # データ不足
]


@dataclass
class OHLCV:
    """1ローソク足"""
    timestamp: int   # epoch ms (or epoch s)
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class RegimeResult:
    label: RegimeLabel
    atr: float
    slope: float
    atr_percentile: float   # 0.0-1.0
    slope_percentile: float # 0.0-1.0
    high_vol_threshold: float
    up_trend_threshold: float
    down_trend_threshold: float
    samples_used: int


def true_range(prev_close: float, h: float, l: float) -> float:
    """1本のTrue Range"""
    return max(h - l, abs(h - prev_close), abs(l - prev_close))


def calc_atr(candles: list[OHLCV], period: int = 14) -> float:
    """
    ATR (Wilder's smoothing)
    candles: 時系列順 (古い→新しい)、 最低 period+1 件必要
    """
    if len(candles) < period + 1:
        return float('nan')
    trs = []
    for i in range(1, len(candles)):
        trs.append(true_range(candles[i-1].close, candles[i].high, candles[i].low))
    # 単純平均で初期化
    atr = sum(trs[:period]) / period
    # Wilder smoothing で更新
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return atr


def calc_slope(candles: list[OHLCV], window: int = 20) -> float:
    """
    Linear Regression Slope (最小二乗法)
    candles: 時系列順、 直近 window 本のclose で傾き計算

    Returns: 1本あたりの close 変化量 (絶対値、 価格スケール)
    """
    if len(candles) < window:
        return float('nan')
    use = candles[-window:]
    xs = list(range(window))
    ys = [c.close for c in use]
    n = window
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(n))
    den = sum((xs[i] - mean_x) ** 2 for i in range(n))
    if den == 0:
        return 0.0
    return num / den


def normalized_slope(slope: float, mean_close: float) -> float:
    """
    Slope を価格に対する比率に正規化 (BTC価格スケールの違いを吸収)
    Returns: slope / mean_close (1本あたりの変化率)
    """
    if mean_close == 0 or math.isnan(slope):
        return float('nan')
    return slope / mean_close


def log_return_slope(candles: list[OHLCV], window: int = 20) -> float:
    """
    Log return slope: (log(close末) - log(close始)) / window
    純粋線形上昇でも価格スケールに依存しない傾き率
    """
    if len(candles) < window:
        return float('nan')
    use = candles[-window:]
    start_close = use[0].close
    end_close = use[-1].close
    if start_close <= 0 or end_close <= 0:
        return float('nan')
    return (math.log(end_close) - math.log(start_close)) / window


def percentile(values: list[float], v: float) -> float:
    """
    v が values の中で何パーセンタイルにあたるか (0.0-1.0)
    NaN は除外
    """
    clean = [x for x in values if not (isinstance(x, float) and math.isnan(x))]
    if not clean:
        return float('nan')
    if v <= min(clean):
        return 0.0
    if v >= max(clean):
        return 1.0
    sorted_vals = sorted(clean)
    n = len(sorted_vals)
    # 線形補間
    for i, sv in enumerate(sorted_vals):
        if sv >= v:
            # rank: i / (n-1)
            return i / max(n - 1, 1)
    return 1.0


def detect_regime(
    candles: list[OHLCV],
    atr_period: int = 14,
    slope_window: int = 20,
    rolling_lookback_bars: int = 720,  # 例: 1h × 720 = 30日
    high_vol_pct: float = 0.67,         # 上位33%が「嵐」
    up_trend_pct: float = 0.67,         # 上位33%が「上昇」
    down_trend_pct: float = 0.33,       # 下位33%が「下降」
) -> RegimeResult:
    """
    現在のレジームを4分類で判定。

    動的閾値: 直近 rolling_lookback_bars 本のATR/Slopeから
              high_vol_pct (デフォルト67%)、up/down_trend_pct でカット

    Args:
        candles: 時系列順 (古い→新しい)、 最低 rolling_lookback_bars+atr_period+slope_window 推奨
        atr_period: ATR 計算期間
        slope_window: Slope 回帰の窓
        rolling_lookback_bars: 動的閾値計算のlookback
        high_vol_pct: ボラ高判定の percentile cutoff
        up_trend_pct / down_trend_pct: トレンド判定 cutoff

    Returns: RegimeResult
    """
    if len(candles) < max(rolling_lookback_bars, atr_period + 1, slope_window):
        return RegimeResult(
            label="unknown", atr=float('nan'), slope=float('nan'),
            atr_percentile=float('nan'), slope_percentile=float('nan'),
            high_vol_threshold=float('nan'), up_trend_threshold=float('nan'),
            down_trend_threshold=float('nan'), samples_used=len(candles),
        )

    # ローリング窓内で各バーのATR/Slopeを計算
    historical_atrs = []
    historical_norm_slopes = []
    start = max(0, len(candles) - rolling_lookback_bars)
    end = len(candles)

    # 計算高速化のため、 一定間隔でサンプリング (rolling_lookback_bars 全件は重い)
    # 各 step バーごとに ATR/Slope を求める
    step = max(1, rolling_lookback_bars // 200)  # 約200サンプル
    for i in range(start + max(atr_period, slope_window), end, step):
        sub = candles[max(0, i - max(atr_period, slope_window) - 1):i + 1]
        a = calc_atr(sub, atr_period)
        # ATR も価格で正規化 (atr / mean_close = 相対ボラ)
        mean_close = sum(c.close for c in sub[-slope_window:]) / slope_window
        a_rel = a / mean_close if mean_close > 0 and not math.isnan(a) else float('nan')
        # Log return slope: 価格スケール非依存
        ls = log_return_slope(sub, slope_window)
        if not math.isnan(a_rel):
            historical_atrs.append(a_rel)
        if not math.isnan(ls):
            historical_norm_slopes.append(ls)

    # 動的閾値
    if not historical_atrs or not historical_norm_slopes:
        return RegimeResult(
            label="unknown", atr=float('nan'), slope=float('nan'),
            atr_percentile=float('nan'), slope_percentile=float('nan'),
            high_vol_threshold=float('nan'), up_trend_threshold=float('nan'),
            down_trend_threshold=float('nan'), samples_used=len(candles),
        )

    sorted_atrs = sorted(historical_atrs)
    sorted_slopes = sorted(historical_norm_slopes)

    def at_pct(sorted_list, p):
        if not sorted_list:
            return float('nan')
        idx = int(len(sorted_list) * p)
        idx = max(0, min(idx, len(sorted_list) - 1))
        return sorted_list[idx]

    high_vol_threshold = at_pct(sorted_atrs, high_vol_pct)
    # Slope は 0基準 + 過去分布の標準偏差で neutral帯を作る
    # 純粋上昇トレンドでも slope > 0 で「up」と判定できるように
    n_s = len(sorted_slopes)
    mean_slope = sum(sorted_slopes) / n_s if n_s else 0.0
    var_slope = sum((s - mean_slope) ** 2 for s in sorted_slopes) / n_s if n_s else 0.0
    std_slope = math.sqrt(var_slope)
    # neutral帯 = ±0.25σ。 これ以上で up/down 判定
    neutral_band = std_slope * 0.25
    up_trend_threshold = neutral_band
    down_trend_threshold = -neutral_band

    # 現在 (直近) のATR/Slope (歴史と同じ正規化)
    current_atr_raw = calc_atr(candles[-(atr_period + 1):], atr_period)
    current_mean_close = sum(c.close for c in candles[-slope_window:]) / slope_window
    current_atr = current_atr_raw / current_mean_close if current_mean_close > 0 and not math.isnan(current_atr_raw) else float('nan')
    current_norm_slope = log_return_slope(candles, slope_window)

    # 4象限分類
    is_high_vol = current_atr > high_vol_threshold if not math.isnan(current_atr) else False
    if not math.isnan(current_norm_slope):
        if current_norm_slope > up_trend_threshold:
            trend = "up"
        elif current_norm_slope < down_trend_threshold:
            trend = "down"
        else:
            trend = "neutral"
    else:
        trend = "neutral"

    if trend == "neutral":
        # 横ばいは別途扱い (label にはなく、 慎重判定)
        label: RegimeLabel = "calm_down" if not is_high_vol else "storm_down"  # 保守側に倒す
    elif trend == "up" and is_high_vol:
        label = "storm_up"
    elif trend == "up":
        label = "calm_up"
    elif trend == "down" and is_high_vol:
        label = "storm_down"
    else:
        label = "calm_down"

    return RegimeResult(
        label=label,
        atr=current_atr,
        slope=current_norm_slope,
        atr_percentile=percentile(historical_atrs, current_atr),
        slope_percentile=percentile(historical_norm_slopes, current_norm_slope),
        high_vol_threshold=high_vol_threshold,
        up_trend_threshold=up_trend_threshold,
        down_trend_threshold=down_trend_threshold,
        samples_used=len(candles),
    )


REGIME_TO_LEVERAGE_HINT = {
    "calm_up":    {"max_lev": 3.0, "stance": "慎重ロング — 小ロット+トレイリングTP"},
    "storm_up":   {"max_lev": 4.0, "stance": "一気に踏み込む — Half-Kelly上限フル"},
    "calm_down":  {"max_lev": 1.5, "stance": "様子見 or 小ロット — 反転待ち"},
    "storm_down": {"max_lev": 4.0, "stance": "退避 or 即ショート — 高速SLで防衛"},
    "unknown":    {"max_lev": 0.0, "stance": "見送り — データ不足"},
}


def regime_to_hint(label: RegimeLabel) -> dict:
    """レジームから推奨レバ・スタンスを取得"""
    return REGIME_TO_LEVERAGE_HINT.get(label, REGIME_TO_LEVERAGE_HINT["unknown"])
