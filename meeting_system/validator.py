"""
validator — 発言検証 (7検証 + 追加インスピレーション + X風スレッド検出)

3者合意 (loop2 R50 Round 1 Must Fix第11項目 + R50-CONSENSUS-LOGIC):
- 既存7検証 (verbatim / 必須タグ / proxy / 共有 / 順番 / 監査 / スロット)
- 「追加インスピレーション」 1行物理義務化検出 (前々議題合意)
- 「[💬 監査ログ]」 スレッド検出 (前議題合意)
- consensus_candidate / overall_consensus_candidate 抽出
"""
from __future__ import annotations

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

INSPIRATION_PATTERN = r"追加インスピレーション"
THREAD_BUTTON_PATTERN = r"\[💬\s*監査ログ"

RELAY_ORDER = ["gpt", "gemini", "claude"]


@dataclass
class ValidationResult:
    passed: bool
    violations: list


def check_required_tags(text: str) -> ValidationResult:
    missing = [label for pat, label in REQUIRED_TAG_PATTERNS if not re.search(pat, text)]
    return ValidationResult(passed=(len(missing) == 0), violations=missing)


def check_proxy_violation(text: str) -> ValidationResult:
    hits = []
    for pat in PROXY_VIOLATION_PATTERNS:
        for m in re.finditer(pat, text):
            hits.append(m.group(0))
    return ValidationResult(passed=(len(hits) == 0), violations=hits)


def check_slot_structure(text: str) -> ValidationResult:
    missing = [label for pat, label in SLOT_STRUCTURE_PATTERNS if not re.search(pat, text)]
    return ValidationResult(passed=(len(missing) == 0), violations=missing)


def check_inspiration(text: str) -> ValidationResult:
    if re.search(INSPIRATION_PATTERN, text):
        return ValidationResult(passed=True, violations=[])
    return ValidationResult(passed=False, violations=["『追加インスピレーション』1行が見つからない"])


def check_relay_order(speakers: list[str]) -> ValidationResult:
    violations = []
    for i in range(1, len(speakers)):
        prev_a = speakers[i - 1].lower()
        cur_a = speakers[i].lower()
        if prev_a not in RELAY_ORDER or cur_a not in RELAY_ORDER:
            continue
        prev_idx = RELAY_ORDER.index(prev_a)
        cur_idx = RELAY_ORDER.index(cur_a)
        expected = (prev_idx + 1) % len(RELAY_ORDER)
        if cur_idx != expected:
            violations.append(
                f"順番違反: {speakers[i - 1]}→{speakers[i]} (expected {RELAY_ORDER[expected]})"
            )
    return ValidationResult(passed=(len(violations) == 0), violations=violations)


def check_no_parallel_send(transmission_log: list[dict]) -> ValidationResult:
    violations = []
    seen: dict = {}
    for t in transmission_log:
        sender = t.get("sender", "")
        recipient = t.get("recipient", "")
        ts = t.get("timestamp", 0)
        key = (sender, ts)
        if key in seen and seen[key] != recipient:
            violations.append(
                f"並列送信: {sender}@{ts} → {seen[key]} & {recipient}"
            )
        seen[key] = recipient
    return ValidationResult(passed=(len(violations) == 0), violations=violations)


CONSENSUS_RE = re.compile(
    r"consensus_candidate\s*[:=]\s*(true|false|blocked|external_wait)",
    re.IGNORECASE,
)
OVERALL_RE = re.compile(
    r"overall_consensus_candidate\s*[:=]\s*(true|false|blocked|external_wait)",
    re.IGNORECASE,
)

# R59 Q3: 3値化 (Gemini/GPT/発言Claude R5合意)
CONSENSUS_VALUES = {"true", "false", "blocked", "external_wait"}


def extract_consensus_candidate(text: str) -> bool:
    """legacy bool API (true/false以外は false扱い)"""
    v = extract_consensus_value(text)
    return v == "true"


# 見出し省略形式fallback (2026-06-12 実害: GPTが新規会話で
# 「consensus_candidate判定\n\ntrue」 とコロン無しで書き、毎回falseに化けて
# 内容合意済みでも正式成立せず max_loops まで空回りした)
SECTION_JUDGE_RE = re.compile(r"consensus_candidate\s*判定", re.IGNORECASE)
VALUE_LINE_RE = re.compile(
    r"^\s*[-*・]?\s*(true|false|blocked|external_wait)\b", re.IGNORECASE)


def extract_consensus_value(text: str) -> str:
    """R59 Q3: 3値返却 true / false / blocked / external_wait"""
    m = OVERALL_RE.search(text)
    if m:
        return m.group(1).lower()
    matches = CONSENSUS_RE.findall(text)
    if matches:
        # true があれば true、 次に blocked、 next external_wait、 最後 false
        norm = [v.lower() for v in matches]
        for priority in ("true", "blocked", "external_wait"):
            if priority in norm:
                return priority
        return "false"
    # fallback: 「consensus_candidate判定」見出し直後3行以内の単独値を採用
    sm = SECTION_JUDGE_RE.search(text)
    if sm:
        checked = 0
        for ln in text[sm.end():].splitlines():
            s = ln.strip()
            if not s:
                continue
            vm = VALUE_LINE_RE.match(s)
            if vm:
                return vm.group(1).lower()
            checked += 1
            if checked >= 3:
                break
    return "false"


