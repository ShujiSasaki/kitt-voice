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

from . import chrome_lock
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


# R65: relay_worker が書出す処理中room (30秒超過で stale = worker停止扱い)
ROUTER_STATE_STALE_SEC = 30.0


def _router_state(base: Path) -> tuple[str | None, list[str]]:
    """(処理中room, FIFO待機room一覧)。stale/未生成は (None, [])"""
    import time as _time
    p = base / "data" / "router_state.json"
    if not p.exists():
        return None, []
    try:
        d = json.loads(p.read_text(encoding=ENC))
    except Exception:
        return None, []
    if _time.time() - float(d.get("updated", 0)) > ROUTER_STATE_STALE_SEC:
        return None, []
    return d.get("active_room"), list(d.get("queue") or [])


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
        # R62: state.json の icon/color を優先 (R55 create_room / R59 Q4 PATCH 設定値)
        "icon": state.get("icon") or icon_cfg["icon"],
        "color": state.get("color") or icon_cfg["color"],
        "archived": state.get("archived", False),
        "project_id": state.get("project_id"),
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
        "last_msg_preview": state.get("last_msg_preview"),
        "topic_title": state.get("topic_title"),
        "queue_priority": state.get("queue_priority", DEFAULT_PRIORITY),
    }


def generate(base: Path = DEFAULT_BASE,
             active_room_id: str | None = None) -> dict:
    rooms = [_room_summary(rid, base) for rid in _list_rooms(base)]
    # R62: archived部屋は sidebar非表示 (Shuji要望「テストの部屋が邪魔」 2026-06-10)
    rooms = [r for r in rooms if not r.get("archived")]
    # R65: worker処理中room (router_state.json由来、 ai_processing statusはfallback)
    router_room, router_queue = _router_state(base)
    processing = router_room
    consensus_unread = 0
    shuji_unread_total = 0
    for r in rooms:
        r["is_processing"] = (r["room_id"] == router_room)
        # UX改善: FIFO待機順 (1始まり)。待機していなければ None
        r["queue_position"] = (
            router_queue.index(r["room_id"]) + 1
            if r["room_id"] in router_queue else None
        )
        if processing is None and r["status"] == "ai_processing":
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
            "router_queue": router_queue,
            "shuji_unread_total": shuji_unread_total,
            "consensus_unread_count": consensus_unread,
            "cdp_port_range": CDP_PORT_RANGE,
            "chrome_lock": chrome_lock.status(base),
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

        # R65: is_processing — router_state.json なし → 全False
        assert all(r["is_processing"] is False for r in data["rooms"])
        # router_state.json 書込み → 該当roomのみ True
        import time as _t
        rs = tmp_base / "data" / "router_state.json"
        rs.parent.mkdir(parents=True, exist_ok=True)
        rs.write_text(json.dumps({"active_room": "btc_auto_trade", "updated": _t.time()}),
                      encoding=ENC)
        data3 = generate(tmp_base)
        flags = {r["room_id"]: r["is_processing"] for r in data3["rooms"]}
        assert flags["btc_auto_trade"] is True, f"is_processing付与失敗: {flags}"
        assert flags["delivery_offer_ai"] is False
        assert data3["global"]["processing_room_id"] == "btc_auto_trade"
        # stale (31秒前) → 全False
        rs.write_text(json.dumps({"active_room": "btc_auto_trade", "updated": _t.time() - 31}),
                      encoding=ENC)
        data4 = generate(tmp_base)
        assert all(r["is_processing"] is False for r in data4["rooms"]), "stale判定失敗"

        # UX改善: FIFO待機列 → queue_position
        rs.write_text(json.dumps({
            "active_room": "btc_auto_trade",
            "queue": ["delivery_offer_ai"],
            "updated": _t.time(),
        }), encoding=ENC)
        data5 = generate(tmp_base)
        pos = {r["room_id"]: r["queue_position"] for r in data5["rooms"]}
        assert pos["delivery_offer_ai"] == 1, f"queue_position誤り: {pos}"
        assert pos["btc_auto_trade"] is None
        assert data5["global"]["router_queue"] == ["delivery_offer_ai"]

        print("PASS: rooms_overview self_test (R65 is_processing + queue_position含む)")
        return True
    finally:
        shutil.rmtree(tmp_base, ignore_errors=True)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    ok = self_test()
    raise SystemExit(0 if ok else 1)
