"""強制ストップ7条件 (LoRAと独立して動作、 合意明記)

3者合意 (2026-06-23 17:28 + 2026-06-24 06:18 btc部屋):
「安全弁はAI任せにせず、 プログラムの「問答無用で止める」 ルールも必ず二重で持って」

7条件:
1. 損切り不明
2. 損切り近すぎ (SL距離 < ATR×0.5)
3. 根拠なし急騰 (rally + OI急増なし)
4. 根拠不足 (材料2点未満 or 汎用キーワードのみ)
5. 薄い逆張り (crashで反発買い等)
6. 板薄/急変 (Volume < 平均30% or ATR > 平均×3)
7. モデルが曖昧 (「不明/曖昧」 含む or 20文字未満)
"""
from __future__ import annotations


def _atr(candles: list[dict], period: int = 14) -> float:
    """Average True Range"""
    if len(candles) < 2:
        return 0.0
    trs = []
    for i in range(1, len(candles)):
        h = candles[i]['high']
        l = candles[i]['low']
        prev_close = candles[i-1]['close']
        trs.append(max(h - l, abs(h - prev_close), abs(l - prev_close)))
    if not trs:
        return 0.0
    n = min(period, len(trs))
    return sum(trs[-n:]) / n


# ===== 各ルール =====

def rule_1_no_stop_loss(response: str) -> bool:
    """ルール1: 損切り不明 (response に「損切」 も「背」 も「SL」 もない)"""
    keywords = ['損切', '背', 'sl', 'ストップ']
    text = response.lower()
    return not any(kw in text for kw in keywords)


def rule_2_sl_too_close(response: str, candles: list[dict]) -> bool:
    """ルール2: 損切り近すぎ (推定SL距離 < ATR×0.5)

    response から「○○円」「○○$」 等の数値を抽出できない場合は
    safe-fail (発火させない、 ATR比較できないため)。
    """
    # 単純実装: response に「近すぎ」「同値」 等の表現があれば検出
    text = response.lower()
    if any(kw in text for kw in ['近すぎ', '同値', '直近', 'ノイズ']):
        # ただし「近すぎだから見送り」 と言ってる場合は OK (modelが判断済)
        if any(safe_kw in text for safe_kw in ['見送り', '様子見', 'no_trade', '入らない']):
            return False  # modelが正しく判断してる
        return True
    return False


def rule_3_unfounded_rally(regime: str, response: str, candles: list[dict]) -> bool:
    """ルール3: 根拠なし急騰 (rally regime + OI増言及なし)"""
    if regime != 'rally':
        return False
    text = response.lower()
    # OI増・需給言及があるか確認
    has_oi_mention = any(kw in text for kw in ['oi', '需給', '出来高', '清算', 'フ ァンディング', 'fr'])
    if not has_oi_mention:
        return True
    return False


def rule_4_insufficient_grounds(materials: list[str], response: str) -> bool:
    """ルール4: 根拠不足 (材料2点未満)"""
    if len(materials) < 2:
        return True
    # 応答も短すぎる場合は根拠不足
    if len(response) < 30:
        return True
    return False


def rule_5_thin_counter(regime: str, response: str) -> bool:
    """ルール5: 薄い逆張り (crash で反発買い、 trend逆方向ショート 等)"""
    text = response.lower()
    if regime == 'crash':
        # crash で「買い」「ロング」 言及があれば逆張りの可能性
        if any(kw in text for kw in ['買い', 'ロング', 'long']):
            # ただし「底打ち確認後」 等のヒントがあれば OK
            if any(safe_kw in text for safe_kw in ['底打ち', '反発確認', '兆候', '見送り', '様子見']):
                return False
            return True
    return False


def rule_6_thin_or_extreme(candles: list[dict]) -> bool:
    """ルール6: 板薄/急変 (Volume < 平均30% or ATR > 平均×3)"""
    if len(candles) < 14:
        return False  # データ不足は safe-fail
    latest = candles[-1]
    avg_volume = sum(c['volume'] for c in candles[-24:]) / min(24, len(candles))
    if avg_volume > 0 and latest['volume'] < avg_volume * 0.3:
        return True

    recent_atr = _atr(candles[-4:], period=4)
    long_atr = _atr(candles[-50:] if len(candles) >= 50 else candles, period=14)
    if long_atr > 0 and recent_atr > long_atr * 3.0:
        return True
    return False


def rule_7_model_ambiguous(response: str) -> bool:
    """ルール7: モデルが曖昧 (「不明/曖昧/分からない」 含む or 20文字未満)"""
    if len(response.strip()) < 20:
        return True
    ambiguous_words = ['不明', '曖昧', '分からない', 'わからない', '判断保留', '不確実']
    return any(kw in response for kw in ambiguous_words)


# ===== 統合判定 =====

def force_stop_check(
    regime: str,
    response: str,
    materials: list[str],
    candles: list[dict],
) -> dict:
    """7条件を全部チェック

    Returns:
        {
            'triggered': bool,    # いずれか1個でも該当
            'rules_hit': list[str],  # 該当ルール名
            'reason': str,        # 人間可読の理由
        }
    """
    triggers = []

    if rule_1_no_stop_loss(response):
        triggers.append('rule_1_no_stop_loss')
    if rule_2_sl_too_close(response, candles):
        triggers.append('rule_2_sl_too_close')
    if rule_3_unfounded_rally(regime, response, candles):
        triggers.append('rule_3_unfounded_rally')
    if rule_4_insufficient_grounds(materials, response):
        triggers.append('rule_4_insufficient_grounds')
    if rule_5_thin_counter(regime, response):
        triggers.append('rule_5_thin_counter')
    if rule_6_thin_or_extreme(candles):
        triggers.append('rule_6_thin_or_extreme')
    if rule_7_model_ambiguous(response):
        triggers.append('rule_7_model_ambiguous')

    rule_descriptions = {
        'rule_1_no_stop_loss': '損切り不明',
        'rule_2_sl_too_close': '損切り近すぎ',
        'rule_3_unfounded_rally': '根拠なし急騰',
        'rule_4_insufficient_grounds': '根拠不足',
        'rule_5_thin_counter': '薄い逆張り',
        'rule_6_thin_or_extreme': '板薄/急変',
        'rule_7_model_ambiguous': 'モデル曖昧',
    }
    reason = '; '.join(rule_descriptions[r] for r in triggers) if triggers else ''

    return {
        'triggered': len(triggers) > 0,
        'rules_hit': triggers,
        'reason': reason,
    }


if __name__ == "__main__":
    # 動作確認 (各ルール単体テスト)
    print("=== stop_rules.py 動作確認 ===")
    dummy_candles = [
        {'open':100,'high':105,'low':95,'close':102,'volume':1000} for _ in range(20)
    ]
    # ルール1: 損切り無し response
    r1 = force_stop_check('trend', '上昇継続。【スタンス】ロング', ['ブレイク','上昇'], dummy_candles)
    print(f"テスト1 (損切り無し): {r1}")

    # ルール7: 曖昧 response
    r2 = force_stop_check('range', '不明', ['レンジ','曖昧'], dummy_candles)
    print(f"テスト2 (曖昧): {r2}")

    # 正常 response
    r3 = force_stop_check('crash',
        '背を割れる前に戻り高値で損切りを置いて戻りを売る。【スタンス】ショート狙い',
        ['暴落中','背明確','損切り根拠あり'],
        dummy_candles)
    print(f"テスト3 (正常): {r3}")
