"""
relay_worker — R57 Phase C: 順次リレー自動進行 background worker

設計 (R57 3者合意 master_data 準拠):
- server.py から物理プロセス分離 (Uvicorn event loop非ブロック)
- timeline.jsonl + state.json を緩いポーリング (event-driven)
- next_actor (gpt/gemini/claude) を chrome_relay.relay_turn で実呼出
- 応答を inject_ai_message POST → server側で validator + state自動進行 + minutes
- 3者合意 consensus_established=true で 当該room の処理停止

依存 (Phase 1既存12モジュール流用):
- meeting_system.chrome_relay (CDP接続 + tab探索 + 応答抽出)
- meeting_system.state_schema (read_state)
- meeting_system.queue_io (timeline読取)

起動:
    python3 scripts/relay_worker.py --room test_room_001 --cdp-port 9222
    python3 scripts/relay_worker.py --room test_room_001 --base /Users/shuji/Desktop/kitt-voice/meeting_system

止める: Ctrl+C
"""
from __future__ import annotations

import argparse
import asyncio
import json
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from meeting_system import chrome_relay  # noqa: E402
from meeting_system.state_schema import (  # noqa: E402
    DEFAULT_BASE, read_state,
)

SEQUENCE = ["gpt", "gemini", "claude"]
DEFAULT_POLL_INTERVAL = 2.0
DEFAULT_SERVER_BASE = "https://100.70.20.113:8765"

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE


def _log(msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def _http(server_base: str, path: str, method: str = "GET",
          body: dict | None = None, csrf: str | None = None,
          auth: tuple[str, str] | None = None) -> tuple[int, dict]:
    headers = {"Content-Type": "application/json"}
    if csrf:
        headers["X-CSRF-Token"] = csrf
    if auth:
        import base64
        token = base64.b64encode(f"{auth[0]}:{auth[1]}".encode()).decode()
        headers["Authorization"] = f"Basic {token}"
    data = (json.dumps(body, ensure_ascii=False).encode("utf-8")
            if body is not None else None)
    req = urllib.request.Request(
        f"{server_base}{path}", method=method, headers=headers, data=data,
    )
    try:
        with urllib.request.urlopen(req, context=_ctx) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read().decode("utf-8"))
        except Exception:
            payload = {"detail": "non_json_error"}
        return e.code, payload


def _csrf(server_base: str, auth: tuple[str, str] | None) -> str:
    return _http(server_base, "/api/csrf-token", auth=auth)[1]["token"]


def _read_timeline_for_room(base: Path, room_id: str) -> list[dict]:
    path = base / "data" / "timeline.jsonl"
    if not path.exists():
        return []
    msgs = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            m = json.loads(line)
        except json.JSONDecodeError:
            continue
        if m.get("room_id") == room_id:
            msgs.append(m)
    return msgs


def _format_prompt(state: dict, msgs: list[dict], next_actor: str) -> str:
    topic = state.get("current_topic") or state.get("topic_title") or "(議題未設定)"
    lines = [
        f"[Clerk(自動) → {next_actor}: {topic}]",
        f"current_loop: {state.get('total_loops', 0)}",
        f"current_turn_in_loop: {state.get('current_turn_in_loop', 0)}",
        f"next_actor: {next_actor}",
        "",
        "## これまでの発言 (時系列)",
        "",
    ]
    # context window: 最新N件 (R57 Phase Cは簡易、 将来はloop境界で切る)
    recent = msgs[-15:]
    for m in recent:
        actor = m.get("actor", "?")
        body = (m.get("body") or "").strip()
        lines.append(f"### {actor}")
        for ln in body.splitlines():
            lines.append(f"> {ln}")
        lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("# あなた (本ターン) のタスク")
    lines.append("以下4セクションで応答してください:")
    lines.append("1. 自身の意見・回答")
    lines.append("2. 前走者発言への監査・批判")
    lines.append("3. consensus_candidate判定 (consensus_candidate: true|false)")
    lines.append("4. 末尾に必ず inspiration / 末尾token 含む")
    lines.append("")
    lines.append("（合意成立基準: 3者全員 consensus_candidate=true で 2巡目以降）")
    return "\n".join(lines)


