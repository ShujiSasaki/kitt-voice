"""強制ストップ7条件 見直しレポート生成

3者合意 (2026-06-24) の Phase 3 補完:
ラベル_2 (強制ストップ7条件のバグ) で集まったケースを集計し、
各ルールの「過剰反応 (false positive)」「見落とし (false negative)」 を分析。

出力: teacher/stop_rules_update_{N}.md (Shujiさん用 見直し提案)
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent.parent
sys.path.insert(0, str(HERE / "teacher"))

from failure_to_teacher import load_signals, load_labels, _load_config_value


RULE_DESCRIPTIONS = {
    'rule_1_no_stop_loss': '損切り不明',
    'rule_2_sl_too_close': '損切り近すぎ',
    'rule_3_unfounded_rally': '根拠なし急騰',
    'rule_4_insufficient_grounds': '根拠不足',
    'rule_5_thin_counter': '薄い逆張り',
    'rule_6_thin_or_extreme': '板薄/急変',
    'rule_7_model_ambiguous': 'モデル曖昧',
}


def analyze_rules(model_version: str) -> dict:
    signals = load_signals(model_version)
    labels = load_labels(model_version)

    # 各ルールの発火回数 + そのうち「バグ判定 (label_2)」 された割合
    rule_fire = Counter()
    rule_bug_marked = Counter()

    for signal in signals:
        ts = signal.get('ts', '')
        rules_hit = signal.get('force_stop', {}).get('rules_hit', [])
        for r in rules_hit:
            rule_fire[r] += 1
            # 該当signalが label_2 (バグ判定) されたか
            label = labels.get(ts)
            if label and 2 in label.get('labels', []):
                rule_bug_marked[r] += 1

    # 各ルールの false positive 率
    analysis = {}
    for rule, fire_count in rule_fire.items():
        bug_count = rule_bug_marked[rule]
        fp_rate = bug_count / fire_count if fire_count > 0 else 0
        analysis[rule] = {
            'description': RULE_DESCRIPTIONS.get(rule, rule),
            'fire_count': fire_count,
            'bug_marked_count': bug_count,
            'false_positive_rate': fp_rate,
            'recommendation': _make_recommendation(rule, fp_rate, fire_count),
        }

    return analysis


def _make_recommendation(rule: str, fp_rate: float, fire_count: int) -> str:
    if fire_count < 5:
        return f"⏳ サンプル数不足 (発火{fire_count}件)、 判断保留"
    if fp_rate > 0.5:
        return f"🔧 過剰反応 (false positive {fp_rate:.0%})、 閾値を緩めるべき"
    if fp_rate > 0.3:
        return f"⚠️ やや過剰 (false positive {fp_rate:.0%})、 閾値の微調整候補"
    if fp_rate == 0:
        return f"✅ 適切 (false positive 0%)"
    return f"✅ 概ね適切 (false positive {fp_rate:.0%})"


def generate_report(model_version: str):
    analysis = analyze_rules(model_version)
    out_file = HERE / "teacher" / f"stop_rules_update_{model_version}.md"

    lines = []
    lines.append(f"# 強制ストップ7条件 見直しレポート (model={model_version})\n")
    lines.append(f"3者合意 (2026-06-24) の Phase 3: ラベル_2 (強制ストップバグ) 集計分析\n")
    lines.append("")
    lines.append("## 各ルールの動作分析\n")
    lines.append("| ルール | 説明 | 発火数 | バグ判定 | false positive | 推奨 |")
    lines.append("|---|---|---|---|---|---|")
    for rule, info in sorted(analysis.items()):
        lines.append(
            f"| `{rule}` | {info['description']} | {info['fire_count']} | "
            f"{info['bug_marked_count']} | {info['false_positive_rate']:.0%} | "
            f"{info['recommendation']} |"
        )

    lines.append("")
    lines.append("## アクション (Shujiさんへ)")
    lines.append("")
    lines.append("- 🔧 「過剰反応」 ルール → `stop_rules.py` の閾値見直し")
    lines.append("- ⚠️ 「やや過剰」 ルール → 次サイクルで動向観察")
    lines.append("- ✅ 「適切」 ルール → そのまま維持")
    lines.append("- 7条件で **見落とし** がないか (Shujiさん感覚): label_1 (危ない場面でやる) が出てる場合、 ルール追加候補")
    lines.append("")

    out_file.write_text('\n'.join(lines), encoding='utf-8')
    print(f"=== レポート出力 ===")
    print(f"  {out_file}")
    print()
    print('\n'.join(lines[:30]))


if __name__ == "__main__":
    model_version = _load_config_value('model_version', 'v6')
    generate_report(model_version)
