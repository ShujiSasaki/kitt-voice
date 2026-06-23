"""育成日記ジェネレータ (各サイクル末で自動生成、 3者会議や Shujiさん用)

3者合意 (2026-06-24) の Phase 2 補完:
サイクル末で 「v(N): 設定 / 結果 / 教訓 / 次バージョンへ」 をMarkdownで自動生成。
training/version_log.md に追記する形式。

使い方:
    python3 eval/cycle_diary.py [--append]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

HERE = Path(__file__).parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "eval"))

from metrics import all_metrics, _load_config_value


def generate_diary(model_version: str) -> str:
    metrics = all_metrics(model_version)
    defense = metrics['defense']
    offense = metrics['offense']
    caution = metrics['caution']

    now = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M JST")

    lines = []
    lines.append(f"## {model_version} 育成日記 ({now})")
    lines.append("")

    # サイクル概要
    lines.append("### サイクル概要")
    lines.append(f"- 総判定数: {defense.get('total', 0)}")
    lines.append(f"- Shuji目視ラベル付き: {defense.get('labeled', 0)}")
    lines.append(f"- ラベル未付き: {defense.get('unlabeled', 0)}")
    lines.append("")

    # 守り層
    lines.append("### 🛡 守り層 (退場しない=土台)")
    lines.append(f"- 危ない場面で「やる」: {defense.get('dangerous_yarei_count', 0)}件 {'✅' if defense.get('dangerous_yarei_count', 0) == 0 else '❌'}")
    lines.append(f"- 強制ストップ7条件バグ: {defense.get('stop_rule_bugs', 0)}件 {'✅' if defense.get('stop_rule_bugs', 0) == 0 else '❌'}")
    lines.append(f"- 自動検出ループ: {defense.get('auto_loop_detected', 0)}件")
    lines.append(f"- 自動検出崩壊: {defense.get('auto_collapse_detected', 0)}件")
    lines.append(f"- **守り層総合: {'✅ PASS' if defense.get('defense_passed', False) else '❌ FAIL'}**")
    lines.append("")

    # 攻め層
    lines.append("### ⚔ 攻め層 (とことん上手くなる=ゴール)")
    for h in [1, 4, 24]:
        pnl = offense.get(f'pnl_{h}h', {})
        evald = pnl.get('evaluated', 0)
        if evald > 0:
            avg = pnl['sum'] / evald
            lines.append(f"- 仮想損益 {h}h後 平均: ${avg:+.2f} ({pnl['wins']}勝 / {pnl['losses']}負 / {evald}件評価)")
        else:
            lines.append(f"- 仮想損益 {h}h後: 未到達")

    win_rate = offense.get('win_rate_24h', 0)
    lines.append(f"- 勝率 (24h): {win_rate * 100:.1f}%")
    pnl_24 = offense.get('pnl_24h', {})
    lines.append(f"- 最大上昇幅 (24h): ${pnl_24.get('max_run_up', 0):.2f}")
    lines.append(f"- 最大逆行幅 (drawdown): ${pnl_24.get('max_drawdown', 0):.2f}")
    lines.append("")

    # 臆病チェック
    lines.append("### 😨 臆病チェック")
    lines.append(f"- no_trade率: {caution.get('no_trade_rate', 0) * 100:.1f}%")
    lines.append(f"- force_stopped率: {caution.get('force_stopped_rate', 0) * 100:.1f}%")
    lines.append(f"- 平均応答長: {caution.get('avg_response_length', 0):.0f}文字")
    lines.append(f"- **臆病チェック総合: {'✅ PASS' if caution.get('caution_passed', False) else '⚠️ WARN'}**")
    warnings = caution.get('warnings', [])
    if warnings:
        lines.append("- 警告:")
        for w in warnings:
            lines.append(f"  - ⚠️ {w}")
    lines.append("")

    # 教訓 / 次バージョン
    lines.append("### 教訓 / 次バージョンへ")

    # 自動判定
    if defense.get('defense_passed') and caution.get('caution_passed'):
        lines.append("- ✅ 合格ライン全達成、 次バージョンへ進行可能")
    elif defense.get('defense_passed'):
        lines.append("- ⚠️ 守り層 PASS、 ただし臆病警告あり → 学習データバランス調整候補")
    else:
        lines.append("- ❌ 守り層 FAIL、 失敗ケースを教師化して次バージョンへ")

    # 失敗カテゴリ別の提案
    if defense.get('dangerous_yarei_count', 0) > 0:
        lines.append(f"  - 安全弁データ追加が必要 (危ない場面で「やる」 {defense.get('dangerous_yarei_count', 0)}件)")
    if caution.get('warnings'):
        for w in caution['warnings']:
            if 'no_trade_rate' in w:
                lines.append("  - 攻め例データを追加 (no_trade率高すぎ)")
            elif 'force_stopped_rate' in w:
                lines.append("  - 強制ストップ7条件の閾値見直し (発火率高すぎ)")
            elif 'response_length' in w:
                lines.append("  - 学習設定見直し (応答短すぎ)")

    lines.append("")

    # 実弾¥10万 移行判定
    lines.append("### 💰 実弾¥10万 移行条件チェック")
    min_cycles = int(_load_config_value('min_cycles_completed', '3'))
    lines.append(f"- 最低{min_cycles}サイクル完了: 未確認 (cycle tracking 必要)")
    lines.append(f"- 臆病警告ゼロ: {'✅ クリア' if caution.get('caution_passed') else '❌ 未クリア'}")
    lines.append(f"- 守り層 PASS: {'✅ クリア' if defense.get('defense_passed') else '❌ 未クリア'}")
    lines.append(f"- 最終判断: Shujiさん自身 (AI多数決外、 合意明記)")
    lines.append("")

    lines.append("---")
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--append', action='store_true',
                        help='version_log.md に追記 (デフォルトは標準出力のみ)')
    parser.add_argument('--version', default=None,
                        help='対象バージョン (デフォルトは config.yml の model_version)')
    args = parser.parse_args()

    mv = args.version or _load_config_value('model_version', 'v6')
    diary = generate_diary(mv)
    print(diary)

    if args.append:
        log_path = HERE / "training" / "version_log.md"
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write("\n\n")
            f.write(diary)
        print(f"\n[appended to {log_path}]")


if __name__ == "__main__":
    main()
