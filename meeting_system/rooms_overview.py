"""
rooms_overview — rooms_overview.json 集約サマリー生成

3者合意 (前議題 R50-MULTI-PROJECT-PARALLEL):
- single source of truth = 各 projects/{room_id}/state.json
- rooms_overview.json は read-mostly な集約 (UI/通知向け)
- orchestrator の各ターン終了時 + UI SSE トリガで再生成
- File Lock + Atomic Move (前々議題合意の queue_io方式)
"""
from __future__ import annotations

import fcntl
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

from .state_schema import (
    DEFAULT_BASE, JST, ENC, NEWLINE,
    read_state, room_state_path,
)

ICON_DEFAULTS = {
    "btc_auto_trade":   {"icon": "₿",  "color": "#F7931A"},
    "news_family_comic":{"icon": "📰", "color": "#4FC3FF"},
    "delivery_offer_ai":{"icon": "🛵", "color": "#2DFF88"},
}

DEFAULT_PRIORITY = 5
CDP_PORT_RANGE = [9222, 9253]


def _overview_path(base: Path) -> Path:
    return base / "data" / "rooms_overview.json"


def _list_rooms(base: Path) -> list[str]:
    projects = base / "projects"
    if not projects.exists():
        return []
    return [p.name for p in projects.iterdir()
            if p.is_dir() and (p / "state.json").exists()]


def _room_summary(room_id: str, base: Path) -> dict:
    state = read_state(room_id, base)
    icon_cfg = ICON_DEFAULTS.get(room_id, {"icon": "💬", "color": "#888888"})
    return {
        "room_id": room_id,
        "title": state.get("project_name") or room_id,
        "icon": icon_cfg["icon"],
        "color": icon_cfg["color"],
        "cdp_port": state.get("chrome_cdp_port"),
        "chrome_profile_dir": str(
            Path("/Users/shuji/Library/Application Support/Google") / f"Chrome-{room_id}"
        ),
        "status": state.get("status", "idle"),
        "current_actor": state.get("current_actor"),
        "next_actor": state.get("next_actor"),
        "current_loop": state.get("total_loops", 0),
        "current_turn_in_loop": state.get("current_turn_in_loop", 0),
        "is_consensus_established": state.get("is_consensus_established", False),
        "consensus_established_loop": state.get("consensus_established_loop"),
        "notify_level": state.get("notify_level", "normal"),
        "unread_count": state.get("unread_count", 0),
        "last_msg_id": state.get("last_msg_id"),
        "last_msg_ts": state.get("last_msg_ts"),
        "topic_title": state.get("topic_title"),
        "queue_priority": state.get("queue_priority", DEFAULT_PRIORITY),
    }


def generate(base: Path = DEFAULT_BASE,
             active_room_id: str | None = None) -> dict:
    rooms = [_room_summary(rid, base) for rid in _list_rooms(base)]
    processing = None
    consensus_unread = 0
    shuji_unread_total = 0
    for r in rooms:
        if r["status"] == "ai_processing":
            processing = r["room_id"]
        shuji_unread_total += r.get("unread_count", 0)
        if r["is_consensus_established"]:
            consensus_unread += 1
    return {
        "schema_version": 1,
        "updated_at": datetime.now(JST).isoformat(),
        "rooms": rooms,
        "global": {
            "active_room_id": active_room_id or (rooms[0]["room_id"] if rooms else None),
            "processing_room_id": processing,
            "shuji_unread_total": shuji_unread_total,
            "consensus_unread_count": consensus_unread,
            "cdp_port_range": CDP_PORT_RANGE,
        },
    }


def refresh(base: Path = DEFAULT_BASE,
            active_room_id: str | None = None) -> dict:
    data = generate(base, active_room_id)
    path = _overview_path(base)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(".lock")
    with open(lock_path, "w", encoding=ENC) as lock_fp:
        fcntl.flock(lock_fp.fileno(), fcntl.LOCK_EX)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding=ENC, newline=NEWLINE,
            dir=path.parent, delete=False,
        ) as tmp:
            json.dump(data, tmp, ensure_ascii=False, indent=2)
            tmp_path = Path(tmp.name)
        os.replace(tmp_path, path)
    return data


def read_overview(base: Path = DEFAULT_BASE) -> dict:
    path = _overview_path(base)
    if not path.exists():
        return generate(base)
    return json.loads(path.read_text(encoding=ENC))


def self_test() -> bool:
    import shutil
    from . import state_schema
    tmp_base = Path(tempfile.mkdtemp(prefix="rooms_overview_test_"))
    try:
        state_schema.init_room("btc_auto_trade", "BTC自動売買", cdp_port=9222, base=tmp_base)
        state_schema.init_room("delivery_offer_ai", "配達AI", cdp_port=9223, base=tmp_base)

        data = refresh(base=tmp_base)
        assert data["schema_version"] == 1
        assert len(data["rooms"]) == 2
        ids = {r["room_id"] for r in data["rooms"]}
        assert ids == {"btc_auto_trade", "delivery_offer_ai"}
        assert data["global"]["cdp_port_range"] == [9222, 9253]

        path = _overview_path(tmp_base)
        assert path.exists()

        data2 = read_overview(tmp_base)
        assert data2["schema_version"] == 1

        print("PASS: rooms_overview self_test")
        return True
    finally:
        shutil.rmtree(tmp_base, ignore_errors=True)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    ok = self_test()
    raise SystemExit(0 if ok else 1)