def extract_thread_audits(text: str) -> list[dict]:
    audits: list[dict] = []
    for m in re.finditer(
        r"target_msg_id\s*[:=]\s*\"?([\w\-]+)\"?[^,]*?kind\s*[:=]\s*\"?(\w+)\"?",
        text,
    ):
        audits.append({"target_msg_id": m.group(1), "kind": m.group(2)})
    return audits


def validate_speech(text: str, speaker: str) -> dict:
    results = {
        "tags": check_required_tags(text),
        "proxy_violation": check_proxy_violation(text),
        "slot_structure": check_slot_structure(text),
        "inspiration": check_inspiration(text),
    }
    return {
        "speaker": speaker,
        "all_passed": all(r.passed for r in results.values()),
        "results": {
            k: {"passed": v.passed, "violations": v.violations}
            for k, v in results.items()
        },
        "consensus_candidate": extract_consensus_candidate(text),  # legacy bool
        "consensus_value": extract_consensus_value(text),  # R59 Q3: 3値
        "thread_audits": extract_thread_audits(text),
    }


# R59 Q2: pwa_summary抽出
import re as _re_q2  # noqa
PWA_SUMMARY_RE = _re_q2.compile(
    r"<pwa_summary>(.*?)</pwa_summary>", _re_q2.DOTALL | _re_q2.IGNORECASE,
)


def extract_pwa_summary(text: str, fallback_max: int = 200) -> str:
    """R59 Q2: <pwa_summary>...</pwa_summary> 抽出 (なければ body先頭200字 fallback)"""
    m = PWA_SUMMARY_RE.search(text or "")
    if m:
        s = m.group(1).strip()
        if s:
            return s[:fallback_max]
    fallback = (text or "").strip().splitlines()
    head = " ".join(ln.strip() for ln in fallback[:3] if ln.strip())
    return head[:fallback_max]


ABNORMAL_NOTIFICATION_CONDITIONS = {
    1: "consensus_reached",
    2: "discussion_deadlock",
    3: "validator_error",
    4: "watchdog_human_required",
    5: "technical_error_3x",
    6: "cost_time_stall_limit",
}


def self_test() -> bool:
    passed, failed = 0, 0
    sample_ok = """### 1. 自身の意見・回答セクション
本案賛成。 consensus_candidate: true

### 2. 前走者発言への監査・批判セクション
Must Fixなし。

追加インスピレーション: テスト

[GPT-Verify: TEST]
[NextActor: Gemini]
[EndTime-JST: 12:00:00]
[is_shuji_represented: false]
[no_proxy_violation: true]
"""
    r = validate_speech(sample_ok, "gpt")
    if r["all_passed"] and r["consensus_candidate"]:
        passed += 1; print("PASS: valid speech with inspiration + consensus")
    else:
        failed += 1; print(f"FAIL: valid speech - {r['results']}")

    sample_no_insp = sample_ok.replace("追加インスピレーション: テスト", "")
    r = validate_speech(sample_no_insp, "gpt")
    if not r["results"]["inspiration"]["passed"]:
        passed += 1; print("PASS: missing inspiration detected")
    else:
        failed += 1; print("FAIL: missing inspiration NOT detected")

    sample_proxy = sample_ok + "\nShujiさんなら賛成と判断する"
    r = validate_speech(sample_proxy, "gpt")
    if not r["results"]["proxy_violation"]["passed"]:
        passed += 1; print("PASS: proxy violation detected")
    else:
        failed += 1; print("FAIL: proxy violation NOT detected")

    order_ok = check_relay_order(["gpt", "gemini", "claude", "gpt"])
    if order_ok.passed:
        passed += 1; print("PASS: relay order valid")
    else:
        failed += 1; print(f"FAIL: relay - {order_ok.violations}")

    order_bad = check_relay_order(["gpt", "claude", "gemini"])
    if not order_bad.passed:
        passed += 1; print("PASS: relay order violation detected")
    else:
        failed += 1; print("FAIL: relay violation NOT detected")

    # 見出し省略形式fallback (2026-06-12 GPT実害対応)
    cases = [
        ("...本文...\nconsensus_candidate判定\n\ntrue\n\n次のセクション", "true"),
        ("consensus_candidate判定\n\n説明が先\nfalse", "false"),
        ("consensus_candidate判定\n\nexternal_wait (理由)", "external_wait"),
        ("consensus_candidate: true が優先", "true"),
        ("判定見出しが無い本文だけ", "false"),
        ("consensus_candidate判定\n\n説明1\n説明2\n説明3\n説明4\ntrue", "false"),  # 3行超は不採用
    ]
    for text, want in cases:
        got = extract_consensus_value(text)
        if got == want:
            passed += 1; print(f"PASS: 見出し省略fallback ({want})")
        else:
            failed += 1; print(f"FAIL: 見出し省略fallback want={want} got={got}")

    print(f"=== validator self_test: {passed}/{passed + failed} ===")
    return failed == 0


if __name__ == "__main__":
    ok = self_test()
    raise SystemExit(0 if ok else 1)
