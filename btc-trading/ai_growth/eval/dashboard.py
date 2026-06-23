"""育成リング 評価ダッシュボード (CLI)

3者合意 (2026-06-24) の合意指標を見やすく表示:
- 守り層 (退場しない=土台)
- 攻め層 (とことん上手くなる=ゴール)
- 臆病チェック (何もしないAIになってないか)
- 育成サイクル進捗 (50-100件の達成度)
- 実弾¥10万 移行条件チェック
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "eval"))

from metrics import all_metrics, load_signals, _load_config_value


def _box(title: str, items: list[tuple[str, str]], width: int = 70):
    print()
    print("┌" + "─" * (width - 2) + "┐")
    title_text = f" {title} "
    pad = (width - 2 - len(title_text)) // 2
    print("│" + " " * pad + title_text + " " * (width - 2 - pad - len(title_text)) + "│")
    print("├" + "─" * (width - 2) + "┤")
    for k, v in items:
        line = f" {k:<35} {v}"
        if len(line) > width - 2:
            line = line[:width - 5] + "..."
        print("│" + line + " " * (width - 2 - len(line)) + "│")
    print("└" + "─" * (width - 2) + "┘")


def _verdict(value: bool, true_msg="✅", false_msg="❌") -> str:
    return true_msg if value else false_msg


def show_dashboard():
    metrics = all_metrics()
    mv = metrics['model_version']

    defense = metrics['defense']
    offense = metrics['offense']
    caution = metrics['caution']

    print()
    print("═" * 70)
    print(f"  danjerクローンAI 育成リング 評価ダッシュボード  (model: {mv})")
    print("═" * 70)

    # ===== 育成サイクル進捗 =====
    target_min = int(_load_config_value('cycle_target_count_min', '50'))
    target_max = int(_load_config_value('cycle_target_count_max', '100'))
    total = defense.get('total', 0)
    progress_pct = total / target_max * 100 if target_max > 0 else 0
    bar_filled = int(progress_pct / 5)  # 20bar
    bar = "█" * min(bar_filled, 20) + "░" * max(20 - bar_filled, 0)
    _box(f"育成サイクル進捗 ({total}/{target_max}件)", [
        ("件数進捗", f"{bar} {progress_pct:.0f}%"),
        ("目標", f"{target_min}〜{target_max}件 / 3週間"),
        ("ラベル付き", f"{defense.get('labeled', 0)}件"),
        ("ラベル未付き", f"{defense.get('unlabeled', 0)}件"),
    ])

    # ===== 守り層 =====
    items = [
        ("危ない場面で「やる」 (必須 0件)", f"{defense.get('dangerous_yarei_count', 0)}件 {_verdict(defense.get('dangerous_yarei_count', 0) == 0)}"),
        ("強制ストップ7条件バグ (必須 0件)", f"{defense.get('stop_rule_bugs', 0)}件 {_verdict(defense.get('stop_rule_bugs', 0) == 0)}"),
        ("同フレーズ無限ループ (自動)", f"{defense.get('auto_loop_detected', 0)}件 {_verdict(defense.get('auto_loop_detected', 0) == 0)}"),
        ("内容崩壊 (自動)", f"{defense.get('auto_collapse_detected', 0)}件 {_verdict(defense.get('auto_collapse_detected', 0) == 0)}"),
        ("ループ (Shuji目視)", f"{defense.get('manual_loop_labeled', 0)}件"),
        ("崩壊 (Shuji目視)", f"{defense.get('manual_collapse_labeled', 0)}件"),
        ("守り層 総合", f"{_verdict(defense.get('defense_passed', False), '✅ PASS', '❌ FAIL')}"),
    ]
    _box("🛡  守り層 (退場しない=土台)", items)

    # ===== 攻め層 =====
    items = []
    for h in [1, 4, 24]:
        pnl = offense.get(f'pnl_{h}h', {})
        evald = pnl.get('evaluated', 0)
        if evald > 0:
            avg = pnl['sum'] / evald
            items.append((f"仮想損益 {h}h後 平均", f"${avg:+.2f} ({evald}件評価)"))
            items.append((f"  勝 / 負", f"{pnl['wins']}勝 / {pnl['losses']}負"))
        else:
            items.append((f"仮想損益 {h}h後", "未到達 (まだN時間経過してない)"))

    win_rate = offense.get('win_rate_24h', 0)
    items.append(("勝率 (24h)", f"{win_rate * 100:.1f}%"))

    pnl_24 = offense.get('pnl_24h', {})
    items.append(("最大上昇幅 (24h)", f"${pnl_24.get('max_run_up', 0):.2f}"))
    items.append(("最大逆行幅 (drawdown)", f"${pnl_24.get('max_drawdown', 0):.2f}"))
    _box("⚔  攻め層 (とことん上手くなる=ゴール)", items)

    # ===== 臆病チェック =====
    items = [
        ("no_trade率", f"{caution.get('no_trade_rate', 0) * 100:.1f}% (閾値 95%超で警告)"),
        ("force_stopped率", f"{caution.get('force_stopped_rate', 0) * 100:.1f}% (閾値 70%超で警告)"),
        ("平均応答長", f"{caution.get('avg_response_length', 0):.0f}文字 (閾値 30文字未満で警告)"),
        ("臆病チェック 総合", f"{_verdict(caution.get('caution_passed', False), '✅ PASS', '⚠️  WARN')}"),
    ]
    warnings = caution.get('warnings', [])
    if warnings:
        items.append(("", ""))
        for w in warnings:
            items.append(("⚠️ ", w))
    _box("😨 臆病チェック (何もしないAIになってないか)", items)

    # ===== 実弾¥10万 移行条件 =====
    min_cycles = int(_load_config_value('min_cycles_completed', '3'))
    cw = caution.get('caution_passed', False)
    df = defense.get('defense_passed', False)
    items = [
        ("最低サイクル数完了 (3サイクル)", f"未確認 (cycle tracking 未実装)"),
        ("臆病警告ゼロ", f"{_verdict(cw, '✅ クリア', '❌ 未クリア')}"),
        ("守り層 PASS", f"{_verdict(df, '✅ クリア', '❌ 未クリア')}"),
        ("最終判断", "Shujiさん自身 (AI多数決外、 合意明記)"),
    ]
    _box("💰 実弾¥10万 移行条件チェック", items)

    print()
    print("=" * 70)
    print(f"  関連ファイル:")
    print(f"    信号ログ: logs/signals_{mv}.jsonl")
    print(f"    ラベル: eval/labels_{mv}.jsonl")
    print(f"  次の作業:")
    print(f"    python3 eval/label_tool.py で未ラベル {defense.get('unlabeled', 0)}件を評価")
    print("=" * 70)


if __name__ == "__main__":
    show_dashboard()
