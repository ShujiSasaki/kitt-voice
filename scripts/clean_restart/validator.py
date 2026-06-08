"""
R50 Round 1合意済 会議運営Validator (system code/script)
- Gemini Must Fix第11項目反映 (スロット構造遵守検証)
- 7検証項目すべて実装
- 並列送信禁止チェック (Shuji 14発目)
- Max Round制限なし (Shuji 15発目で撤回)
"""
import re
from dataclasses import dataclass


REQUIRED_TAG_PATTERNS = [
    (r"\[(GPT|Gemini|Claude)-Verify:", "Verify Token"),
    (r"\[NextActor:", "NextActor"),
    (r"\[EndTime-JST:", "EndTime-JST"),
    (r"\[is_shuji_represented:\s*false\]", "is_shuji_represented:false"),
    (r"\[no_proxy_violation:\s*true\]", "no_proxy_violation:true"),
]

PROXY_VIOLATION_PATTERNS = [
    r"Shujiさんなら",
    r"Shujiの意図",
    r"Shujiの代弁",
    r"Shujiが認める",
    r"Shujiさんが考える",
    r"Shujiさんは納得",
    r"Shujiさん.{0,10}承認.{0,5}得",
]

SLOT_STRUCTURE_PATTERNS = [
    (r"###\s*1\.\s*自身の意見", "Slot 1 自意見"),
    (r"###\s*2\.\s*前走者発言への監査", "Slot 2 監査"),
]

RELAY_ORDER = ["GPT", "Gemini", "SpeakingClaude"]


@dataclass
class ValidationResult:
    passed: bool
    violations: list


def check_verbatim_match(original: str, transmitted: str) -> ValidationResult:
    """Item 1: verbatim一致 chunk比較"""
    orig = original.strip()
    trans = transmitted.strip()
    if orig == trans:
        return ValidationResult(passed=True, violations=[])
    return ValidationResult(passed=False, violations=[f"verbatim mismatch (orig:{len(orig)} chars / trans:{len(trans)} chars)"])


def check_required_tags(text: str) -> ValidationResult:
    """Item 2: 必須タグ存在確認"""
    missing = []
    for pattern, label in REQUIRED_TAG_PATTERNS:
        if not re.search(pattern, text):
            missing.append(label)
    return ValidationResult(passed=(len(missing) == 0), violations=missing)


def check_proxy_violation(text: str) -> ValidationResult:
    """Item 3: proxy violation検出"""
    hits = []
    for pattern in PROXY_VIOLATION_PATTERNS:
        for m in re.finditer(pattern, text):
            hits.append(m.group(0))
    return ValidationResult(passed=(len(hits) == 0), violations=hits)


def check_full_share(speech_log: list) -> ValidationResult:
    """Item 4: 未共有検出 - 各発言が3者全員に届いたか"""
    missing = []
    for s in speech_log:
        speaker = s.get('speaker', '')
        recipients = set(s.get('recipients', []))
        expected = {"GPT", "Gemini", "SpeakingClaude"} - {speaker}
        if expected - recipients:
            missing.append(f"{speaker} speech missing for {sorted(expected - recipients)}")
    return ValidationResult(passed=(len(missing) == 0), violations=missing)


def check_relay_order(speaker_sequence: list) -> ValidationResult:
    """Item 5: 順番飛ばし検出"""
    violations = []
    for i in range(1, len(speaker_sequence)):
        prev_speaker = speaker_sequence[i-1]
        curr_speaker = speaker_sequence[i]
        if prev_speaker not in RELAY_ORDER or curr_speaker not in RELAY_ORDER:
            continue
        prev_idx = RELAY_ORDER.index(prev_speaker)
        curr_idx = RELAY_ORDER.index(curr_speaker)
        expected_curr = (prev_idx + 1) % len(RELAY_ORDER)
        if curr_idx != expected_curr:
            violations.append(f"順番飛ばし: {prev_speaker}→{curr_speaker} (expected {RELAY_ORDER[expected_curr]})")
    return ValidationResult(passed=(len(violations) == 0), violations=violations)


