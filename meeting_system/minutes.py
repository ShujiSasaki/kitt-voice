"""
minutes — 議事録自動生成 (R57 Phase B)

timeline.jsonl の room_id + loop_num 該当 msg を md書式で出力
出力先: data/projects/{room_id}/minutes/round_{loop_num}.md

R57 3者合意 master_data (発言Claude R1指摘): Phase 1既存12モジュール流用
- queue_io.append_timeline で書かれた timeline.jsonl を読み取り
- state_schema.read_state で current loop把握
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .state_schema import DEFAULT_BASE, JST, read_state

ENC = "utf-8"
NEWLINE = "\n"


def _timeline_path(base: Path) -> Path:
    return base / "data" / "timeline.jsonl"


def _minutes_path(room_id: str, loop_num: int, base: Path) -> Path:
    return base / "data" / "projects" / room_id / "minutes" / f"round_{loop_num}.md"


def _read_timeline_for_room(base: Path, room_id: str) -> list[dict]:
    path = _timeline_path(base)
    if not path.exists():
        return []
    msgs = []
    for line in path.read_text(encoding=ENC).splitlines():
        if not line.strip():
            continue
        try:
            m = json.loads(line)
        except json.JSONDecodeError:
            continue
        if m.get("room_id") == room_id:
            msgs.append(m)
    return msgs


ACTOR_LABEL = {
    "shuji": "👤 Shuji",
    "gpt": "🟢 GPT",
    "gemini": "🟣 Gemini",
    "claude": "🟠 Claude",
    "validator": "⚙️ Validator",
}


def generate_minutes(
    room_id: str, loop_num: int, base: Path = DEFAULT_BASE,
) -> dict:
    state = read_state(room_id, base)
    msgs = _read_timeline_for_room(base, room_id)
    loop_msgs = [m for m in msgs if int(m.get("loop", 0)) == loop_num]
    if not loop_msgs:
        loop_msgs = msgs
    lines = []
    title = state.get("current_topic") or state.get("topic_title") or room_id
    lines.append(f"# Round {loop_num} — {title}")
    lines.append("")
    lines.append(f"- **Room**: {room_id}")
    lines.append(f"- **Loop**: {loop_num}")
    lines.append(f"- **Generated**: {datetime.now(JST).isoformat()}")
    lines.append(
        f"- **Consensus**: "
        f"{'✅ established' if state.get('is_consensus_established') else '❌ pending'}"
    )
    if state.get("consensus_established_reason"):
        lines.append(f"- **Reason**: {state['consensus_established_reason']}")
    lines.append("")
    lines.append("---")
    lines.append("")
    for m in loop_msgs:
        actor = m.get("actor", "?")
        label = ACTOR_LABEL.get(actor, actor)
        ts = m.get("ts", "")
        body = m.get("body", "").strip()
        v = m.get("validator") or {}
        v_status = "✅ PASS" if v.get("pass") else "❌ FAIL"
        lines.append(f"## {label}  ·  {ts}  ·  {v_status}")
        lines.append("")
        for ln in body.splitlines():
            lines.append(f"> {ln}")
        lines.append("")
        if v.get("items"):
            lines.append(f"_validator items: {', '.join(v['items'])}_")
            lines.append("")
        lines.append("---")
        lines.append("")
    out_path = _minutes_path(room_id, loop_num, base)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(NEWLINE.join(lines), encoding=ENC, newline=NEWLINE)
    return {"path": str(out_path), "msg_count": len(loop_msgs)}


def self_test() -> bool:
    import shutil
    import tempfile
    tmp_base = Path(tempfile.mkdtemp(prefix="minutes_test_"))
    try:
        from . import queue_io
        from .state_schema import write_state_atomic, default_state
        room_id = "test_room"
        state = default_state(room_id)
        state["current_topic"] = "Test議題"
        state["total_loops"] = 1
        write_state_atomic(room_id, state, base=tmp_base)
        for actor, body in [
            ("shuji", "テスト発言"),
            ("gpt", "GPT回答\nconsensus_candidate: true"),
            ("gemini", "Gemini同意"),
        ]:
            queue_io.append_timeline({
                "room_id": room_id, "msg_id": f"mid_{actor}",
                "actor": actor, "body": body, "loop": 1,
                "validator": {"pass": True, "items": ["test"]},
            }, base=tmp_base)
        result = generate_minutes(room_id, 1, base=tmp_base)
        assert Path(result["path"]).exists(), "minutes file not created"
        content = Path(result["path"]).read_text(encoding=ENC)
        assert "テスト発言" in content, "shuji body missing"
        assert "GPT回答" in content, "gpt body missing"
        assert "Gemini同意" in content, "gemini body missing"
        assert "✅ established" in content or "❌ pending" in content
        print("PASS: minutes self_test")
        return True
    finally:
        shutil.rmtree(tmp_base, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(0 if self_test() else 1)
