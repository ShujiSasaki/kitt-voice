"""
server — FastAPI + uvicorn (localhost:8765) + SSE

3者合意 (前々々議題 R50-PLAN-B-SYSTEM-DETAIL + 前議題 R50-MULTI-PROJECT):
- /api/rooms/overview — 集約サマリー
- /api/rooms/{room_id}/state — room state
- /api/rooms/{room_id}/timeline — タイムライン
- /api/rooms/{room_id}/submit — Shuji発言投入 (atomic_append → queue/)
- /api/rooms/{room_id}/interrupt — SIGINT送信 (二重防御)
- /api/thread/{msg_id} — X風スレッド (関連監査エントリ)
- /api/notification — 通知設定 ON/OFF/STRICT
- /api/events — SSE (timeline.jsonl変更通知)
- /api/rooms/{room_id}/activate — UIアクティブroom切替
- CORS: localhost:8765 のみ許可 (Gemini Must Fix 2採択)
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path

from .state_schema import DEFAULT_BASE, JST, read_state, write_state_atomic
from . import queue_io, rooms_overview, notification_controller, sigint_handler
from . import validator_consensus

STATIC = Path(__file__).parent / "local_board"


def _timeline_path(base: Path) -> Path:
    return base / "data" / "timeline.jsonl"


def _read_timeline(base: Path, since: str = "") -> list[dict]:
    path = _timeline_path(base)
    if not path.exists():
        return []
    msgs: list[dict] = []
    seen = (since == "")
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            m = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not seen:
            if m.get("msg_id") == since:
                seen = True
            continue
        msgs.append(m)
    return msgs


def _filter_room(msgs: list[dict], room_id: str) -> list[dict]:
    return [m for m in msgs if m.get("room_id") == room_id]


def create_app(base: Path = DEFAULT_BASE):
    try:
        from fastapi import FastAPI, Request, HTTPException
        from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
        from fastapi.middleware.cors import CORSMiddleware
    except ImportError as e:
        raise RuntimeError(
            "FastAPI 未インストール: pip install fastapi uvicorn"
        ) from e

    app = FastAPI(title="ぐるぐる3者会議 local_board")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:8765",
            "http://localhost:8765",
        ],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/")
    async def index():
        idx = STATIC / "index.html"
        if not idx.exists():
            return JSONResponse({"error": "index.html not found"}, status_code=404)
        return FileResponse(idx)

    @app.get("/app.js")
    async def app_js():
        return FileResponse(STATIC / "app.js")

    @app.get("/style.css")
    async def style_css():
        return FileResponse(STATIC / "style.css")

    @app.get("/api/rooms/overview")
    async def get_overview():
        return rooms_overview.refresh(base)

    @app.get("/api/rooms/{room_id}/state")
    async def get_room_state(room_id: str):
        return read_state(room_id, base)

    @app.get("/api/rooms/{room_id}/timeline")
    async def get_room_timeline(room_id: str, since: str = ""):
        msgs = _filter_room(_read_timeline(base, since), room_id)
        return {"messages": msgs}

    @app.post("/api/rooms/{room_id}/submit")
    async def post_submit(room_id: str, req: Request):
        data = await req.json()
        body = (data.get("body") or "").strip()
        if not body:
            return JSONResponse({"error": "empty"}, status_code=400)
        state = read_state(room_id, base)
        if state.get("status") == "ai_processing":
            return JSONResponse(
                {"error": "ai_busy_use_interrupt"}, status_code=409,
            )
        nxt = state.get("next_actor") or "gpt"
        msg_id = queue_io.atomic_append(
            f"shuji_to_{nxt}_{room_id}", body, sender="shuji", base=base,
        )
        state["last_shuji_input_ts"] = datetime.now(JST).isoformat()
        validator_consensus.reset_consensus_on_shuji_input(room_id, base)
        write_state_atomic(room_id, state, base)
        queue_io.append_timeline({
            "room_id": room_id,
            "msg_id": msg_id,
            "actor": "shuji",
            "body": body,
            "raw": body,
            "tags": {},
            "validator": {"pass": True, "items": ["shuji_direct"]},
        }, base=base)
        return {"ok": True, "msg_id": msg_id}

    @app.post("/api/rooms/{room_id}/interrupt")
    async def post_interrupt(room_id: str):
        result = sigint_handler.request_interrupt(room_id, base)
        return result

    @app.post("/api/rooms/{room_id}/activate")
    async def post_activate(room_id: str):
        rooms_overview.refresh(base, active_room_id=room_id)
        return {"ok": True, "active_room_id": room_id}

    @app.get("/api/thread/{parent_msg_id}")
    async def get_thread(parent_msg_id: str):
        msgs = _read_timeline(base)
        items = []
        for m in msgs:
            for audit in m.get("audits", []):
                if audit.get("target_msg_id") == parent_msg_id:
                    items.append({
                        "actor": m.get("actor"),
                        "ts": m.get("ts"),
                        "kind": audit.get("kind", "agree"),
                        "body": audit.get("summary", ""),
                        "ref_msg_id": m.get("msg_id"),
                    })
        return {"items": items}

    @app.get("/api/notification")
    async def get_notification():
        return notification_controller.read_config(base)

    @app.post("/api/notification")
    async def post_notification(req: Request):
        data = await req.json()
        cur = notification_controller.read_config(base)
        cur.update({k: v for k, v in data.items() if k in
                    ("level", "slack_webhook_url", "discord_webhook_url")})
        notification_controller.write_config(cur, base)
        return {"ok": True, "config": cur}

    @app.get("/api/events")
    async def events():
        async def stream():
            last_size = -1
            tl = _timeline_path(base)
            while True:
                size = tl.stat().st_size if tl.exists() else 0
                if size != last_size:
                    yield "data: update\n\n"
                    last_size = size
                await asyncio.sleep(1)
        return StreamingResponse(stream(), media_type="text/event-stream")

    return app


def self_test() -> bool:
    try:
        import fastapi  # noqa
    except ImportError:
        print("SKIP: server self_test (fastapi未インストール、 統合時にインストール)")
        return True
    app = create_app()
    routes = [r.path for r in app.routes]
    expected = [
        "/", "/api/rooms/overview",
        "/api/rooms/{room_id}/state", "/api/rooms/{room_id}/timeline",
        "/api/rooms/{room_id}/submit", "/api/rooms/{room_id}/interrupt",
        "/api/rooms/{room_id}/activate", "/api/thread/{parent_msg_id}",
        "/api/notification", "/api/events",
    ]
    missing = [e for e in expected if e not in routes]
    assert not missing, f"missing routes: {missing}"
    print("PASS: server self_test (route inventory)")
    return True


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    ok = self_test()
    if ok and "--serve" in sys.argv:
        try:
            import uvicorn
            uvicorn.run(create_app(), host="127.0.0.1", port=8765)
        except ImportError:
            print("uvicorn未インストール")
    raise SystemExit(0 if ok else 1)
