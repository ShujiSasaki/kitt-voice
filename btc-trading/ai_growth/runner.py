"""育成リング メインループ

3者合意 (2026-06-24 06:41 btc部屋):
- 起動時 paper_mode=true assert (絶対必須)
- 1日2-3回判定 → 3週間で50-100件 (合意の目標件数)
- 全判定をログに残す (Shujiさん目視ラベル付けの素材)
- 取引所APIには一切触らない (yfinance public のみ)

このファイルは「ローカルファイル読み書きのみ」、 注文関連処理は一切含まない。
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))


# ===== paper_mode 起動時assert (合意必須) =====
def assert_paper_mode():
    config_path = HERE / "config.yml"
    if not config_path.exists():
        raise RuntimeError("config.yml not found")
    text = config_path.read_text(encoding='utf-8')
    for line in text.splitlines():
        line_clean = line.split('#')[0].strip()
        if line_clean.startswith('paper_mode:'):
            value = line_clean.split(':', 1)[1].strip().lower()
            if value not in ('true', 'yes', 'on'):
                raise RuntimeError(
                    f"❌ paper_mode={value} (true以外)。 起動禁止。\n"
                    "本番遮断の合意により、 paper_mode=true 以外では起動できません。"
                )
            return True
    raise RuntimeError("❌ paper_mode 未設定。 起動禁止。")


def _load_config_value(key: str, default=None):
    config_path = HERE / "config.yml"
    if not config_path.exists():
        return default
    for line in config_path.read_text(encoding='utf-8').splitlines():
        line_clean = line.split('#')[0].strip()
        if line_clean.startswith(f'{key}:'):
            return line_clean.split(':', 1)[1].strip().strip('"\'')
    return default


# ===== メインループ =====

def run_single_judgement():
    """1回の判定 (fetch → regime → predict → stop_rules → signal → log)"""
    from data_source import (
        fetch_btc_ohlcv, get_recent_candles, get_latest_candle,
        fetch_market_snapshot,
    )
    from regime_detector import (
        detect_regime, extract_materials, extract_market_materials,
    )
    from inference import predict
    from stop_rules import force_stop_check
    from signal_generator import generate_signal

    # 1. fetch
    print(f"[{datetime.now()}] fetching BTC OHLCV...")
    df = fetch_btc_ohlcv(period="60d", interval="1h")
    candles = get_recent_candles(df, n=240)  # 10日分
    latest = get_latest_candle(df)

    # 1b. loop2合意: 判定直前にライブ public市場データ取得 (OI/FR/L:S/板)
    print(f"  fetching market snapshot (OI/FR/L:S/orderbook)...")
    market_snapshot = fetch_market_snapshot("BTCUSDT")

    # 2. regime + materials (OHLCV由来 + ライブ snapshot由来 を マージ)
    regime = detect_regime(candles)
    base_mats = extract_materials(candles, regime)
    live_mats = extract_market_materials(market_snapshot, candles)
    materials = base_mats + live_mats
    print(f"  regime={regime}")
    print(f"  OHLCV由来 materials={base_mats}")
    print(f"  ライブ snapshot materials={live_mats}")
    print(f"  latest close=${latest['close']:.2f}")

    # 3. predict (v6 LoRA、 dry_run可)
    date_str = datetime.now().strftime("%Y-%m-%d")
    response = predict(regime, materials, date_str)
    print(f"  response: {response[:200]}")

    # 4. force_stop check
    fs_result = force_stop_check(regime, response, materials, candles)
    print(f"  force_stop: {fs_result}")

    # 5. signal
    signal = generate_signal(response, fs_result)
    print(f"  signal: {signal['signal']} (stance={signal['stance']})")

    # 6. log
    log_entry = {
        'ts': datetime.now(timezone(timedelta(hours=9))).isoformat(),
        'btc_price': latest['close'],
        'regime': regime,
        'materials': materials,
        'market_snapshot': market_snapshot,
        'response': response,
        'force_stop': fs_result,
        'signal': signal,
        'paper_mode_confirmed': True,
        'no_order_assertion': True,
    }
    log_dir = HERE / "logs"
    log_dir.mkdir(exist_ok=True)
    model_version = _load_config_value('model_version', 'v6')
    log_file = log_dir / f"signals_{model_version}.jsonl"
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
    print(f"  logged to {log_file.name}")
    print()
    return log_entry


def main_loop():
    """メインループ (1日2-3回判定)"""
    print("=" * 70)
    print("  danjerクローンAI 育成リング 起動")
    print("=" * 70)

    # 起動時の安全assert
    print("[startup] checking paper_mode...")
    assert_paper_mode()
    print("[startup] ✅ paper_mode=true (本番遮断ON)")
    print()

    interval_hours = int(_load_config_value('judgement_interval_hours', '8'))
    print(f"[startup] 判定間隔: {interval_hours}時間 (1日{24 // interval_hours}回)")
    print()

    while True:
        try:
            run_single_judgement()
        except Exception as e:
            print(f"[ERROR] {type(e).__name__}: {e}")
            # 1回失敗してもループは止めない
        print(f"[sleep] {interval_hours}h ({interval_hours * 3600}s)")
        time.sleep(interval_hours * 3600)


if __name__ == "__main__":
    if '--once' in sys.argv:
        # 1回だけ実行 (テスト用)
        assert_paper_mode()
        print("[runner] paper_mode confirmed, running once...")
        run_single_judgement()
    else:
        main_loop()
