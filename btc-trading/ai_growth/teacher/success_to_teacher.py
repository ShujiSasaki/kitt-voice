"""正例 (label=[0]) → 教師データに追加

3者合意 (2026-06-24) の Phase 3 補完:
正例 (Shujiさんが「良い判定」 と認めたもの) は そのまま教師データ化。
これで次バージョンが正しい応答パターンを強化できる。

出力: teacher/teacher_{N}.jsonl (failure_to_teacher の結果に追記)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).parent.parent
sys.path.insert(0, str(HERE / "teacher"))

from failure_to_teacher import (
    load_signals, load_labels, build_user_prompt, SYS_PROMPT, _load_config_value
)


def convert_successes(model_version: str) -> int:
    signals = load_signals(model_version)
    labels = load_labels(model_version)
    if not labels:
        print(f"⚠️ labels_{model_version}.jsonl が空、 変換するものなし")
        return 0

    out_file = HERE / "teacher" / f"teacher_{model_version}.jsonl"

    converted = 0
    # 追記モードで開く (failure_to_teacher の結果がある前提)
    with open(out_file, 'a', encoding='utf-8') as f:
        for signal in signals:
            ts = signal.get('ts', '')
            label = labels.get(ts)
            if not label:
                continue
            if not label.get('is_positive', False):
                continue  # 失敗ケースはスキップ

            # 正例: response をそのまま教師にする
            regime = signal.get('regime', 'range')
            materials = signal.get('materials', [])
            date_str = ts[:10] if ts else '2026-06-24'
            response = signal.get('response', '').strip()
            if len(response) < 20:
                continue  # 短すぎは スキップ

            teacher = {
                'messages': [
                    {'role': 'system', 'content': SYS_PROMPT},
                    {'role': 'user', 'content': build_user_prompt(regime, date_str, materials)},
                    {'role': 'assistant', 'content': response},
                ],
                'meta': {
                    'source': 'success_to_teacher',
                    'original_signal_ts': ts,
                    'verified_by': 'shuji_manual_review',
                },
            }
            f.write(json.dumps(teacher, ensure_ascii=False) + '\n')
            converted += 1

    print(f"=== 正例 → 教師化 (model={model_version}) ===")
    print(f"  正例件数: {converted}")
    print(f"  出力: teacher/teacher_{model_version}.jsonl (追記)")
    return converted


if __name__ == "__main__":
    model_version = _load_config_value('model_version', 'v6')
    convert_successes(model_version)
