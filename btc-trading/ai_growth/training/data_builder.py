"""v(N+1) 学習データ生成

3者合意 (2026-06-24) の Phase 4:
既存 8000件 (vNの学習データ) + teacher_vN.jsonl (失敗修正+正例) →
vN+1の学習データを生成。 ランダムシャッフル + 安全弁比率維持。

出力: training/data_v{N+1}.jsonl (Kaggle に push する元)
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).parent.parent
sys.path.insert(0, str(HERE / "teacher"))

from failure_to_teacher import _load_config_value


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding='utf-8').splitlines() if l.strip()]


def is_safety_valve(messages: list[dict]) -> bool:
    """assistant 応答が「【スタンス】見送り」「【スタンス】様子見」 で終わる = 安全弁"""
    if len(messages) < 3:
        return False
    asst = messages[2].get('content', '')
    return '【スタンス】見送り' in asst or '【スタンス】様子見' in asst


def build_next_version_data(
    current_version: str,
    next_version: str,
    base_data_path: Path,
    target_size: int = 8000,
    seed: int = 42,
) -> dict:
    """新バージョン学習データ生成

    Args:
        current_version: 現バージョン ('v6')
        next_version: 次バージョン ('v7')
        base_data_path: vN の学習データ (例: danjer_lora_poc_data.jsonl)
        target_size: 目標件数 (デフォルト8000、 合意通り)
        seed: shuffle用 (再現性のため42固定)
    """
    print(f"=== v{next_version} 学習データ生成 ===")
    print(f"  base: {base_data_path}")

    # 既存データ読み込み
    base_data = load_jsonl(base_data_path)
    print(f"  既存データ: {len(base_data)}件")

    # 教師データ読み込み (vN の eval結果から)
    teacher_path = HERE / "teacher" / f"teacher_{current_version}.jsonl"
    teacher_data = load_jsonl(teacher_path)
    print(f"  教師データ ({current_version}): {len(teacher_data)}件")

    if not teacher_data:
        print(f"⚠️ teacher_{current_version}.jsonl が空、 ベースデータをそのまま v{next_version} に")

    # 既存データから teacher と重複するものを除外 (近似: user prompt一致)
    teacher_users = set()
    for t in teacher_data:
        if len(t.get('messages', [])) >= 2:
            teacher_users.add(t['messages'][1].get('content', ''))

    base_filtered = [
        b for b in base_data
        if len(b.get('messages', [])) < 2 or
        b['messages'][1].get('content', '') not in teacher_users
    ]
    print(f"  既存データ (重複除外後): {len(base_filtered)}件")

    # 合算
    combined = base_filtered + teacher_data
    print(f"  合算: {len(combined)}件")

    # 件数調整: target_size に合わせる
    random.seed(seed)
    if len(combined) > target_size:
        random.shuffle(combined)
        combined = combined[:target_size]
    elif len(combined) < target_size:
        # 不足は base から重複OKで補完
        needed = target_size - len(combined)
        supplement = random.choices(base_filtered, k=needed)
        combined.extend(supplement)

    # 安全弁比率確認
    safety_count = sum(1 for r in combined if is_safety_valve(r.get('messages', [])))
    safety_ratio = safety_count / len(combined) if combined else 0
    print(f"  安全弁比率: {safety_count}/{len(combined)} = {safety_ratio:.2%}")

    # 最終シャッフル
    random.shuffle(combined)

    # 出力
    out_file = HERE / "training" / f"data_{next_version}.jsonl"
    out_file.parent.mkdir(exist_ok=True)
    with open(out_file, 'w', encoding='utf-8') as f:
        for r in combined:
            # 'meta' キーがあれば残すが、 messages のみで学習可能
            messages = r.get('messages')
            if messages:
                f.write(json.dumps({'messages': messages}, ensure_ascii=False) + '\n')

    print(f"  出力: {out_file} ({len(combined)}件)")
    return {
        'next_version': next_version,
        'output_file': str(out_file),
        'count': len(combined),
        'safety_count': safety_count,
        'safety_ratio': safety_ratio,
        'from_base': len(base_filtered),
        'from_teacher': len(teacher_data),
    }


def detect_next_version(current: str) -> str:
    """v6 → v7 のような version番号インクリメント"""
    if current.startswith('v') and current[1:].isdigit():
        return f"v{int(current[1:]) + 1}"
    return current + "_next"


if __name__ == "__main__":
    current = _load_config_value('model_version', 'v6')
    next_v = detect_next_version(current)
    base_path = Path('/Users/shuji/Desktop/kitt-voice/btc-trading/danjer_triplet/danjer_lora_poc_data.jsonl')
    result = build_next_version_data(current, next_v, base_path)
    print()
    print(json.dumps(result, ensure_ascii=False, indent=2))
