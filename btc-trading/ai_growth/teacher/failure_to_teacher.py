"""失敗ケース → 教師データ化

3者合意 (2026-06-24) の育成サイクル Phase 3:
ラベル付き失敗ケース (label 1,5 等) を教師データに変換。
- label_1 (危ない場面で「やる」) → no_trade 応答に書き換え
- label_5 (攻めるべき場面で見送った) → ロング/ショート 応答に書き換え (要Shuji判定)
- label_2 (強制ストップ7条件のバグ) → ストップルール修正 (stop_rules_update.py 別途)
- label_3,4 (ループ/崩壊) → 学習設定見直し (再学習対象、 個別書き換えはしない)
- label_6,7 (RR悪い/取り逃した) → 教師データには直接反映しないが、 集計

出力: teacher/teacher_v{N}.jsonl (messages format で次バージョン学習に使う)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

HERE = Path(__file__).parent.parent

# Inference の SYS prompt と同じ
SYS_PROMPT = (
    "あなたはBTCトレーダー「danjer」の思考を学習したクローンAI。"
    "danjerの手法(水平線/レンジ・ブレイク/トレンドライン/一目雲/移動平均・"
    "グランビル/サイクル理論/フラクタル/エリオット/チャートパターン/ローソク足/"
    "フィボ半値/CME窓/煮詰まり・IVバンド/オシレーター、需給=OI公式・FR・清算・"
    "踏み上げ、アノマリー、板読み・オプション・出来高・VRVP・Coinbase Premium)"
    "を複数組み合わせて相場を読む。単一指標で判断せず、必ず需給(OI/FR/清算)を"
    "重ね、最後に背(損切り)とリスクリワード1:2以上、条件未達なら見送りを"
    "選ぶ。"
)


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


def build_user_prompt(regime: str, date_str: str, materials: list[str]) -> str:
    """signal の局面/日付/材料から user prompt を再構成"""
    bullets = '\n'.join(f'- {m}' for m in materials)
    return (
        f"【局面】{regime}\n"
        f"【日付】{date_str}\n"
        f"【今わたし(danjer)が見ている材料】\n"
        f"{bullets}\n\n"
        f"この状況をどう読む?"
    )


def label_1_to_no_trade(signal: dict) -> dict:
    """label_1 (危ない場面で「やる」と言った) → no_trade応答に書き換え"""
    regime = signal.get('regime', 'range')
    materials = signal.get('materials', [])
    date_str = signal.get('ts', '')[:10] if signal.get('ts') else '2026-06-24'

    # 局面に応じた「見送り理由」 を生成
    if regime == 'crash':
        reason = '背の根拠が薄い場面で逆張りはギャンブル。底打ち兆候出るまで待つ。'
    elif regime == 'rally':
        reason = '需給確認できない急騰は短命の可能性。背取れる場面まで様子見。'
    elif regime == 'trend':
        reason = '損切り根拠が定まらない場面でブレイク追いはしない。深い押しまで待つ。'
    else:
        reason = '材料が揃ってない場面でエントリーは設計が破綻する。確度上がるまで様子見。'

    new_assistant = (
        f"{reason}\n\n"
        f"【スタンス】見送り"
    )

    return {
        'messages': [
            {'role': 'system', 'content': SYS_PROMPT},
            {'role': 'user', 'content': build_user_prompt(regime, date_str, materials)},
            {'role': 'assistant', 'content': new_assistant},
        ],
        'meta': {
            'source': 'failure_to_teacher_label_1',
            'original_signal_ts': signal.get('ts'),
            'original_signal': signal.get('signal', {}).get('signal'),
            'corrected_to': 'no_trade',
        },
    }


def convert_failures(model_version: str) -> int:
    """失敗ケース → 教師データ変換"""
    signals = load_signals(model_version)
    labels = load_labels(model_version)
    if not labels:
        print(f"⚠️ labels_{model_version}.jsonl が空、 変換するものなし")
        return 0

    out_file = HERE / "teacher" / f"teacher_{model_version}.jsonl"
    out_file.parent.mkdir(exist_ok=True)

    converted = 0
    skipped = 0
    rules_review = []
    notes = []

    with open(out_file, 'w', encoding='utf-8') as f:
        for signal in signals:
            ts = signal.get('ts', '')
            label = labels.get(ts)
            if not label:
                continue
            label_list = label.get('labels', [])
            if not label_list:
                continue

            # label_1: 危ない場面で「やる」 → no_trade教師化 (主要変換)
            if 1 in label_list:
                teacher = label_1_to_no_trade(signal)
                f.write(json.dumps(teacher, ensure_ascii=False) + '\n')
                converted += 1

            # label_2: 強制ストップバグ → ルール見直し対象 (rules_reviewに記録)
            if 2 in label_list:
                rules_review.append({
                    'signal_ts': ts,
                    'force_stop': signal.get('force_stop', {}),
                    'free_text': label.get('free_text', ''),
                })

            # label_3, 4: ループ/崩壊 → 学習設定見直し (個別教師化はしない)
            if 3 in label_list or 4 in label_list:
                notes.append(f"label_{3 if 3 in label_list else 4}: {ts}")
                skipped += 1

            # label_5: 攻めるべき場面で見送った → 個別判定必要、 教師化は次サイクル
            if 5 in label_list:
                notes.append(f"label_5 (offensive correction needed): {ts}")
                skipped += 1

            # label_6, 7: RR系 → 集計のみ、 教師化なし
            if 6 in label_list or 7 in label_list:
                pass

            # label_8: その他テキスト → 集計のみ
            if 8 in label_list:
                notes.append(f"label_8 (free_text): {label.get('free_text', '')[:80]}")

    # ルール見直し対象を別ファイル
    if rules_review:
        review_file = HERE / "teacher" / f"stop_rules_review_{model_version}.jsonl"
        with open(review_file, 'w', encoding='utf-8') as f:
            for r in rules_review:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')

    # サマリー
    print(f"=== 教師データ変換 (model={model_version}) ===")
    print(f"  教師化件数: {converted}")
    print(f"  スキップ (個別判定要 or 集計のみ): {skipped}")
    print(f"  ルール見直し対象: {len(rules_review)}件")
    print(f"  出力: teacher/teacher_{model_version}.jsonl")
    if notes:
        print(f"  メモ (先頭5件):")
        for n in notes[:5]:
            print(f"    - {n}")

    return converted


if __name__ == "__main__":
    model_version = _load_config_value('model_version', 'v6')
    convert_failures(model_version)
