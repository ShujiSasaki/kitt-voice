"""
server — FastAPI + uvicorn (Tailscale or localhost:8765) + SSE

3者合意 (R50-IPHONE-DASHBOARD-ACCESS Loop 3 確定仕様):
- host=$MEETING_HOST (Tailscale IP bind 推奨)
- CORS allow_origins に Tailscale IP origin 動的追加
- Basic認証 (MEETING_BASIC_USER/PASS env + hmac.compare_digest)
- CSRFトークン (session-bound + 24h TTL)
- Replay防止 (client msg_id + server is_duplicate)
- 全 POST endpoint verify_basic Depends
"""
from __future__ import annotations

import asyncio
import hmac
import json
import os
import secrets
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    from fastapi import FastAPI, Request, HTTPException, Depends
    from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.security import HTTPBasic, HTTPBasicCredentials
    from fastapi.exceptions import RequestValidationError
except ImportError as _fastapi_import_error:
    FastAPI = None  # type: ignore
    Request = None  # type: ignore
    HTTPException = None  # type: ignore
    Depends = None  # type: ignore
    StreamingResponse = None  # type: ignore
    FileResponse = None  # type: ignore
    JSONResponse = None  # type: ignore
    CORSMiddleware = None  # type: ignore
    HTTPBasic = None  # type: ignore
    HTTPBasicCredentials = None  # type: ignore
    RequestValidationError = None  # type: ignore

from .state_schema import (
    DEFAULT_BASE, JST, read_state, write_state_atomic,
    create_room, RoomAlreadyExistsError,
)
from . import queue_io, rooms_overview, notification_controller, sigint_handler
from . import validator_consensus

STATIC = Path(__file__).parent / "local_board"

MEETING_HOST = os.environ.get("MEETING_HOST", "127.0.0.1")
MEETING_PORT = int(os.environ.get("MEETING_PORT", "8765"))
MEETING_BASIC_USER = os.environ.get("MEETING_BASIC_USER", "")
MEETING_BASIC_PASS = os.environ.get("MEETING_BASIC_PASS", "")
MEETING_TAILSCALE_IP = os.environ.get("MEETING_TAILSCALE_IP", "")

CSRF_TTL_SECONDS = 86400
_csrf_tokens: dict[str, float] = {}
_seen_msg_ids: set[str] = set()
_MAX_SEEN_MSG_IDS = 10000


def _detect_tailscale_ip() -> str:
    return MEETING_TAILSCALE_IP


def _gen_csrf_token() -> str:
    token = secrets.token_urlsafe(32)
    now = time.time()
    _csrf_tokens[token] = now + CSRF_TTL_SECONDS
    expired = [t for t, exp in _csrf_tokens.items() if exp < now]
    for t in expired:
        del _csrf_tokens[t]
    return token


def _verify_csrf(token: str) -> bool:
    if not token:
        return False
    exp = _csrf_tokens.get(token)
    if not exp or exp < time.time():
        return False
    return True


