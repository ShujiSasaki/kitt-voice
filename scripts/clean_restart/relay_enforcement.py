"""
R50 Round 1合意済 並列送信絶対禁止 + 順次リレー強制
- Shuji 14発目: 「だから並列に送るなと言ったでしょ」
- 送信前 lock取得 → 送信 → response受領 → 次AI送信
- 重複送信、 同時送信、 順番飛ばしの完全防止
"""
import json
import os
import time
from pathlib import Path
from contextlib import contextmanager


REPO_ROOT = Path(__file__).resolve().parents[2]
LOGS_DIR = REPO_ROOT / "logs"
RELAY_LOCK_FILE = LOGS_DIR / "relay.lock"
RELAY_HISTORY_FILE = LOGS_DIR / "relay_history.jsonl"

RELAY_ORDER = ["GPT", "Gemini", "SpeakingClaude"]

RELAY_LOCK_TIMEOUT_SEC = 600


class ParallelSendViolation(Exception):
    pass


class OrderViolation(Exception):
    pass


def get_next_actor(prev_speaker: str) -> str:
    if prev_speaker not in RELAY_ORDER:
        raise ValueError(f"unknown speaker: {prev_speaker}")
    idx = RELAY_ORDER.index(prev_speaker)
    return RELAY_ORDER[(idx + 1) % len(RELAY_ORDER)]


def _read_lock() -> dict | None:
    if not RELAY_LOCK_FILE.exists():
        return None
    try:
        return json.loads(RELAY_LOCK_FILE.read_text())
    except Exception:
        return None


def _is_stale(lock_data: dict) -> bool:
    age = time.time() - lock_data.get("acquired_at", 0)
    return age > RELAY_LOCK_TIMEOUT_SEC


@contextmanager
def relay_lock(sender: str, recipient: str):
    """送信前 lock取得。 既存lockあれば ParallelSendViolation raise (stale例外あり)"""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    existing = _read_lock()
    if existing and not _is_stale(existing):
        raise ParallelSendViolation(
            f"並列送信検出: 既存lock {existing['sender']}→{existing['recipient']} "
            f"(取得 {time.time() - existing['acquired_at']:.0f}秒前) / "
            f"新規送信要求 {sender}→{recipient}"
        )

    try:
        fd = os.open(str(RELAY_LOCK_FILE), os.O_CREAT | os.O_TRUNC | os.O_WRONLY)
        lock_data = {
            "sender": sender,
            "recipient": recipient,
            "acquired_at": time.time(),
        }
        os.write(fd, json.dumps(lock_data).encode('utf-8'))
        os.close(fd)
    except Exception as e:
        raise ParallelSendViolation(f"lock取得失敗: {e}")

    try:
        yield lock_data
    finally:
        try:
            RELAY_LOCK_FILE.unlink()
        except FileNotFoundError:
            pass


def verify_relay_order(sender: str, recipient: str, last_speaker: str = None) -> None:
    """順次リレー輪番 (GPT→Gemini→SpeakingClaude→GPT) 遵守確認"""
    if sender == "Shuji":
        if recipient != "GPT":
            raise OrderViolation(f"Shuji発言は必ずGPTのみ。 recipient={recipient}")
        return
    if last_speaker is None:
        return
    expected_sender = last_speaker
    if sender != expected_sender:
        raise OrderViolation(f"順番飛ばし: 期待={expected_sender} 実={sender}")
    expected_recipient = get_next_actor(sender)
    if recipient != expected_recipient:
        raise OrderViolation(f"順番飛ばし: 期待recipient={expected_recipient} 実={recipient}")


def log_transmission(sender: str, recipient: str, content_hash: str, content_len: int) -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "ts_jst": time.strftime("%Y-%m-%d %H:%M:%S JST", time.localtime()),
        "ts_epoch": time.time(),
        "sender": sender,
        "recipient": recipient,
        "content_hash": content_hash,
        "content_len": content_len,
    }
    with open(RELAY_HISTORY_FILE, 'a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def transmit(sender: str, recipient: str, content: str, last_speaker: str = None, send_fn=None) -> dict:
    """順次リレー強制 transmit 統合関数"""
    import hashlib
    verify_relay_order(sender, recipient, last_speaker)
    with relay_lock(sender, recipient) as lock_data:
        if send_fn:
            send_fn(recipient, content)
        content_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()[:16]
        log_transmission(sender, recipient, content_hash, len(content))
        return {
            "sender": sender,
            "recipient": recipient,
            "content_hash": content_hash,
            "transmitted_at": lock_data["acquired_at"],
        }


def self_test():
    passed = 0
    failed = 0

    if get_next_actor("GPT") == "Gemini":
        passed += 1
        print("PASS: GPT→Gemini")
    else:
        failed += 1
    if get_next_actor("Gemini") == "SpeakingClaude":
        passed += 1
        print("PASS: Gemini→SpeakingClaude")
    else:
        failed += 1
    if get_next_actor("SpeakingClaude") == "GPT":
        passed += 1
        print("PASS: SpeakingClaude→GPT (Round完)")
    else:
        failed += 1

    try:
        verify_relay_order("Shuji", "GPT")
        passed += 1
        print("PASS: Shuji→GPT allowed")
    except OrderViolation:
        failed += 1
        print("FAIL: Shuji→GPT")

    try:
        verify_relay_order("Shuji", "Gemini")
        failed += 1
        print("FAIL: Shuji→Gemini should have raised")
    except OrderViolation:
        passed += 1
        print("PASS: Shuji→Gemini correctly blocked")

    try:
        verify_relay_order("GPT", "SpeakingClaude", last_speaker="GPT")
        failed += 1
        print("FAIL: GPT→SpeakingClaude (skip Gemini) should have raised")
    except OrderViolation:
        passed += 1
        print("PASS: 順番飛ばし GPT→SpeakingClaude blocked")

    try:
        with relay_lock("GPT", "Gemini"):
            try:
                with relay_lock("Gemini", "SpeakingClaude"):
                    failed += 1
                    print("FAIL: 並列送信 should have raised")
            except ParallelSendViolation:
                passed += 1
                print("PASS: 並列送信 検出 (nested lock blocked)")
    except Exception as e:
        failed += 1
        print(f"FAIL outer lock: {e}")

    if not RELAY_LOCK_FILE.exists():
        passed += 1
        print("PASS: lock auto-released")
    else:
        failed += 1
        RELAY_LOCK_FILE.unlink()

    print(f"\n=== SELF-TEST RESULT: {passed}/{passed+failed} PASSED ===")
    return failed == 0


if __name__ == "__main__":
    self_test()