def check_speak_and_audit(text: str) -> ValidationResult:
    """Item 6 + 7: 発言+監査両方実施 + スロット構造遵守 (Gemini Must Fix第11項目)"""
    missing = []
    for pattern, label in SLOT_STRUCTURE_PATTERNS:
        if not re.search(pattern, text):
            missing.append(f"missing {label} section")
    return ValidationResult(passed=(len(missing) == 0), violations=missing)


def check_no_parallel_send(transmission_log: list) -> ValidationResult:
    """並列送信禁止チェック (Shuji 14発目)"""
    violations = []
    timestamps_by_speaker = {}
    for t in transmission_log:
        sender = t.get('sender', '')
        recipient = t.get('recipient', '')
        ts = t.get('timestamp', 0)
        key = (sender, ts)
        if key in timestamps_by_speaker and timestamps_by_speaker[key] != recipient:
            violations.append(f"並列送信検出: {sender}@{ts} → {timestamps_by_speaker[key]} & {recipient}")
        timestamps_by_speaker[key] = recipient
    return ValidationResult(passed=(len(violations) == 0), violations=violations)


def validate_speech(text: str, speaker: str, prev_speaker: str = None) -> dict:
    """発言1件への総合検証"""
    results = {
        "tags": check_required_tags(text),
        "proxy_violation": check_proxy_violation(text),
        "slot_structure": check_speak_and_audit(text),
    }
    all_passed = all(r.passed for r in results.values())
    return {
        "speaker": speaker,
        "all_passed": all_passed,
        "results": {k: {"passed": v.passed, "violations": v.violations} for k, v in results.items()},
    }


ABNORMAL_NOTIFICATION_CONDITIONS = {
    1: "consensus_reached",
    2: "discussion_deadlock",
    3: "validator_error",
    4: "watchdog_human_required",
    5: "technical_error_3x",
    6: "cost_time_stall_limit",
}


def get_abnormal_condition_label(code: int) -> str:
    return ABNORMAL_NOTIFICATION_CONDITIONS.get(code, "unknown")


def self_test():
    """validator.py 自己テスト"""
    passed = 0
    failed = 0

    sample_valid = """
### 1. 自身の意見・回答セクション
Q1賛成。

### 2. 前走者発言への監査・批判セクション
GPT発言 Must Fixなし。

[GPT-Verify: R50-ROUND1-SLOT1-TEST]
[NextActor: Gemini]
[EndTime-JST: 12:00:00]
[is_shuji_represented: false]
[no_proxy_violation: true]
"""
    r = validate_speech(sample_valid, "GPT")
    if r["all_passed"]:
        passed += 1
        print("PASS: valid speech")
    else:
        failed += 1
        print(f"FAIL: valid speech - {r['results']}")

    sample_proxy = sample_valid + "\nShujiさんなら賛成と判断する"
    r = validate_speech(sample_proxy, "GPT")
    if not r["results"]["proxy_violation"]["passed"]:
        passed += 1
        print("PASS: proxy violation detected")
    else:
        failed += 1
        print("FAIL: proxy violation NOT detected")

    sample_no_slot = """
GPT発言。
[GPT-Verify: TEST]
[NextActor: Gemini]
[EndTime-JST: 12:00:00]
[is_shuji_represented: false]
[no_proxy_violation: true]
"""
    r = validate_speech(sample_no_slot, "GPT")
    if not r["results"]["slot_structure"]["passed"]:
        passed += 1
        print("PASS: slot structure violation detected")
    else:
        failed += 1
        print("FAIL: slot structure violation NOT detected")

    order_ok = check_relay_order(["GPT", "Gemini", "SpeakingClaude", "GPT"])
    if order_ok.passed:
        passed += 1
        print("PASS: relay order valid")
    else:
        failed += 1
        print(f"FAIL: relay order - {order_ok.violations}")

    order_bad = check_relay_order(["GPT", "SpeakingClaude", "Gemini"])
    if not order_bad.passed:
        passed += 1
        print("PASS: relay order violation detected")
    else:
        failed += 1
        print("FAIL: relay order violation NOT detected")

    print(f"\n=== SELF-TEST RESULT: {passed}/{passed+failed} PASSED ===")
    return failed == 0


if __name__ == "__main__":
    self_test()
