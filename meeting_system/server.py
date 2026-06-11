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
    from fastapi import FastAPI, Request, HTTPException, Depends, UploadFile, File, Form
    from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.security import HTTPBasic, HTTPBasicCredentials
    from fastapi.exceptions import RequestValidationError
except ImportError as _fastapi_import_error:
    FastAPI = None  # type: ignore
    Request = None  # type: ignore
    HTTPException = None  # type: ignore
    Depends = None  # type: ignore
    UploadFile = None  # type: ignore
    File = None  # type: ignore
    Form = None  # type: ignore
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
from . import validator_consensus, validator, minutes, projects
from . import consensus_summary

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

# Phase F: 画像upload
ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg", "image/jpg": ".jpg",
    "image/png": ".png", "image/gif": ".gif", "image/webp": ".webp",
}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10MB


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


# R58.1 #9: Watchdog 180s (Gemini R3仕様確定 + GPT R3/R6全面採用)
WATCHDOG_STALL_SEC = 180.0
_watchdog_fired_at: dict[str, float] = {}


def _check_relay_stall(room_id: str, state: dict, base: Path) -> bool:
    """relay稼働中に timeline が180秒更新なし → System警告inject + status強制idle。

    R61 fix #2: worker pause中の過剰発火防止。
    status が idle以外 (external_wait/blocked/consensus_reached/paused_by_shuji)
    なら 既に stop状態 → Watchdog発火対象外
    """
    # R61 fix #2: stop状態は 既に「Shuji介入待ち」 = Watchdog不要
    if state.get("status") in ("external_wait", "blocked", "consensus_reached", "paused_by_shuji"):
        return False
    if state.get("is_consensus_established"):
        return False
    tl = _timeline_path(base)
    if not tl.exists():
        return False
    tl_age = time.time() - tl.stat().st_mtime
    if tl_age <= WATCHDOG_STALL_SEC:
        return False
    # R61: worker起動直後の猶予 (heartbeat mtime が tl mtimeより新しい → worker新規起動)
    hb = base / "data" / "projects" / room_id / "relay_heartbeat.json"
    if hb.exists():
        hb_mtime = hb.stat().st_mtime
        tl_mtime = tl.stat().st_mtime
        if hb_mtime > tl_mtime:
            # worker起動後 timeline未更新 = worker uptime を見る
            worker_uptime = time.time() - hb_mtime
            # heartbeat 自体は毎iteration update なので、
            # 「heartbeat初回からの経過」 をproxyに first-loop json探す
            try:
                hb_data = json.loads(hb.read_text(encoding="utf-8"))
                start_ts = hb_data.get("start_ts")
                if start_ts:
                    worker_uptime = time.time() - start_ts
            except Exception:
                pass
            if worker_uptime < WATCHDOG_STALL_SEC:
                return False
    age = tl_age
    # 同一stallへの多重発火防止 (5分クールダウン)
    last_fired = _watchdog_fired_at.get(room_id, 0.0)
    if time.time() - last_fired < 300.0:
        return False
    _watchdog_fired_at[room_id] = time.time()

    stalled_actor = (state.get("next_actor") or "?").upper()
    warn_body = (
        f"⚠️ [System] {stalled_actor}の応答が{int(WATCHDOG_STALL_SEC)}秒間"
        "途絶えたため、 リレーを一時停止しコントロールをShujiさんに返却しました"
    )
    record = {
        "room_id": room_id,
        "msg_id": f"watchdog_{room_id}_{int(time.time())}",
        "actor": "validator",
        "body": warn_body,
        "raw": warn_body,
        "tags": {"system": "watchdog_180s"},
        "validator": {"pass": True, "items": ["system_watchdog"]},
    }
    queue_io.append_timeline(record, base=base)

    # R60.1 (Shujiさん指摘 2026-06-10 19:05): "コントロールをShujiさんに返却"
    # と表示してるのに idle のままで worker続行 → 同じactor再呼出 → 永遠 stall
    # 修正: external_wait に切替 → R59 Q3経路でworker auto-pause + Shuji介入待ち
    state["status"] = "external_wait"
    # 次の actor 進めて Shuji再開時に同じstallに再陥らないように
    cur_next = state.get("next_actor")
    seq = ["gpt", "gemini", "claude"]
    if cur_next in seq:
        idx = seq.index(cur_next)
        state["next_actor"] = seq[(idx + 1) % len(seq)]
    write_state_atomic(room_id, state, base)
    try:
        notification_controller.notify(
            f"relay stall検知: {stalled_actor} {int(WATCHDOG_STALL_SEC)}s無応答 (room={room_id}) → external_wait",
            level="normal", base=base,
        )
    except Exception:
        pass
    return True


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

    # R65.1: iOS PWAの強キャッシュ対策 — UIファイルは毎回鮮度確認させる (304は軽量)
    _NO_CACHE = {"Cache-Control": "no-cache, must-revalidate"}

    @app.get("/")
    async def index(user=Depends(verify_basic)):
        idx = STATIC / "index.html"
        if not idx.exists():
            return JSONResponse({"error": "index.html not found"}, status_code=404)
        return FileResponse(idx, headers=_NO_CACHE)

    @app.get("/app.js")
    async def app_js(user=Depends(verify_basic)):
        return FileResponse(STATIC / "app.js", headers=_NO_CACHE)

    @app.get("/style.css")
    async def style_css(user=Depends(verify_basic)):
        return FileResponse(STATIC / "style.css", headers=_NO_CACHE)

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
        data = rooms_overview.refresh(base)
        # R65.1: UI自動更新 — app.js の mtime を ui_version として返す。
        # client は load時の値と比較し、 変化したら自動full reload (iOS PWAキャッシュ対策)
        try:
            data["global"]["ui_version"] = str(int((STATIC / "app.js").stat().st_mtime))
        except Exception:
            pass
        return data

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
        st = read_state(room_id, base)
        # R58 Must Fix B: relay_worker.py heartbeat状態 を 同梱
        hb_path = base / "data" / "projects" / room_id / "relay_heartbeat.json"
        rw_state = "off"
        rw_age = None
        if hb_path.exists():
            try:
                age = time.time() - hb_path.stat().st_mtime
                rw_age = age
                # R58.1 #8: 5.0s → 10.0s (Gemini R3: macOS 12 I/Oバッファによる
                # ランプチャタリング防止バッファ)
                if age < 10.0:
                    rw_state = "running"
                else:
                    rw_state = "off"
            except Exception:
                pass
        # R58.1 #9: Watchdog 180s — relay稼働中のCDPハング救済
        if rw_state == "running":
            try:
                if _check_relay_stall(room_id, st, base):
                    st = read_state(room_id, base)
            except Exception:
                pass
        if st.get("is_consensus_established"):
            ce_at = st.get("consensus_established_at")
            try:
                if ce_at:
                    ce_dt = datetime.fromisoformat(ce_at)
                    if (datetime.now(JST) - ce_dt).total_seconds() < 10:
                        rw_state = "done"
            except Exception:
                pass
        st["relay_worker_state"] = rw_state
        if rw_age is not None:
            st["relay_worker_heartbeat_age_sec"] = round(rw_age, 1)
        # R61 E: stall_reason をヘッダ表示用に同梱
        stall_reason = None
        st_status = st.get("status")
        if st.get("is_consensus_established"):
            stall_reason = "✅ 合意成立 (再開で続行可)"
        elif st_status == "external_wait":
            stall_reason = "⌛ AI判断: 外部待ち (再開で続行可)"
        elif st_status == "blocked":
            stall_reason = "⏸ AI判断: 人間判断待ち"
        elif st_status == "paused_by_shuji":
            stall_reason = "🛑 Shujiさんが割込中"
        elif st_status == "ai_processing" and rw_state == "off":
            stall_reason = "⚠️ AI処理中だが relay_worker停止"
        elif rw_state == "off" and st_status == "idle":
            stall_reason = "💤 relay_worker未起動 (Mac側で起動必要)"
        st["stall_reason"] = stall_reason
        return st

    @app.get("/api/rooms/{room_id}/timeline")
    async def get_room_timeline(
        room_id: str, since: str = "", user=Depends(verify_basic),
    ):
        msgs = _filter_room(_read_timeline(base, since), room_id)
        # R58 Must Fix A: 各msgに read_count + 4者中の comma separated read_by を同梱
        rr_path = base / "data" / "projects" / room_id / "read_receipts.json"
        if rr_path.exists():
            try:
                rr = json.loads(rr_path.read_text(encoding="utf-8"))
                for m in msgs:
                    info = rr.get(m.get("msg_id", ""), {})
                    read_by = info.get("read_by", [])
                    # author を read_by から除く (受信者のみカウント)
                    author = m.get("actor")
                    receivers = [r for r in read_by if r != author]
                    m["read_count"] = len(receivers)
                    m["read_by"] = receivers
                    m["read_total"] = 3  # 4者 - 自分 = 3者がreader
            except Exception:
                pass
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
        state["unread_count"] = 0  # Phase D: Shuji発言で 既読扱い
        validator_consensus.reset_consensus_on_shuji_input(room_id, base)
        write_state_atomic(room_id, state, base)
        # R58 Must Fix A: shuji が tab確認で 全AI既読
        try:
            rr_path = base / "data" / "projects" / room_id / "read_receipts.json"
            if rr_path.exists():
                rr = json.loads(rr_path.read_text(encoding="utf-8"))
                for m_id, info in rr.items():
                    if "shuji" not in info.get("read_by", []):
                        info["read_by"].append("shuji")
                rr_path.write_text(
                    json.dumps(rr, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
        except Exception:
            pass
        record = {
            "room_id": room_id,
            "msg_id": msg_id,
            "actor": "shuji",
            "body": body,
            "raw": body,
            "tags": {},
            "validator": {"pass": True, "items": ["shuji_direct"]},
        }
        attachments = data.get("attachments")
        if isinstance(attachments, list) and attachments:
            record["attachments"] = attachments
        queue_io.append_timeline(record, base=base)
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

    # R61 D: 議題再開 (iPhone PWAから ワンタップで stall解除)
    @app.post("/api/rooms/{room_id}/resume_relay")
    async def post_resume_relay(
        room_id: str, req: Request, user=Depends(verify_basic),
    ):
        csrf = req.headers.get("X-CSRF-Token", "")
        if not _verify_csrf(csrf):
            raise HTTPException(status_code=403, detail="csrf_invalid")
        state = read_state(room_id, base)
        prev_status = state.get("status")
        prev_loops = state.get("total_loops", 0)
        # Stall 関連の status を idle に戻し、 next_actor進める
        # R63.1: paused_by_shuji も解除対象 (割込→submit→再開 が始まらないbug修正)
        if prev_status in ("blocked", "external_wait", "consensus_reached",
                           "paused_by_shuji"):
            state["status"] = "idle"
        if state.get("is_consensus_established"):
            state["is_consensus_established"] = False
            state["consensus_established_at"] = None
            state["consensus_established_loop"] = None
            state["consensus_established_reason"] = "shuji_resumed"
        # R61 fix: max_loops制限を解除するため total_loopsを 0にreset
        # (timeline.jsonl の過去発言は不変、 cands/loops_historyのみ resetで新議題扱い)
        state["total_loops"] = 0
        state["current_turn_in_loop"] = 0
        state["consensus_candidates_per_loop"] = {}
        state["loops_history"] = []
        # next_actor は gpt にreset (新議題は順序最初から)
        state["next_actor"] = "gpt"
        write_state_atomic(room_id, state, base)
        return {
            "ok": True,
            "prev_status": prev_status,
            "prev_loops": prev_loops,
            "next_actor": state.get("next_actor"),
            "loops_reset": True,
        }

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

    # R60 ②: projects list / register / autolink
    @app.get("/api/projects")
    async def get_projects(user=Depends(verify_basic)):
        return {"projects": projects.list_projects(base)}

    @app.post("/api/projects")
    async def post_register_project(
        req: Request, user=Depends(verify_basic),
    ):
        csrf = req.headers.get("X-CSRF-Token", "")
        if not _verify_csrf(csrf):
            raise HTTPException(status_code=403, detail="csrf_invalid")
        data = await req.json()
        try:
            res = projects.register_project(
                project_id=data.get("project_id", ""),
                repo_path=data.get("repo_path"),
                tool=data.get("tool", "manual"),
                room_id=data.get("room_id", ""),
                participants=data.get("participants"),
                default_order=data.get("default_order"),
                base=base,
            )
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        return {"ok": True, "project": res}

    @app.get("/api/projects/autolink")
    async def get_autolink(cwd: str, user=Depends(verify_basic)):
        """起動時自動紐付け。 cwd を投げると 1件返るか None (=Shuji確認必要)"""
        found = projects.find_project_by_path(cwd, base)
        return {
            "matched": bool(found),
            "project": found,
            "cwd": cwd,
        }

    # R59 Q4: 会議室編集 PATCH (名前/説明/色/アイコン/参加AI/順番/議題/アーカイブ + 変更履歴)
    EDITABLE_FIELDS = {
        "project_name", "description", "color", "icon",
        "current_topic", "topic_title",
        "participants", "actor_sequence", "archived",
        "notify_level",
        # R60 ②
        "project_id", "repo_path", "tool",
    }

    @app.patch("/api/rooms/{room_id}")
    async def patch_room(
        room_id: str, req: Request, user=Depends(verify_basic),
    ):
        csrf = req.headers.get("X-CSRF-Token", "")
        if not _verify_csrf(csrf):
            raise HTTPException(status_code=403, detail="csrf_invalid")
        if "/" in room_id or ".." in room_id:
            raise HTTPException(status_code=400, detail="invalid_room_id")
        data = await req.json()
        if not isinstance(data, dict):
            return JSONResponse({"error": "invalid_body"}, status_code=400)
        state = read_state(room_id, base)
        if not state.get("room_id"):
            raise HTTPException(status_code=404, detail="room_not_found")
        changes = []
        for k, v in data.items():
            if k not in EDITABLE_FIELDS:
                continue
            old = state.get(k)
            if old == v:
                continue
            state[k] = v
            changes.append({"field": k, "old": old, "new": v})
        if not changes:
            return {"ok": True, "changes": [], "msg": "no_changes"}
        # 変更履歴 append-only
        state.setdefault("edit_history", []).append({
            "ts": datetime.now(JST).isoformat(),
            "editor": "shuji",
            "changes": changes,
        })
        write_state_atomic(room_id, state, base)
        return {"ok": True, "changes": changes}

    @app.post("/api/rooms/{room_id}/inject_ai_message")
    async def post_inject_ai_message(
        room_id: str, req: Request, user=Depends(verify_basic),
    ):
        csrf = req.headers.get("X-CSRF-Token", "")
        if not _verify_csrf(csrf):
            raise HTTPException(status_code=403, detail="csrf_invalid")
        data = await req.json()
        actor = (data.get("actor") or "").strip().lower()
        if actor not in ("gpt", "gemini", "claude", "validator"):
            return JSONResponse(
                {"error": "invalid_actor", "allowed": ["gpt", "gemini", "claude", "validator"]},
                status_code=400,
            )
        body = (data.get("body") or "").strip()
        if not body:
            return JSONResponse({"error": "empty_body"}, status_code=400)
        # R58.1 #10: 順番違反actor 409拒否 (発言Claude R3提案 + GPT R4/R6 + Gemini R7全面採用)
        # validator は System message/監査inject用に順番外許可
        if actor in ("gpt", "gemini", "claude"):
            _turn_state = read_state(room_id, base)
            _expected = _turn_state.get("next_actor")
            if _expected and actor != _expected:
                return JSONResponse(
                    {"error": "turn_violation",
                     "expected_actor": _expected, "got_actor": actor},
                    status_code=409,
                )
        client_msg_id = (data.get("client_msg_id") or "").strip()
        if client_msg_id and _check_replay(client_msg_id):
            return {"ok": True, "msg_id": client_msg_id, "deduplicated": True}
        raw = data.get("raw") or body
        tags = data.get("tags") or {}
        loop_override = data.get("loop")

        speech_result = validator.validate_speech(body, actor)
        consensus_candidate = bool(speech_result.get("consensus_candidate"))
        consensus_value = speech_result.get("consensus_value", "false")  # R59 Q3
        pwa_summary = validator.extract_pwa_summary(body)  # R59 Q2
        v_results = speech_result.get("results") or {}
        v_items = [k for k, v in v_results.items() if v.get("passed")]
        v_violations = {k: v.get("violations") for k, v in v_results.items() if not v.get("passed")}
        validator_payload = {
            "pass": bool(speech_result.get("all_passed")),
            "items": v_items or ["auto_validated"],
        }
        if v_violations:
            validator_payload["violations"] = v_violations

        # Allow caller-provided validator payload to override (e.g. relay_worker forcing)
        if data.get("validator"):
            validator_payload = data["validator"]

        msg_id = queue_io.atomic_append(
            f"{actor}_response_{room_id}", body, sender=actor,
            msg_id=client_msg_id or None, base=base,
        )

        new_state = validator_consensus.record_actor_speech(
            room_id=room_id, actor=actor, msg_id=msg_id,
            consensus_candidate=consensus_candidate, base=base,
            consensus_value=consensus_value,  # R59 Q3
        )
        # R59 Q3 / R61 B: blocked/external_wait → 同loop内に2者以上いる時のみ全体停止
        # 1者だけなら 議論継続 (他2者で判定可能なケース、 Shujiさん指示 2026-06-10)
        if consensus_value in ("blocked", "external_wait"):
            try:
                _st = read_state(room_id, base)
                cur_loop_key = str(_st.get("total_loops", 0))
                cur_cands = _st.get("consensus_candidates_per_loop", {}).get(cur_loop_key, {})
                same_loop_waiters = sum(
                    1 for v in cur_cands.values()
                    if v in ("blocked", "external_wait")
                )
                if same_loop_waiters >= 2:
                    _st["status"] = consensus_value
                    write_state_atomic(room_id, _st, base)
                # else: 1者だけなら status維持 (worker進行継続)
            except Exception:
                pass
        loop_for_record = loop_override if loop_override is not None else new_state.get("total_loops")

        record = {
            "room_id": room_id,
            "msg_id": msg_id,
            "actor": actor,
            "body": body,
            "raw": raw,
            "tags": tags,
            "validator": validator_payload,
            "loop": loop_for_record,
            "summary": pwa_summary,  # R59 Q2: PWA要約 (200字)
            "consensus_value": consensus_value,  # R59 Q3
        }
        queue_io.append_timeline(record, base=base)

        consensus_state = validator_consensus.mark_consensus_if_established(room_id, base=base)
        minutes_info = None
        notify_info = None
        newly_established = (
            consensus_state.get("is_consensus_established")
            and not new_state.get("is_consensus_established")
        )
        summary_info = None
        if newly_established:
            try:
                minutes_info = minutes.generate_minutes(
                    room_id,
                    consensus_state.get("consensus_established_loop") or loop_for_record,
                    base=base,
                )
            except Exception as e:
                minutes_info = {"error": str(e)}
            # R64: 合意まとめ自動提示 (timeline inject + 議事録 + フラグ反転)
            try:
                summary_info = consensus_summary.generate_and_inject(room_id, base=base)
            except Exception as e:
                summary_info = {"error": str(e)}
            try:
                notify_info = notification_controller.notify_consensus_reached(
                    room_id=room_id,
                    topic_title=consensus_state.get("current_topic") or consensus_state.get("topic_title"),
                    base=base,
                )
            except Exception as e:
                notify_info = {"error": str(e)}

        # validator FAIL → 異常通知 (level=normal)、 ただし connstrain unset時はskip
        if not validator_payload.get("pass"):
            try:
                notification_controller.notify(
                    f"⚠️ validator FAIL: room={room_id} actor={actor} "
                    f"items={validator_payload.get('items')} "
                    f"violations={validator_payload.get('violations')}",
                    level="normal",
                    title="ぐるぐる3者会議 — validator_error",
                    base=base,
                )
            except Exception:
                pass  # 通知失敗で本体APIを落とさない

        # unread_count: AI応答inject時に+1 (Shujiさん未確認分)
        try:
            cur_state = read_state(room_id, base)
            cur_state["unread_count"] = int(cur_state.get("unread_count", 0)) + 1
            write_state_atomic(room_id, cur_state, base)
        except Exception:
            pass

        # R58 Must Fix A: 既読(n/3) 実値連動
        # - 新AI inject = 既存全msgs の read_by に 今 inject した actor を追加 (発言前に過去履歴を読んだ扱い)
        # - 自msgは read_by = [actor] で開始 (n=0)
        try:
            rr_path = base / "data" / "projects" / room_id / "read_receipts.json"
            rr_path.parent.mkdir(parents=True, exist_ok=True)
            rr = {}
            if rr_path.exists():
                try:
                    rr = json.loads(rr_path.read_text(encoding="utf-8"))
                except Exception:
                    rr = {}
            for m_id, info in rr.items():
                if actor not in info.get("read_by", []):
                    info.setdefault("read_by", []).append(actor)
            rr[msg_id] = {
                "author": actor,
                "read_by": [actor],
                "ts": datetime.now(JST).isoformat(),
            }
            rr_path.write_text(
                json.dumps(rr, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

        return {
            "ok": True, "msg_id": msg_id, "actor": actor,
            "loop": loop_for_record,
            "consensus_candidate": consensus_candidate,
            "validator_pass": validator_payload.get("pass"),
            "next_actor": consensus_state.get("next_actor"),
            "is_consensus_established": consensus_state.get("is_consensus_established"),
            "minutes": minutes_info,
            "consensus_summary": summary_info,
        }

    @app.post("/api/rooms/{room_id}/upload")
    async def post_upload(
        room_id: str, req: Request, user=Depends(verify_basic),
    ):
        csrf = req.headers.get("X-CSRF-Token", "")
        if not _verify_csrf(csrf):
            raise HTTPException(status_code=403, detail="csrf_invalid")
        # room_id safety
        if "/" in room_id or ".." in room_id or not room_id.strip():
            raise HTTPException(status_code=400, detail="invalid_room_id")
        form = await req.form()
        upload = form.get("file")
        if upload is None or not hasattr(upload, "filename"):
            raise HTTPException(status_code=400, detail="file_missing")
        content_type = (upload.content_type or "").lower()
        ext = ALLOWED_IMAGE_TYPES.get(content_type)
        if not ext:
            return JSONResponse(
                {"error": "invalid_content_type",
                 "allowed": list(ALLOWED_IMAGE_TYPES.keys()),
                 "got": content_type},
                status_code=400,
            )
        data = await upload.read()
        if len(data) > MAX_UPLOAD_BYTES:
            return JSONResponse(
                {"error": "file_too_large",
                 "max_bytes": MAX_UPLOAD_BYTES, "got": len(data)},
                status_code=413,
            )
        if not data:
            return JSONResponse({"error": "empty_file"}, status_code=400)
        att_dir = base / "data" / "attachments" / room_id
        att_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(JST).strftime("%Y%m%d_%H%M%S_%f")
        secure_name = f"{ts}{ext}"
        out_path = att_dir / secure_name
        out_path.write_bytes(data)
        url = f"/api/rooms/{room_id}/attachments/{secure_name}"
        return {
            "ok": True, "url": url, "filename": secure_name,
            "content_type": content_type, "size_bytes": len(data),
        }

    @app.get("/api/rooms/{room_id}/attachments/{filename}")
    async def get_attachment(
        room_id: str, filename: str, user=Depends(verify_basic),
    ):
        if "/" in room_id or ".." in room_id:
            raise HTTPException(status_code=400, detail="invalid_room_id")
        if "/" in filename or ".." in filename or "\\" in filename:
            raise HTTPException(status_code=400, detail="invalid_filename")
        path = base / "data" / "attachments" / room_id / filename
        if not path.exists():
            raise HTTPException(status_code=404, detail="not_found")
        return FileResponse(path)

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
        "/api/rooms/{room_id}/inject_ai_message",
        "/api/rooms/{room_id}/resume_relay",
        "/api/rooms/{room_id}/upload",
        "/api/rooms/{room_id}/attachments/{filename}",
        "/api/projects", "/api/projects/autolink",
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
