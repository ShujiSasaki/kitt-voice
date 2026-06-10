"""
state_schema — schema_v2 各room state.json スキーマ定義

3者合意 (前2議題):
- 巡数管理: total_loops, current_turn_in_loop, loops_history
- 合意成立判定: is_consensus_established, consensus_required_min_loops=2
- room分離: projects/{room_id}/state.json (single source of truth)
- 既存フィールド継承: claude_speaker_tab_id, chrome_cdp_port
"""
from __future__ import annotations

import fcntl
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

JST = timezone(timedelta(hours=9))
ENC = "utf-8"
NEWLINE = "\n"

DEFAULT_BASE = Path("/Users/shuji/Desktop/kitt-voice/meeting_system")

SCHEMA_VERSION = 2
SEQUENCE = ["gpt", "gemini", "claude"]


def default_state(
    room_id: str,
    project_name: str = "",
    cdp_port: int = 9222,
    claude_tab_id: Optional[int] = None,
    color: str = "#4F46E5",
    icon: str = "💬",
) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "room_id": room_id,
        "project_name": project_name,
        "color": color,
        "icon": icon,
        "current_topic": "",
        "created_at": datetime.now(JST).isoformat(),
        "status": "idle",
        "current_actor": None,
        "next_actor": "gpt",
        "current_turn_in_loop": 0,
        "total_loops": 0,
        "loops_history": [],
        "consensus_candidates_per_loop": {},
        "is_consensus_established": False,
        "consensus_established_at": None,
        "consensus_established_loop": None,
        "consensus_established_reason": None,
        "consensus_required_min_loops": 2,
        "topic_id": None,
        "topic_title": None,
        "topic_started_at": None,
        "claude_speaker_tab_id": claude_tab_id,
        "chrome_cdp_port": cdp_port,
        "queue_priority": 5,
        "notify_level": "normal",
        "unread_count": 0,
        "last_msg_id": None,
        "last_msg_ts": None,
        "last_shuji_input_ts": None,
        "interrupt_ts": None,
        "tabs": {},
        # R59 Q4: 会議室編集履歴
        "edit_history": [],
        "description": "",
        "participants": ["gpt", "gemini", "claude"],
        "actor_sequence": ["gpt", "gemini", "claude"],
        "archived": False,
    }


def room_state_path(room_id: str, base: Path = DEFAULT_BASE) -> Path:
    return base / "projects" / room_id / "state.json"


def read_state(room_id: str, base: Path = DEFAULT_BASE) -> dict:
    path = room_state_path(room_id, base)
    if not path.exists():
        return default_state(room_id)
    return json.loads(path.read_text(encoding=ENC))


def write_state_atomic(room_id: str, state: dict, base: Path = DEFAULT_BASE) -> None:
    path = room_state_path(room_id, base)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(".lock")
    with open(lock_path, "w", encoding=ENC) as lock_fp:
        fcntl.flock(lock_fp.fileno(), fcntl.LOCK_EX)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding=ENC, newline=NEWLINE,
            dir=path.parent, delete=False,
            prefix=".state_", suffix=".json",
        ) as tmp:
            json.dump(state, tmp, ensure_ascii=False, indent=2)
            tmp_path = Path(tmp.name)
        os.replace(tmp_path, path)


def init_room(
    room_id: str,
    project_name: str = "",
    cdp_port: int = 9222,
    base: Path = DEFAULT_BASE,
) -> dict:
    state = default_state(room_id, project_name, cdp_port)
    write_state_atomic(room_id, state, base)
    return state


class RoomAlreadyExistsError(Exception):
    pass


def create_room(
    room_id: str,
    project_name: str = "",
    color: str = "#4F46E5",
    icon: str = "💬",
    cdp_port: int = 9222,
    base: Path = DEFAULT_BASE,
) -> dict:
    """3者合意 R55:
    state.json + ディレクトリ群 (queue/responses/minutes/browser_profile/timeline.jsonl)
    をアトミック生成 (失敗時 shutil.rmtree でロールバック)
    """
    if not room_id or "/" in room_id or ".." in room_id:
        raise ValueError(f"invalid room_id: {room_id!r}")
    room_dir = base / "projects" / room_id
    if room_dir.exists():
        raise RoomAlreadyExistsError(f"room already exists: {room_id}")
    try:
        room_dir.mkdir(parents=True, exist_ok=False)
        (room_dir / "queue").mkdir()
        (room_dir / "responses").mkdir()
        (room_dir / "minutes").mkdir()
        (room_dir / "browser_profile").mkdir()
        (room_dir / "timeline.jsonl").touch()
        state = default_state(
            room_id=room_id,
            project_name=project_name or room_id,
            cdp_port=cdp_port,
            color=color,
            icon=icon,
        )
        write_state_atomic(room_id, state, base)
        return state
    except Exception:
        shutil.rmtree(room_dir, ignore_errors=True)
        raise


def reset_topic(room_id: str, topic_id: str, topic_title: str,
                base: Path = DEFAULT_BASE) -> dict:
    state = read_state(room_id, base)
    state["topic_id"] = topic_id
    state["topic_title"] = topic_title
    state["topic_started_at"] = datetime.now(JST).isoformat()
    state["total_loops"] = 0
    state["current_turn_in_loop"] = 0
    state["loops_history"] = []
    state["consensus_candidates_per_loop"] = {}
    state["is_consensus_established"] = False
    state["consensus_established_at"] = None
    state["consensus_established_loop"] = None
    state["consensus_established_reason"] = None
    state["next_actor"] = "gpt"
    state["status"] = "idle"
    write_state_atomic(room_id, state, base)
    return state


def self_test() -> bool:
    import shutil
    tmp_base = Path(tempfile.mkdtemp(prefix="state_schema_test_"))
    try:
        s = init_room("test_room", "Test Project", cdp_port=9222, base=tmp_base)
        assert s["schema_version"] == 2
        assert s["consensus_required_min_loops"] == 2
        assert s["next_actor"] == "gpt"
        assert s["total_loops"] == 0

        s2 = read_state("test_room", base=tmp_base)
        assert s2["room_id"] == "test_room"

        reset_topic("test_room", "topic_A", "テスト議題", base=tmp_base)
        s3 = read_state("test_room", base=tmp_base)
        assert s3["topic_id"] == "topic_A"
        assert s3["total_loops"] == 0

        print("PASS: state_schema self_test")
        return True
    finally:
        shutil.rmtree(tmp_base, ignore_errors=True)


if __name__ == "__main__":
    ok = self_test()
    raise SystemExit(0 if ok else 1)
