"""信号生成: 【スタンス】抽出 → long/short/no_trade/force_stopped

3者合意 (2026-06-24): 強制ストップ7条件は常に優先 (force_stopped が勝つ)。
LoRA応答の【スタンス】から方向判定。 不明はデフォルト no_trade (安全寄り)。
"""
from __future__ import annotations

import re


# ===== 抽出 =====

def extract_stance(response: str) -> str:
    """response から「【スタンス】〇〇」 を抽出 (見つからなければ空文字)"""
    # 「【スタンス】」 以降の改行までを取得
    match = re.search(r'【スタンス】\s*(.+?)(?:\n|$)', response)
    if match:
        return match.group(1).strip()
    # 別パターン: 「スタンス:」「方針:」 等
    for pattern in [r'スタンス[::\s]+(.+?)(?:\n|$)', r'方針[::\s]+(.+?)(?:\n|$)']:
        m = re.search(pattern, response)
        if m:
            return m.group(1).strip()
    return ''


# ===== 信号判定 =====

NO_TRADE_KEYWORDS = ['no_trade', '見送り', '様子見', 'ノートレ', 'スキップ',
                     '入らない', '入れない', '保留', '回避', '撤退']
LONG_KEYWORDS = ['ロング', '買い', 'long', 'ドテンロング', '押し目買い',
                 '反発買い']
SHORT_KEYWORDS = ['ショート', '売り', 'short', 'ドテンショート', '戻り売り',
                  '空売り']


def classify_stance(stance: str) -> str:
    """stance文字列から方向判定

    優先順位 (合意の安全寄りデフォルト):
    1. no_trade keyword → no_trade
    2. short keyword → short
    3. long keyword → long
    4. 不明 → no_trade
    """
    if not stance:
        return 'no_trade'
    s = stance.lower()

    # no_trade を最優先 (安全寄り)
    if any(kw in s for kw in NO_TRADE_KEYWORDS):
        return 'no_trade'

    # short/long の判定
    has_short = any(kw in s for kw in SHORT_KEYWORDS)
    has_long = any(kw in s for kw in LONG_KEYWORDS)

    if has_short and has_long:
        # 両方含むのは曖昧 → 安全寄り
        return 'no_trade'
    if has_short:
        return 'short'
    if has_long:
        return 'long'
    return 'no_trade'  # 不明はデフォルト no_trade


def generate_signal(response: str, force_stop_result: dict) -> dict:
    """信号生成

    Args:
        response: LoRA応答テキスト
        force_stop_result: stop_rules.force_stop_check() の戻り値

    Returns:
        {
            'signal': 'long' | 'short' | 'no_trade' | 'force_stopped',
            'stance': str,           # 抽出した【スタンス】
            'classified_as': str,    # stance 単体の判定 (force_stop前)
            'force_stopped': bool,
            'rules_hit': list[str],
        }
    """
    stance = extract_stance(response)
    classified = classify_stance(stance)

    # 強制ストップが常に優先 (合意必須)
    if force_stop_result['triggered']:
        return {
            'signal': 'force_stopped',
            'stance': stance,
            'classified_as': classified,
            'force_stopped': True,
            'rules_hit': force_stop_result['rules_hit'],
        }

    return {
        'signal': classified,
        'stance': stance,
        'classified_as': classified,
        'force_stopped': False,
        'rules_hit': [],
    }


if __name__ == "__main__":
    print("=== signal_generator.py 動作確認 ===")

    # ケース1: 明確な long
    s1 = generate_signal(
        'danjerは押し目買いを狙う。【スタンス】ロング',
        {'triggered': False, 'rules_hit': [], 'reason': ''},
    )
    print(f"テスト1 (long): {s1}")

    # ケース2: no_trade
    s2 = generate_signal(
        '背がないので入らない。【スタンス】様子見',
        {'triggered': False, 'rules_hit': [], 'reason': ''},
    )
    print(f"テスト2 (no_trade): {s2}")

    # ケース3: force_stopped (LoRA は long言ってるが、 ルール1で止まる)
    s3 = generate_signal(
        'ロングしたい。【スタンス】ロング',  # 損切り無し
        {'triggered': True, 'rules_hit': ['rule_1_no_stop_loss'], 'reason': '損切り不明'},
    )
    print(f"テスト3 (force_stopped): {s3}")

    # ケース4: 曖昧 (default no_trade)
    s4 = generate_signal(
        '判断が難しい',  # 【スタンス】無し
        {'triggered': False, 'rules_hit': [], 'reason': ''},
    )
    print(f"テスト4 (空 stance → no_trade): {s4}")