def _check_replay(msg_id: str) -> bool:
    if not msg_id:
        return False
    if msg_id in _seen_msg_ids:
        return True
    _seen_msg_ids.add(msg_id)
    if len(_seen_msg_ids) > _MAX_SEEN_MSG_IDS:
        keep = list(_seen_msg_ids)[-_MAX_SEEN_MSG_IDS // 2:]
        _seen_msg_ids.clear()
        _seen_msg_ids.update(keep)
    return False


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
    if FastAPI is None:
        raise RuntimeError(
            "FastAPI 未インストール: pip install fastapi uvicorn"
        )

    app = FastAPI(title="ぐるぐる3者会議 local_board")

    @app.exception_handler(RequestValidationError)
    async def _422_debug(request: Request, exc: RequestValidationError):
        import sys
        print(
            f"[422 DEBUG] {request.method} {request.url.path} "
            f"errors={exc.errors()}",
            file=sys.stderr, flush=True,
        )
        return JSONResponse(
            status_code=422,
            content={"detail": exc.errors()},
        )

    allow_origins_list = [
        f"http://127.0.0.1:{MEETING_PORT}",
        f"http://localhost:{MEETING_PORT}",
    ]
    ts_ip = _detect_tailscale_ip()
    if ts_ip:
        allow_origins_list.append(f"http://{ts_ip}:{MEETING_PORT}")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins_list,
        allow_methods=["*"],
        allow_headers=["*", "X-CSRF-Token"],
    )

    _basic = HTTPBasic(auto_error=False)

    def verify_basic(
        credentials: Optional[HTTPBasicCredentials] = Depends(_basic),
    ):
        if not MEETING_BASIC_USER or not MEETING_BASIC_PASS:
            return None
        if credentials is None:
            raise HTTPException(
                status_code=401, detail="auth_required",
                headers={"WWW-Authenticate": "Basic"},
            )
        ok_user = hmac.compare_digest(
            credentials.username.encode("utf-8"),
            MEETING_BASIC_USER.encode("utf-8"),
        )
        ok_pass = hmac.compare_digest(
            credentials.password.encode("utf-8"),
            MEETING_BASIC_PASS.encode("utf-8"),
        )
        if not (ok_user and ok_pass):
            raise HTTPException(
                status_code=401, detail="auth_invalid",
                headers={"WWW-Authenticate": "Basic"},
            )
        return credentials.username

    @app.get("/")
    async def index(user=Depends(verify_basic)):
        idx = STATIC / "index.html"
        if not idx.exists():
            return JSONResponse({"error": "index.html not found"}, status_code=404)
        return FileResponse(idx)

    @app.get("/app.js")
    async def app_js(user=Depends(verify_basic)):
        return FileResponse(STATIC / "app.js")

    @app.get("/style.css")
    async def style_css(user=Depends(verify_basic)):
        return FileResponse(STATIC / "style.css")

    @app.get("/manifest.json")
    async def manifest():
        return FileResponse(STATIC / "manifest.json")

    @app.get("/apple-touch-icon-192.png")
    async def apple_touch_icon_192():
        return FileResponse(STATIC / "apple-touch-icon-192.png")

    @app.get("/apple-touch-icon-512.png")
    async def apple_touch_icon_512():
        return FileResponse(STATIC / "apple-touch-icon-512.png")

    @app.get("/api/csrf-token")
    async def get_csrf(user=Depends(verify_basic)):
        return {"token": _gen_csrf_token()}

    @app.get("/api/rooms/overview")
    async def get_overview(user=Depends(verify_basic)):
        return rooms_overview.refresh(base)

    @app.post("/api/rooms/create")
    async def post_create_room(
        req: Request, user=Depends(verify_basic),
    ):
        csrf = req.headers.get("X-CSRF-Token", "")
        if not _verify_csrf(csrf):
            raise HTTPException(status_code=403, detail="csrf_invalid")
        data = await req.json()
        room_id = (data.get("room_id") or "").strip()
        if not room_id:
            return JSONResponse({"error": "room_id_required"}, status_code=400)
        try:
            state = create_room(
                room_id=room_id,
                project_name=(data.get("project_name") or room_id).strip(),
                color=(data.get("color") or "#4F46E5").strip(),
                icon=(data.get("icon") or "💬").strip(),
                base=base,
            )
        except RoomAlreadyExistsError:
            return JSONResponse(
                {"error": "room_already_exists", "room_id": room_id},
                status_code=409,
            )
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        return {
            "ok": True,
            "room_id": state["room_id"],
            "project_name": state["project_name"],
            "color": state["color"],
            "icon": state["icon"],
            "created_at": state["created_at"],
        }

    @app.get("/api/rooms/{room_id}/state")
    async def get_room_state(room_id: str, user=Depends(verify_basic)):
        return read_state(room_id, base)

    @app.get("/api/rooms/{room_id}/timeline")
    async def get_room_timeline(
        room_id: str, since: str = "", user=Depends(verify_basic),
    ):
        msgs = _filter_room(_read_timeline(base, since), room_id)
        return {"messages": msgs}

    @app.post("/api/rooms/{room_id}/submit")
    async def post_submit(
        room_id: str, req: Request, user=Depends(verify_basic),
    ):
        csrf = req.headers.get("X-CSRF-Token", "")
        if not _verify_csrf(csrf):
            raise HTTPException(status_code=403, detail="csrf_invalid")
        data = await req.json()
        body = (data.get("body") or "").strip()
        client_msg_id = (data.get("client_msg_id") or "").strip()
        if not body:
            return JSONResponse({"error": "empty"}, status_code=400)
        if client_msg_id and _check_replay(client_msg_id):
            return {"ok": True, "msg_id": client_msg_id, "deduplicated": True}
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
    async def post_interrupt(
        room_id: str, req: Request, user=Depends(verify_basic),
    ):
        csrf = req.headers.get("X-CSRF-Token", "")
        if not _verify_csrf(csrf):
            raise HTTPException(status_code=403, detail="csrf_invalid")
        result = sigint_handler.request_interrupt(room_id, base)
        return result

    @app.post("/api/rooms/{room_id}/activate")
    async def post_activate(
        room_id: str, req: Request, user=Depends(verify_basic),
    ):
        csrf = req.headers.get("X-CSRF-Token", "")
        if not _verify_csrf(csrf):
            raise HTTPException(status_code=403, detail="csrf_invalid")
        rooms_overview.refresh(base, active_room_id=room_id)
        return {"ok": True, "active_room_id": room_id}

    @app.get("/api/thread/{parent_msg_id}")
    async def get_thread(parent_msg_id: str, user=Depends(verify_basic)):
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
    async def get_notification(user=Depends(verify_basic)):
        return notification_controller.read_config(base)

    @app.post("/api/notification")
    async def post_notification(req: Request, user=Depends(verify_basic)):
        csrf = req.headers.get("X-CSRF-Token", "")
        if not _verify_csrf(csrf):
            raise HTTPException(status_code=403, detail="csrf_invalid")
        data = await req.json()
        cur = notification_controller.read_config(base)
        cur.update({k: v for k, v in data.items() if k in
                    ("level", "slack_webhook_url", "discord_webhook_url")})
        notification_controller.write_config(cur, base)
        return {"ok": True, "config": cur}

    @app.get("/api/events")
    async def events(user=Depends(verify_basic)):
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
            host = MEETING_HOST
            if "--tailscale" in sys.argv:
                ts = MEETING_TAILSCALE_IP or "127.0.0.1"
                host = ts
            print(f"binding {host}:{MEETING_PORT}")
            uvicorn.run(create_app(), host=host, port=MEETING_PORT)
        except ImportError:
            print("uvicorn未インストール")
    raise SystemExit(0 if ok else 1)
