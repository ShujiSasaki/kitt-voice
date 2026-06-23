"""評価指標 (3層): 守り + 攻め + 臆病チェック

3者合意 (2026-06-24 06:41 btc部屋) の合意通り、 3層の指標を計算:
- 守り層: 危ない場面で「やる」、 強制ストップバグ、 ループ、 崩壊
- 攻め層: 仮想損益 1h/4h/24h、 最大上昇/逆行幅、 勝率、 平均RR
- 臆病チェック: no_trade率、 強制ストップ発火率、 平均応答長
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

HERE = Path(__file__).parent.parent


def _load_config_value(key: str, default=None):
    config_path = HERE / "config.yml"
    if not config_path.exists():
        return default
    for line in config_path.read_text(encoding='utf-8').splitlines():
        line_clean = line.split('#')[0].strip()
        if line_clean.startswith(f'{key}:'):
            return line_clean.split(':', 1)[1].strip().strip('"\'')
    return default


def load_signals(model_version: str) -> list[dict]:
    log_file = HERE / "logs" / f"signals_{model_version}.jsonl"
    if not log_file.exists():
        return []
    return [json.loads(l) for l in log_file.read_text(encoding='utf-8').splitlines() if l.strip()]


def load_labels(model_version: str) -> dict[str, dict]:
    label_file = HERE / "eval" / f"labels_{model_version}.jsonl"
    if not label_file.exists():
        return {}
    out = {}
    for line in label_file.read_text(encoding='utf-8').splitlines():
        if line.strip():
            d = json.loads(line)
            out[d.get('signal_ts', '')] = d
    return out


# ===== 守り層 =====

def metrics_defense(signals: list[dict], labels: dict[str, dict]) -> dict:
    """守り層指標 (退場しないための土台)"""
    total = len(signals)
    if total == 0:
        return {'note': 'signals empty'}

    # ラベル付き件数
    labeled = [s for s in signals if s.get('ts', '') in labels]
    labeled_count = len(labeled)

    # 各失敗カテゴリ件数 (ラベル付きから)
    fail_counts = {i: 0 for i in range(1, 9)}
    for s in labeled:
        lbl = labels.get(s.get('ts', ''), {})
        for l in lbl.get('labels', []):
            if l in fail_counts:
                fail_counts[l] += 1

    # 自動検出: 内容崩壊 (応答に9連続/中国語片/空)
    auto_collapse = 0
    auto_loop = 0
    for s in signals:
        response = s.get('response', '')
        if not response or len(response) < 10:
            auto_collapse += 1
        elif re.search(r'9{15,}|1{15,}|0{15,}', response):
            auto_collapse += 1
        elif '单选字典' in response or 'is a 1.' in response:
            auto_collapse += 1
        elif re.search(r'(.{4,30})\1{4,}', response):
            auto_loop += 1

    return {
        'total': total,
        'labeled': labeled_count,
        'unlabeled': total - labeled_count,
        # 合意基準 (0件が必須)
        'dangerous_yarei_count': fail_counts[1],   # 危ない場面で「やる」
        'stop_rule_bugs': fail_counts[2],          # 強制ストップ7条件のバグ
        'auto_loop_detected': auto_loop,           # 自動検出: 同フレーズ無限ループ
        'auto_collapse_detected': auto_collapse,   # 自動検出: 内容崩壊
        'manual_loop_labeled': fail_counts[3],
        'manual_collapse_labeled': fail_counts[4],
        # 判定
        'defense_passed': (
            fail_counts[1] == 0 and fail_counts[2] == 0 and
            auto_loop == 0 and auto_collapse == 0 and
            fail_counts[3] == 0 and fail_counts[4] == 0
        ),
    }


# ===== 攻め層 =====

def fetch_price_after(ts_str: str, hours: int) -> Optional[float]:
    """信号時刻から N時間後の BTC価格を yfinance で取得

    Returns:
        N時間後の終値 (float)。 未到達 (未来) or 取得失敗時は None
    """
    try:
        from datetime import datetime, timezone
        from data_source import fetch_btc_ohlcv
        import pandas as pd

        signal_dt = datetime.fromisoformat(ts_str.replace('+09:00', '+09:00'))
        target_dt = signal_dt + pd.Timedelta(hours=hours)
        now = datetime.now(tz=signal_dt.tzinfo)
        if target_dt > now:
            return None  # まだ未到達

        # 必要な期間をfetch
        period_days = max(7, hours // 24 + 7)
        df = fetch_btc_ohlcv(period=f"{period_days}d", interval="1h")
        if df.empty:
            return None
        # signal時刻に最も近い行を探す
        target_ts = target_dt.tz_convert(df.index.tz)
        idx = df.index.get_indexer([target_ts], method='nearest')[0]
        return float(df.iloc[idx]['Close'])
    except Exception:
        return None


def metrics_offense(signals: list[dict]) -> dict:
    """攻め層指標 (とことん上手くなるためのゴール)

    仮想損益 1h/4h/24h は、 各信号時点の price と N時間後の price の差で計算。
    long → (after - before)、 short → (before - after)。
    no_trade / force_stopped は損益0。
    """
    total = len(signals)
    if total == 0:
        return {'note': 'signals empty'}

    horizons = [1, 4, 24]
    pnl_results = {h: {'sum': 0.0, 'wins': 0, 'losses': 0, 'evaluated': 0,
                       'max_run_up': 0.0, 'max_drawdown': 0.0}
                   for h in horizons}

    for s in signals:
        sig = s.get('signal', {}).get('signal')
        if sig in ('no_trade', 'force_stopped'):
            continue  # PnL 0
        entry_price = s.get('btc_price', 0.0)
        if entry_price <= 0:
            continue
        ts = s.get('ts', '')

        for h in horizons:
            after_price = fetch_price_after(ts, h)
            if after_price is None:
                continue
            if sig == 'long':
                pnl = after_price - entry_price
            elif sig == 'short':
                pnl = entry_price - after_price
            else:
                continue
            pnl_results[h]['sum'] += pnl
            pnl_results[h]['evaluated'] += 1
            if pnl > 0:
                pnl_results[h]['wins'] += 1
                if pnl > pnl_results[h]['max_run_up']:
                    pnl_results[h]['max_run_up'] = pnl
            elif pnl < 0:
                pnl_results[h]['losses'] += 1
                if pnl < pnl_results[h]['max_drawdown']:
                    pnl_results[h]['max_drawdown'] = pnl

    # 勝率 (24h基準)
    win_rate_24h = 0.0
    if pnl_results[24]['evaluated'] > 0:
        win_rate_24h = pnl_results[24]['wins'] / pnl_results[24]['evaluated']

    return {
        'total': total,
        'pnl_1h': pnl_results[1],
        'pnl_4h': pnl_results[4],
        'pnl_24h': pnl_results[24],
        'win_rate_24h': win_rate_24h,
    }


# ===== 臆病チェック =====

def metrics_caution(signals: list[dict]) -> dict:
    """臆病チェック (「何もしないAIになってないか」)"""
    total = len(signals)
    if total == 0:
        return {'note': 'signals empty'}

    no_trade_count = sum(1 for s in signals if s.get('signal', {}).get('signal') == 'no_trade')
    force_stopped_count = sum(1 for s in signals if s.get('signal', {}).get('signal') == 'force_stopped')
    response_lengths = [len(s.get('response', '')) for s in signals if s.get('response')]
    avg_response_length = sum(response_lengths) / len(response_lengths) if response_lengths else 0

    no_trade_rate = no_trade_count / total if total > 0 else 0
    force_stopped_rate = force_stopped_count / total if total > 0 else 0

    # 閾値 (config.yml準拠)
    no_trade_max = float(_load_config_value('no_trade_rate_max', '0.95'))
    force_stop_max = float(_load_config_value('force_stop_rate_max', '0.70'))
    resp_min = float(_load_config_value('avg_response_length_min', '30'))

    warnings = []
    if no_trade_rate > no_trade_max:
        warnings.append(f"no_trade_rate {no_trade_rate:.2%} > {no_trade_max:.0%}")
    if force_stopped_rate > force_stop_max:
        warnings.append(f"force_stopped_rate {force_stopped_rate:.2%} > {force_stop_max:.0%}")
    if avg_response_length < resp_min:
        warnings.append(f"avg_response_length {avg_response_length:.0f} < {resp_min}")

    return {
        'total': total,
        'no_trade_count': no_trade_count,
        'force_stopped_count': force_stopped_count,
        'no_trade_rate': no_trade_rate,
        'force_stopped_rate': force_stopped_rate,
        'avg_response_length': avg_response_length,
        'warnings': warnings,
        'caution_passed': len(warnings) == 0,
    }


# ===== 統合 =====

def all_metrics(model_version: Optional[str] = None) -> dict:
    if model_version is None:
        model_version = _load_config_value('model_version', 'v6')
    signals = load_signals(model_version)
    labels = load_labels(model_version)
    return {
        'model_version': model_version,
        'defense': metrics_defense(signals, labels),
        'offense': metrics_offense(signals),
        'caution': metrics_caution(signals),
    }


if __name__ == "__main__":
    import json as _j
    result = all_metrics()
    print(_j.dumps(result, ensure_ascii=False, indent=2))