async def _drive_one_turn(
    room_id: str, base: Path, cdp_port: int,
    server_base: str, auth: tuple[str, str] | None,
) -> dict:
    state = read_state(room_id, base)
    if state.get("is_consensus_established"):
        return {"done": True, "reason": "consensus_established"}
    if state.get("status") == "ai_processing":
        return {"skip": True, "reason": "ai_processing_in_flight"}

    next_actor = state.get("next_actor") or "gpt"
    if next_actor not in SEQUENCE:
        return {"skip": True, "reason": f"invalid_next_actor:{next_actor}"}

    msgs = _read_timeline_for_room(base, room_id)
    if not msgs:
        return {"skip": True, "reason": "timeline_empty"}

    last_actor = msgs[-1].get("actor")
    if last_actor not in ("shuji", "gpt", "gemini", "claude"):
        return {"skip": True, "reason": f"unknown_last_actor:{last_actor}"}
    if last_actor in SEQUENCE and last_actor == next_actor:
        return {"skip": True, "reason": "next_actor_already_spoke_just_now"}

    prompt = _format_prompt(state, msgs, next_actor)
    _log(f"→ {next_actor} via CDP {cdp_port} ({len(prompt)} chars)")
    try:
        resp_text = await chrome_relay.relay_turn(cdp_port, next_actor, prompt)
    except Exception as e:
        _log(f"⚠ chrome_relay failed: {e}")
        return {"error": str(e), "actor": next_actor}

    _log(f"← {next_actor} {len(resp_text)} chars")

    csrf = _csrf(server_base, auth)
    status, j = _http(
        server_base,
        f"/api/rooms/{room_id}/inject_ai_message", "POST",
        body={"actor": next_actor, "body": resp_text, "raw": resp_text},
        csrf=csrf, auth=auth,
    )
    if status >= 400:
        _log(f"⚠ inject_ai_message {status}: {j}")
        return {"error": f"inject_failed:{status}", "detail": j}

    _log(
        f"✓ injected actor={j.get('actor')} loop={j.get('loop')} "
        f"cons={j.get('consensus_candidate')} "
        f"next={j.get('next_actor')} "
        f"established={j.get('is_consensus_established')}"
    )
    return j


def _heartbeat(base: Path, room_id: str) -> None:
    """R58 Must Fix B: server.py が mtime < 5sで running と判定するためのtouch"""
    try:
        hb_path = base / "data" / "projects" / room_id / "relay_heartbeat.json"
        hb_path.parent.mkdir(parents=True, exist_ok=True)
        hb_path.write_text(
            json.dumps({"ts": __import__("time").time(), "pid": __import__("os").getpid()}),
            encoding="utf-8",
        )
    except Exception:
        pass


async def run_room(
    room_id: str, base: Path, cdp_port: int | None,
    poll: float, server_base: str, auth: tuple[str, str] | None,
) -> None:
    _log(f"start room={room_id} base={base} cdp={cdp_port} poll={poll}s server={server_base}")
    while True:
        try:
            _heartbeat(base, room_id)
            state = read_state(room_id, base)
            if state.get("is_consensus_established"):
                _log("✅ consensus_established — pausing 30s")
                await asyncio.sleep(30)
                continue
            port = cdp_port or state.get("chrome_cdp_port") or 9222
            result = await _drive_one_turn(room_id, base, port, server_base, auth)
            if result.get("done"):
                _log(f"done: {result.get('reason')}")
                await asyncio.sleep(30)
            elif result.get("error"):
                await asyncio.sleep(max(poll, 5.0))
            elif result.get("skip"):
                await asyncio.sleep(poll)
            else:
                await asyncio.sleep(poll)
        except KeyboardInterrupt:
            _log("interrupted")
            return
        except Exception as e:
            _log(f"⚠ loop error: {e}")
            await asyncio.sleep(max(poll, 5.0))


def main() -> int:
    p = argparse.ArgumentParser(description="R57 relay_worker (Phase C)")
    p.add_argument("--room", required=True)
    p.add_argument("--cdp-port", type=int, default=None)
    p.add_argument("--base", default=str(DEFAULT_BASE))
    p.add_argument("--poll", type=float, default=DEFAULT_POLL_INTERVAL)
    p.add_argument("--server", default=DEFAULT_SERVER_BASE,
                   help="server.py base URL (default: https://100.70.20.113:8765)")
    p.add_argument("--basic-user", default=None)
    p.add_argument("--basic-pass", default=None)
    args = p.parse_args()
    auth = ((args.basic_user, args.basic_pass)
            if args.basic_user and args.basic_pass else None)
    try:
        asyncio.run(run_room(
            args.room, Path(args.base).resolve(), args.cdp_port,
            args.poll, args.server, auth,
        ))
    except KeyboardInterrupt:
        return 0
    return 0


def self_test() -> bool:
    """構造のみ検証 (CDP接続なしでテスト)"""
    sample_state = {"total_loops": 1, "current_turn_in_loop": 1, "current_topic": "Test"}
    sample_msgs = [
        {"actor": "shuji", "body": "テスト発言"},
        {"actor": "gpt", "body": "GPT R1\nconsensus_candidate: true"},
    ]
    prompt = _format_prompt(sample_state, sample_msgs, "gemini")
    assert "[Clerk(自動) → gemini" in prompt
    assert "current_loop: 1" in prompt
    assert "テスト発言" in prompt
    assert "GPT R1" in prompt
    assert "consensus_candidate" in prompt
    print("PASS: relay_worker self_test (prompt structure)")
    return True


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        raise SystemExit(0 if self_test() else 1)
    raise SystemExit(main())
