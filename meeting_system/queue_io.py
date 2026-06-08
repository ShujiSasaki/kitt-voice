"""
queue_io — Markdownキュー I/O (File Lock + Atomic Move + UTF-8/LF固定)

物理仕様 (3者合意):
- File Lock: fcntl.flock(LOCK_EX) で Race Condition物理防止
- Atomic Move: tempfile + os.replace で POSIX atomic保証 (同一FS)
- UTF-8 BOM無し / 改行 LF (\n) 固定
- msg_id = uuid.uuid4() で冪等性
- validator_log.jsonl 形式 (1行1件)
"""
from __future__ import annotations

import fcntl
import json
import os
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

JST = timezone(timedelta(hours=9))
ENC = "utf-8"
NEWLINE = "\n"

DEFAULT_BASE = Path("/Users/shuji/Desktop/kitt-voice/meeting_system")


@dataclass
class Message:
    msg_id: str
    sender: str
    body: str
    ts: str

    def to_block(self) -> str:
        return (
            f"\n<!-- MSG_ID: {self.msg_id} | SENDER: {self.sender} | TS: {self.ts} -->\n"
            f"{self.body.rstrip()}\n"
        )


def _lock_path(target: Path) -> Path:
    return target.with_suffix(target.suffix + ".lock")


def _now_jst() -> str:
    return datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")


def _queue_path(base: Path, queue_name: str) -> Path:
    return base / "queue" / f"{queue_name}.md"


def atomic_append(
    queue_name: str,
    content: str,
    sender: str,
    msg_id: Optional[str] = None,
    base: Path = DEFAULT_BASE,
) -> str:
    target = _queue_path(base, queue_name)
    target.parent.mkdir(parents=True, exist_ok=True)
    msg_id = msg_id or str(uuid.uuid4())
    msg = Message(msg_id=msg_id, sender=sender, body=content, ts=_now_jst())

    lock_path = _lock_path(target)
    with open(lock_path, "w", encoding=ENC) as lock_fp:
        fcntl.flock(lock_fp.fileno(), fcntl.LOCK_EX)
        existing = target.read_text(encoding=ENC) if target.exists() else ""
        with tempfile.NamedTemporaryFile(
            mode="w", encoding=ENC, newline=NEWLINE,
            dir=target.parent, delete=False, prefix=".tmp_", suffix=".md",
        ) as tmp:
            tmp.write(existing)
            tmp.write(msg.to_block())
            tmp_path = Path(tmp.name)
        os.replace(tmp_path, target)
    return msg_id


def _parse_messages(content: str) -> list[dict]:
    msgs: list[dict] = []
    cur: Optional[dict] = None
    for line in content.splitlines():
        if line.startswith("<!-- MSG_ID:"):
            if cur is not None:
                cur["body"] = "\n".join(cur["body_lines"]).rstrip()
                cur.pop("body_lines", None)
                msgs.append(cur)
            header = line.strip("<!- >").strip()
            parts = {kv.split(":", 1)[0].strip(): kv.split(":", 1)[1].strip()
                     for kv in header.split("|") if ":" in kv}
            cur = {
                "msg_id": parts.get("MSG_ID", ""),
                "sender": parts.get("SENDER", ""),
                "ts": parts.get("TS", ""),
                "body_lines": [],
            }
        elif cur is not None:
            cur["body_lines"].append(line)
    if cur is not None:
        cur["body"] = "\n".join(cur["body_lines"]).rstrip()
        cur.pop("body_lines", None)
        msgs.append(cur)
    return msgs


def atomic_drain(
    queue_name: str,
    base: Path = DEFAULT_BASE,
    archive: bool = True,
) -> list[dict]:
    target = _queue_path(base, queue_name)
    if not target.exists():
        return []

    lock_path = _lock_path(target)
    with open(lock_path, "w", encoding=ENC) as lock_fp:
        fcntl.flock(lock_fp.fileno(), fcntl.LOCK_EX)
        content = target.read_text(encoding=ENC)
        messages = _parse_messages(content)

        if archive and content.strip():
            date = datetime.now(JST).strftime("%Y-%m-%d")
            arc_dir = base / "archive" / date
            arc_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(JST).strftime("%H%M%S_%f")
            arc_path = arc_dir / f"{queue_name}_{stamp}.md"
            with tempfile.NamedTemporaryFile(
                mode="w", encoding=ENC, newline=NEWLINE,
                dir=arc_dir, delete=False,
            ) as tmp:
                tmp.write(content)
                arc_tmp = Path(tmp.name)
            os.replace(arc_tmp, arc_path)

        with tempfile.NamedTemporaryFile(
            mode="w", encoding=ENC, newline=NEWLINE,
            dir=target.parent, delete=False,
        ) as tmp:
            tmp.write("")
            empty_tmp = Path(tmp.name)
        os.replace(empty_tmp, target)
    return messages


def append_validator_log(record: dict, base: Path = DEFAULT_BASE) -> None:
    path = base / "data" / "validator_log.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = _lock_path(path)
    record = dict(record)
    record.setdefault("ts", _now_jst())
    with open(lock_path, "w", encoding=ENC) as lock_fp:
        fcntl.flock(lock_fp.fileno(), fcntl.LOCK_EX)
        with open(path, "a", encoding=ENC, newline=NEWLINE) as fp:
            fp.write(json.dumps(record, ensure_ascii=False) + NEWLINE)


def append_timeline(record: dict, base: Path = DEFAULT_BASE) -> None:
    path = base / "data" / "timeline.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = _lock_path(path)
    record = dict(record)
    record.setdefault("ts", _now_jst())
    with open(lock_path, "w", encoding=ENC) as lock_fp:
        fcntl.flock(lock_fp.fileno(), fcntl.LOCK_EX)
        with open(path, "a", encoding=ENC, newline=NEWLINE) as fp:
            fp.write(json.dumps(record, ensure_ascii=False) + NEWLINE)


def self_test() -> bool:
    import shutil
    tmp_base = Path(tempfile.mkdtemp(prefix="queue_io_test_"))
    try:
        mid = atomic_append("q_test", "hello world", "sender_a", base=tmp_base)
        assert mid, "msg_id empty"
        assert (tmp_base / "queue" / "q_test.md").exists(), "queue file not created"

        mid2 = atomic_append("q_test", "second message", "sender_b", base=tmp_base)
        assert mid2 != mid, "msg_id should differ"

        msgs = atomic_drain("q_test", base=tmp_base, archive=True)
        assert len(msgs) == 2, f"expected 2 messages, got {len(msgs)}"
        assert msgs[0]["body"].startswith("hello"), f"body mismatch: {msgs[0]['body']!r}"
        assert msgs[1]["sender"] == "sender_b"

        msgs_after = atomic_drain("q_test", base=tmp_base)
        assert msgs_after == [], "drain should leave queue empty"

        archives = list((tmp_base / "archive").rglob("*.md"))
        assert len(archives) == 1, f"archive count {len(archives)}"

        append_validator_log({"actor": "gpt", "pass": True}, base=tmp_base)
        log_path = tmp_base / "data" / "validator_log.jsonl"
        assert log_path.exists(), "validator log missing"
        line = log_path.read_text(encoding=ENC).strip()
        assert json.loads(line)["actor"] == "gpt"

        print("PASS: queue_io self_test")
        return True
    finally:
        shutil.rmtree(tmp_base, ignore_errors=True)


if __name__ == "__main__":
    ok = self_test()
    raise SystemExit(0 if ok else 1)
