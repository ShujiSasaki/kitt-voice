"""Shujiさん向け 8択ラベル付けツール (CLI)

3者合意 (2026-06-24 06:41 btc部屋):
「失敗の仕分けを8種類のボタンを選ぶだけにする (Shujiさん作業負担軽減)」

使い方:
    cd btc-trading/ai_growth
    python3 eval/label_tool.py [--limit 10]

各信号を1件ずつ表示 → 8択選択 (複数可、 0=正例、 q=保存して終了) → labels_v{N}.jsonl
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

HERE = Path(__file__).parent.parent  # ai_growth/

# 8択ラベル (合意通り)
LABELS = {
    1: "危ない場面で「やる」と言った (no_trade違反)",
    2: "強制ストップ7条件のバグ (ルール誤動作)",
    3: "同フレーズ無限ループ",
    4: "内容崩壊 (9連続/中国語片/空)",
    5: "攻めるべき場面で見送った (臆病すぎ)",
    6: "損失幅 (逆行) が大きすぎた (RR悪い)",
    7: "利益機会を取り逃した (RR良くなかった)",
    8: "その他 (テキスト記入)",
}


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
    signals = []
    for line in log_file.read_text(encoding='utf-8').splitlines():
        if line.strip():
            signals.append(json.loads(line))
    return signals


def load_existing_labels(model_version: str) -> dict[str, dict]:
    """既存ラベル (再開対応): ts → label dict"""
    label_file = HERE / "eval" / f"labels_{model_version}.jsonl"
    if not label_file.exists():
        return {}
    out = {}
    for line in label_file.read_text(encoding='utf-8').splitlines():
        if line.strip():
            d = json.loads(line)
            out[d.get('signal_ts', '')] = d
    return out


def save_label(label: dict, model_version: str):
    label_file = HERE / "eval" / f"labels_{model_version}.jsonl"
    label_file.parent.mkdir(exist_ok=True)
    with open(label_file, 'a', encoding='utf-8') as f:
        f.write(json.dumps(label, ensure_ascii=False) + '\n')


def display_signal(signal: dict, index: int, total: int):
    """1件の信号を表示"""
    print()
    print("=" * 70)
    print(f"  Q{index + 1}/{total}  ts={signal.get('ts','')[:19]}  BTC=${signal.get('btc_price', 0):.2f}")
    print("=" * 70)
    print(f"[regime] {signal.get('regime')}")
    print(f"[materials] {signal.get('materials')}")
    print(f"[response]")
    print(f"  {signal.get('response', '')[:400]}")
    sig_info = signal.get('signal', {})
    fs_info = signal.get('force_stop', {})
    print(f"[signal] {sig_info.get('signal')} (stance={sig_info.get('stance')})")
    if fs_info.get('triggered'):
        print(f"[force_stop] triggered: {fs_info.get('reason')}")
    print("-" * 70)


def display_label_menu():
    """8択メニューを表示"""
    print()
    print("Shujiさんの評価をお願いします (正例なら 0、 複数該当はカンマ区切り):")
    for k, v in LABELS.items():
        print(f"  [{k}] {v}")
    print("  [0] 正例 (どれにも該当しない、 良い判定)")
    print("  [s] スキップ (後で評価)")
    print("  [q] 保存して終了")
    print()


def parse_input(s: str) -> tuple[str, list[int], str]:
    """ユーザー入力を解釈

    Returns:
        (action: 'label' | 'skip' | 'quit', labels: list[int], free_text: str)
    """
    s = s.strip()
    if s.lower() in ('q', 'quit', 'exit'):
        return 'quit', [], ''
    if s.lower() in ('s', 'skip'):
        return 'skip', [], ''
    if s == '0':
        return 'label', [0], ''
    try:
        # カンマ区切り or 空白区切りを許容
        items = [int(x.strip()) for x in s.replace(' ', ',').split(',') if x.strip()]
        for x in items:
            if x not in range(0, 9):
                raise ValueError(f"無効な番号: {x}")
        return 'label', items, ''
    except ValueError as e:
        print(f"⚠️  入力エラー: {e}、 もう一度")
        return 'invalid', [], ''


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Shujiさん向け 8択ラベル付けツール")
    parser.add_argument('--limit', type=int, default=None,
                        help="この回で評価する最大件数 (デフォルト: 全件)")
    args = parser.parse_args()

    model_version = _load_config_value('model_version', 'v6')
    signals = load_signals(model_version)
    if not signals:
        print(f"⚠️  logs/signals_{model_version}.jsonl が空 or 存在しません")
        sys.exit(1)

    existing = load_existing_labels(model_version)
    pending = [s for s in signals if s.get('ts', '') not in existing]

    print()
    print("=" * 70)
    print(f"  danjerクローンAI 育成リング ラベル付けツール (8択)")
    print(f"  model: {model_version}")
    print(f"  全件: {len(signals)}件、 評価済み: {len(existing)}件、 未評価: {len(pending)}件")
    print("=" * 70)

    if not pending:
        print("\n✅ 全件評価済みです")
        return

    if args.limit:
        pending = pending[:args.limit]
        print(f"  この回で評価: {len(pending)}件")

    labeled_count = 0
    skipped_count = 0
    for i, signal in enumerate(pending):
        display_signal(signal, i, len(pending))
        display_label_menu()

        while True:
            choice = input("選択 > ").strip()
            action, labels, _ = parse_input(choice)
            if action == 'invalid':
                continue
            break

        if action == 'quit':
            print("\n保存して終了します")
            break
        if action == 'skip':
            skipped_count += 1
            continue

        free_text = ''
        if 8 in labels:
            free_text = input("その他: 詳細を記入 > ").strip()

        label_entry = {
            'signal_ts': signal.get('ts'),
            'labeled_at': datetime.now(timezone(timedelta(hours=9))).isoformat(),
            'labels': labels,  # 0 = 正例、 1-8 = 各失敗カテゴリ
            'free_text': free_text,
            'is_positive': labels == [0],
            'is_failure': any(l > 0 for l in labels),
            'failure_categories': [LABELS[l] for l in labels if l in LABELS],
        }
        save_label(label_entry, model_version)
        labeled_count += 1
        print(f"✓ ラベル保存 ({labeled_count}件目)")

    print()
    print("=" * 70)
    print(f"  完了: 評価 {labeled_count}件、 スキップ {skipped_count}件")
    print(f"  累計: {len(existing) + labeled_count}/{len(signals)}件")
    print("=" * 70)


if __name__ == "__main__":
    main()
