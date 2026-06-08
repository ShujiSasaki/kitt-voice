# Validator (会議監査system code) 仕様

事務Claude/orchestratorの動作を機械検証する **system code/script** 。 思考機能なし、 純粋な検証ロジックのみ。

## 配置
`scripts/clean_restart/validator.py` (将来実装、 Python)

## 検証項目 (7項目、 Gemini Must Fix第11項目反映)

### 1. verbatim一致
- Shujiさん発言と 事務Claudeが GPTに転送した内容の chunk比較
- 3者発言と 事務Claudeが次AIに転送した内容の chunk比較
- 文字列完全一致 (改行・スペース含む)

```python
def check_verbatim_match(original: str, transmitted: str) -> bool:
    return original.strip() == transmitted.strip()
```

### 2. 必須タグ確認
- `[<AI>-Verify: ...]`
- `[NextActor: ...]`
- `[EndTime-JST: HH:MM:SS]`
- `[is_shuji_represented: false]`
- `[no_proxy_violation: true]`

```python
import re
REQUIRED_TAGS = [
    r'\[(GPT|Gemini|Claude)-Verify:',
    r'\[NextActor:',
    r'\[EndTime-JST:',
    r'\[is_shuji_represented:',
    r'\[no_proxy_violation:'
]

def check_required_tags(text: str) -> list[str]:
    missing = []
    for pattern in REQUIRED_TAGS:
        if not re.search(pattern, text):
            missing.append(pattern)
    return missing
```

### 3. proxy violation検出
- Shuji代弁パターン:
  - 「Shujiさんなら」
  - 「Shujiの意図」
  - 「Shujiの代弁」
  - 「Shujiが認める」
  - 「Shujiさんが考える」
  - 「Shujiさんは納得」

```python
PROXY_PATTERNS = [
    r"Shujiさんなら",
    r"Shujiの意図",
    r"Shujiの代弁",
    r"Shujiが認める",
    r"Shujiさんが考える",
    r"Shujiさんは納得",
    r"Shujiさん.{0,10}承認.{0,5}得",
]

def check_proxy_violation(text: str) -> list[str]:
    hits = []
    for pattern in PROXY_PATTERNS:
        m = re.search(pattern, text)
        if m:
            hits.append(m.group(0))
    return hits
```

### 4. 未共有検出
- 各Shujiさん発言が GPT/Gemini/発言Claude 全員に転送されたか log解析
- 各GPT発言が Gemini/発言Claude に転送されたか
- 各Gemini発言が GPT/発言Claude に転送されたか
- 各発言Claude発言が GPT/Gemini に転送されたか

```python
def check_full_share(speech_log: list[dict]) -> list[str]:
    """各発言が3者全員に届いたか確認"""
    missing = []
    for s in speech_log:
        recipients = s.get('recipients', [])
        expected = {'GPT', 'Gemini', 'SpeakingClaude'} - {s['speaker']}
        actual = set(recipients)
        if expected != actual:
            missing.append(f"{s['speaker']}'s speech missing for {expected - actual}")
    return missing
```

### 5. 順番飛ばし検出
- 順次リレー (GPT→Gemini→発言Claude→GPT) の順序遵守

```python
RELAY_ORDER = ['GPT', 'Gemini', 'SpeakingClaude']

def check_relay_order(speakers: list[str]) -> list[str]:
    """state.jsonのnext_actor履歴を検証"""
    violations = []
    for i in range(1, len(speakers)):
        prev_idx = RELAY_ORDER.index(speakers[i-1])
        curr_idx = RELAY_ORDER.index(speakers[i])
        expected_curr = (prev_idx + 1) % 3
        if curr_idx != expected_curr:
            violations.append(f"順番飛ばし: {speakers[i-1]} → {speakers[i]}")
    return violations
```

### 6. 発言+監査両方実施検出 (Shuji 13発目)
- 各発言で「自意見」 + 「他者監査」 両方が含まれているか

```python
def check_speak_and_audit(text: str) -> dict:
    """スロット1 (自意見) とスロット2 (他者監査) 両方を確認"""
    has_section_1 = bool(re.search(r'###\s*1\.\s*自身の意見', text))
    has_section_2 = bool(re.search(r'###\s*2\.\s*前走者発言への監査', text))
    return {
        'section_1_self_opinion': has_section_1,
        'section_2_audit': has_section_2,
        'both_present': has_section_1 and has_section_2
    }
```

### 7. スロット構造遵守検証 (Gemini Must Fix第11項目)
- `### 1. 自身の意見・回答セクション` 見出し存在
- `### 2. 前走者発言への監査・批判セクション` 見出し存在
- 上記6番と統合

## 異常検知時の動作

1. Validator → 異常log記録
2. 事務Claudeへ「該当発言転送停止」 指示
3. Shujiさんへ通知 (Email/KITT音声/Claude Codeチャット)
4. orchestrator Watchdog発動
5. 該当AIへ「修正再送依頼」 自動送信 (Validator経由)

## 通知6条件への組み込み

異常通知6条件のうち、 Validator関連は:
- 3. Validator異常 (本仕様のいずれかの検証失敗時)
- 4. Watchdog HUMAN_REQUIRED (Validator異常が3回連続)

## 実装優先順位

Phase 0 (即時): 1, 2, 3 (verbatim/タグ/proxy) → 既存orchestrator_prototype.pyに組み込み
Phase 1: 4, 5 (未共有/順番飛ばし)
Phase 2: 6, 7 (スロット構造)
