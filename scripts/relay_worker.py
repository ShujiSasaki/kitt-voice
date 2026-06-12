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
    python3 scripts/relay_worker.py                       # R63: 自動roomルーター (FIFO最古優先)
    python3 scripts/relay_worker.py --room test_room_001  # 従来: 固定room
    python3 scripts/relay_worker.py --cdp-port 9222 --base /Users/shuji/Desktop/kitt-voice/meeting_system

R63 自動ルーター (3者合意 2026-06-11 07:07):
- --room 省略時、 全room走査 → 最古の未処理Shuji submitの部屋へ自動アタッチ (FIFO)
- 現部屋が収束 (合意成立/blocked/external_wait/max_loops) するまで切替えない
- 同一部屋の複数submitも投入順処理 (queue_io ts が保証)
- inject堅牢化: 200確認 + 失敗時1回リトライ + ターン完了ログ
- 単一worker直列のまま (多重worker不採用 — 3 AI tabは1セットのため)

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
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from meeting_system import chrome_relay  # noqa: E402
from meeting_system.state_schema import (  # noqa: E402
    DEFAULT_BASE, read_state, write_state_atomic,
)

SEQUENCE = ["gpt", "gemini", "claude"]
DEFAULT_POLL_INTERVAL = 2.0
DEFAULT_SERVER_BASE = "https://100.70.20.113:8765"
# R58.2: max_loop limit (runaway防止 — 2026-06-10 36-loop runaway事件)
DEFAULT_MAX_LOOPS = 5
# R58.2: prompt縮小 (timeline最新N件のみ抜粋、 19000+ chars → ~3000 chars想定)
DEFAULT_RECENT_MSGS = 9  # 直近3 loops分 (= 1 loop 3 msgs × 3)
# R60 ③: 連続無応答失敗 → external_wait自動停止 (Claude R5提案)
MAX_CONSECUTIVE_FAILURES = 3
_consecutive_failures: dict[str, int] = {}

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


# ---------------------------------------------------------------------------
# R63: 自動roomルーター (FIFO最古優先)
# ---------------------------------------------------------------------------

# 収束扱いの status (これらは Shuji介入 or 新submitまで relay対象外)
STOP_STATUSES = ("blocked", "external_wait", "consensus_reached", "paused_by_shuji",
                 "max_loops_reached")  # R66


def _mark_max_loops_status(room_id: str, base: Path) -> bool:
    """R66: status=max_loops_reached を1回だけ書込 (冪等)。書込んだらTrue"""
    try:
        st = read_state(room_id, base)
        if st.get("status") == "max_loops_reached":
            return False
        st["status"] = "max_loops_reached"
        write_state_atomic(room_id, st, base)
        return True
    except Exception:
        return False


def _notify_max_loops(
    room_id: str, base: Path, state: dict, max_loops: int,
    server_base: str, auth: tuple[str, str] | None,
) -> None:
    """R66: max_loops到達の停止案内 — status書込 + validator inject + Mac通知 (1回だけ)"""
    if not _mark_max_loops_status(room_id, base):
        return  # 既に通知済み
    loops = state.get("total_loops", 0)
    cands = state.get("consensus_candidates_per_loop", {}).get(str(loops), {})
    cands_view = (", ".join(f"{a}={v}" for a, v in cands.items()) or "記録なし")
    now_jst = time.strftime("%Y-%m-%d %H:%M:%S")
    body = (
        f"⚠️ [System] ループ上限 (max_loops={max_loops}) 到達 — 自動リレーを停止しました\n"
        f"- 部屋: {state.get('project_name') or room_id}\n"
        f"- 到達loop: {loops}/{max_loops}\n"
        f"- 停止時刻: {now_jst} JST\n"
        f"- 最終巡の判定: {cands_view}\n"
        f"- 次の操作: ▶再開 (loop数リセットで議論続行) / 新しい指示をsubmitしても再開します\n"
        f"[Validator-Verify: R66-MAXLOOPS-NOTIFY]"
    )
    try:
        csrf = _csrf(server_base, auth)
        _http(
            server_base, f"/api/rooms/{room_id}/inject_ai_message", "POST",
            body={"actor": "validator", "body": body}, csrf=csrf, auth=auth,
        )
    except Exception as e:
        _log(f"⚠ max_loops通知inject失敗: {e}")
    try:
        from meeting_system import notification_controller
        notification_controller.notify(
            f"ループ上限到達: {state.get('project_name') or room_id} "
            f"({loops}/{max_loops}巡) — ▶再開待ち",
            level="normal", base=base,
        )
    except Exception:
        pass
    _log(f"⚠ R66 max_loops通知 room={room_id} loops={loops}/{max_loops}")


def _find_orphan_max_loops(base: Path, max_loops: int) -> list[str]:
    """R66: 到達済みなのに status未マークのroom (worker再起動の取りこぼし救済)"""
    result = []
    proj_dir = base / "projects"
    if not proj_dir.exists():
        return result
    for d in sorted(proj_dir.iterdir()):
        if not (d / "state.json").exists():
            continue
        try:
            st = read_state(d.name, base)
        except Exception:
            continue
        if (not st.get("archived")
                and not st.get("is_consensus_established")
                and st.get("status") not in STOP_STATUSES
                and st.get("total_loops", 0) >= max_loops):
            result.append(d.name)
    return result


def _parse_ts(s: str | None) -> datetime | None:
    """timeline形式 '2026-06-11 06:57:05 JST' と ISO形式の両対応 (naive JSTで比較)"""
    if not s:
        return None
    try:
        return datetime.strptime(s.replace("T", " ")[:19], "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return None


def _room_pending(state: dict, max_loops: int) -> bool:
    """未処理のShuji submitを持ち relay進行が必要なroomか"""
    if state.get("archived"):
        return False
    if state.get("is_consensus_established"):
        return False
    if state.get("status") in STOP_STATUSES:
        return False
    if state.get("total_loops", 0) >= max_loops:
        return False
    if not state.get("last_shuji_input_ts"):
        return False  # 一度もsubmitされていないroom
    return True


def _pending_since(room_id: str, base: Path, state: dict) -> datetime | None:
    """FIFO key = 現在の未処理batchの最初のShuji submit時刻。

    最後のAI発言より後のshuji発言群 = 待機中batch → その先頭ts。
    議論進行中 (最後がAI発言) なら state.last_shuji_input_ts にfallback。
    """
    msgs = _read_timeline_for_room(base, room_id)
    last_ai_idx = -1
    for i, m in enumerate(msgs):
        if m.get("actor") in SEQUENCE:
            last_ai_idx = i
    waiting = [m for m in msgs[last_ai_idx + 1:] if m.get("actor") == "shuji"]
    ts = _parse_ts(waiting[0].get("ts")) if waiting else None
    if ts is None:
        ts = _parse_ts(state.get("last_shuji_input_ts"))
    return ts


def _scan_pending_rooms(base: Path, max_loops: int) -> list[tuple[datetime, str]]:
    """全room走査 → pending roomを (pending_since, room_id) 昇順 (FIFO) で返す"""
    result: list[tuple[datetime, str]] = []
    proj_dir = base / "projects"
    if not proj_dir.exists():
        return result
    for d in sorted(proj_dir.iterdir()):
        if not (d / "state.json").exists():
            continue
        room_id = d.name
        try:
            state = read_state(room_id, base)
        except Exception:
            continue
        if not _room_pending(state, max_loops):
            continue
        ts = _pending_since(room_id, base, state)
        if ts is None:
            continue
        result.append((ts, room_id))
    result.sort(key=lambda x: x[0])
    return result


def _converged_reason(state: dict, max_loops: int) -> str | None:
    """現在の部屋が「一区切り」 (収束) したか。 切替してよい理由 or None"""
    if state.get("archived"):
        return "archived"
    if state.get("is_consensus_established"):
        return "consensus_established"
    st = state.get("status")
    if st in STOP_STATUSES:
        return f"status={st}"
    if state.get("total_loops", 0) >= max_loops:
        return f"max_loops={max_loops}"
    return None


# タブ安定運用 (2026-06-12): 会話肥大の自動防止 — 一定ターン数 or 連続スロー応答で
# gpt/gemini を新規会話へ自動リフレッシュ (claudeはcode session専用のため対象外)
CONV_RESET_TURNS = 30
SLOW_TURN_SEC = 120.0
CONV_RESET_SLOW_STREAK = 2
_turns_since_reset: dict[str, int] = {}
_slow_streak: dict[str, int] = {}


def _needs_conversation_reset(actor: str) -> str | None:
    if actor not in ("gpt", "gemini"):
        return None
    if _turns_since_reset.get(actor, 0) >= CONV_RESET_TURNS:
        return f"turns>={CONV_RESET_TURNS}"
    if _slow_streak.get(actor, 0) >= CONV_RESET_SLOW_STREAK:
        return f"slow_streak>={CONV_RESET_SLOW_STREAK} (応答{int(SLOW_TURN_SEC)}秒超が連続)"
    return None


def _record_turn_duration(actor: str, dur_sec: float) -> None:
    _turns_since_reset[actor] = _turns_since_reset.get(actor, 0) + 1
    _slow_streak[actor] = (_slow_streak.get(actor, 0) + 1) if dur_sec > SLOW_TURN_SEC else 0


# stale-dup guard (2026-06-12): 巨大化した会話でタイムアウト→リロード後、
# 画面に残った過去応答を再取得して重複injectする事故の遮断
# (実害: 🔧部屋にGPT同一1006文字応答が3連続inject)
_recent_resp_hashes: dict[str, list[str]] = {}


def _resp_hash(resp_text: str) -> str:
    import hashlib
    return hashlib.sha1((resp_text or "").strip().encode("utf-8", "replace")).hexdigest()


def _is_stale_duplicate(actor: str, resp_text: str) -> bool:
    return _resp_hash(resp_text) in _recent_resp_hashes.get(actor, [])


def _remember_resp(actor: str, resp_text: str) -> None:
    lst = _recent_resp_hashes.setdefault(actor, [])
    lst.append(_resp_hash(resp_text))
    del lst[:-5]  # 直近5件のみ保持


def _validate_room_token(resp_text: str, room_id: str) -> str:
    """R67 routing_validation: 応答末尾の部屋トークン検証。

    返値: 'ok' / 'missing' / 'wrong:<検出された別room>'
    """
    import re
    found = re.findall(r"\[Room:\s*([A-Za-z0-9_\-]+)\s*\]", resp_text or "")
    if not found:
        return "missing"
    if found[-1] == room_id:
        return "ok"
    return f"wrong:{found[-1]}"


def _format_prompt(
    state: dict, msgs: list[dict], next_actor: str,
    recent_n: int = DEFAULT_RECENT_MSGS,
) -> str:
    topic = state.get("current_topic") or state.get("topic_title") or "(議題未設定)"
    total_loops = state.get("total_loops", 0)
    room_id = state.get("room_id", "")
    lines = [
        f"[Clerk(自動) → {next_actor}: {topic}]",
        f"room_id: {room_id}",
        f"current_loop: {total_loops}",
        f"current_turn_in_loop: {state.get('current_turn_in_loop', 0)}",
        f"next_actor: {next_actor}",
        "",
        f"⚠️ 部屋分離 (R67): これは部屋『{room_id}』のターンです。",
        "- この会話windowは複数の部屋で共用されています。直前に別の部屋の議題へ回答していても、その内容を再送しないこと。",
        "- 本プロンプトに含まれる議題と直近発言のみに基づいて回答すること。",
        "- あなたの過去の回答がここに見えなくても「同一ターンの再配信」と解釈しないこと (別部屋のターンだった可能性が高い)。",
        "",
    ]
    # R58.2: 最初のShuji発言 (議題本文) を必ず含める
    shuji_first = next((m for m in msgs if m.get("actor") == "shuji"), None)
    if shuji_first:
        lines.append("## 議題 (Shuji原文)")
        lines.append("")
        for ln in (shuji_first.get("body") or "").splitlines():
            lines.append(f"> {ln}")
        lines.append("")
    if total_loops >= 3:
        lines.append(f"## 進行状況サマリー (loops完了: {total_loops})")
        lines.append("※過去 timeline は省略 (最新発言のみ提示)、 議論長期化のため簡潔判定を求む")
        lines.append("")
    lines.append(f"## 直近の発言 (最新{recent_n}件)")
    lines.append("")
    recent = msgs[-recent_n:]
    for m in recent:
        actor = m.get("actor", "?")
        body = (m.get("body") or "").strip()
        # R58.2: 長文は切り詰め
        if len(body) > 600:
            body = body[:600] + "\n…(中略)…"
        lines.append(f"### {actor} (loop={m.get('loop','-')})")
        for ln in body.splitlines():
            lines.append(f"> {ln}")
        lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("# あなた (本ターン) のタスク")
    lines.append("以下5セクションで応答してください:")
    lines.append("1. 自身の意見・回答 (簡潔に、 1000文字以内推奨)")
    lines.append("2. 前走者発言への監査・批判")
    lines.append("3. consensus_candidate判定 (R59 Q3: true / false / blocked / external_wait)")
    lines.append("   - true: 合意成立可")
    lines.append("   - false: 議論継続必要")
    lines.append("   - blocked: 人間の判断待ち (自動relay停止)")
    lines.append("   - external_wait: 外部ログ/操作待ち (自動relay停止)")
    lines.append("4. あなたの発言の要点を約200文字の口語で <pwa_summary>〜</pwa_summary> タグに入れて書く (この指示文をタグ内にコピーしない)")
    lines.append("5. 末尾に必ず Verify token 含む")
    lines.append(f"6. 最終行に必ず [Room: {room_id}] の1行を含める (R67 部屋ルーティング検証用 — 欠落/不一致は再送要求されます)")
    lines.append("")
    lines.append("(合意成立基準: 3者全員 consensus_candidate=true で 2巡目以降)")
    if total_loops >= 2:
        lines.append("")
        lines.append("⚠️ Shujiさんからの指示 (2026-06-10 18:55):")
        lines.append("「回答が安定しない。 GPTとGeminiが揺れることが多い」")
        lines.append("- 過去のloopで他者が既に true表明済なら、 大きな未解決リスクがない限り true 同意で収束させよ")
        lines.append("- 完璧を求めて false / external_wait を連発しない")
        lines.append("- 「中略」 「証跡不足」 等の場合は **具体的に何の追加証跡が必要か** を 1点だけ明示せよ (今回は事務Claudeが必ず再inject)")
        lines.append("- 改善余地が 'nice-to-have' レベルなら true、 'must-fix' なら false")
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

    # R59 bug fix: Watchdog validator inject等は relay順序に影響しない
    # → 最後msgが validator/system系なら 1個手前を「実 last_actor」 とみなす
    last_real = next(
        (m for m in reversed(msgs)
         if m.get("actor") in ("shuji", "gpt", "gemini", "claude")),
        None,
    )
    if last_real is None:
        return {"skip": True, "reason": "no_real_last_actor"}
    last_actor = last_real.get("actor")
    # R61 fix #5 (Fable5 root cause解明 2026-06-10 21:05):
    # resume_relay 後に next_actor=gpt へ reset されると、
    # timeline 最後の実発言者も gpt のケースで 永久 silent skip していた。
    # → 「直前発言」 とみなすのは last_real が 120秒以内の場合のみ。
    # それより古い = reset/再開後 → 重複送信リスクなし → 進行してよい。
    if last_actor in SEQUENCE and last_actor == next_actor:
        last_ts_recent = False
        ts_str = last_real.get("ts", "")
        try:
            from datetime import datetime as _dt
            # "2026-06-10 20:07:45 JST" 形式
            t = _dt.strptime(ts_str[:19], "%Y-%m-%d %H:%M:%S")
            age_sec = (_dt.now() - t).total_seconds()
            last_ts_recent = age_sec < 120.0
        except Exception:
            last_ts_recent = True  # parse不能なら安全側 (skip)
        if last_ts_recent:
            return {"skip": True, "reason": "next_actor_already_spoke_just_now"}
        # 古い発言 → 進行 (重複防止は server側 R58.1 #10 の 409 guardが二重防御)

    prompt = _format_prompt(state, msgs, next_actor)
    # タブ安定運用: 会話肥大なら送信前に新規会話へリフレッシュ
    reset_reason = _needs_conversation_reset(next_actor)
    if reset_reason:
        _log(f"♻ {next_actor} 会話リフレッシュ ({reset_reason})")
        try:
            if await chrome_relay.reset_conversation(cdp_port, next_actor):
                _turns_since_reset[next_actor] = 0
                _slow_streak[next_actor] = 0
                _log(f"♻ {next_actor} 新規会話へ移行完了")
        except Exception as e:
            _log(f"⚠ 会話リフレッシュ失敗 (そのまま続行): {e}")
    _log(f"→ {next_actor} [room={room_id}] via CDP {cdp_port} ({len(prompt)} chars)")
    _turn_t0 = time.time()
    try:
        resp_text = await chrome_relay.relay_turn(cdp_port, next_actor, prompt)
    except Exception as e:
        _log(f"⚠ chrome_relay failed: {e}")
        # R60 ③: 連続失敗カウンタ加算 → MAX到達で external_wait inject
        _consecutive_failures[room_id] = _consecutive_failures.get(room_id, 0) + 1
        if _consecutive_failures[room_id] >= MAX_CONSECUTIVE_FAILURES:
            _log(
                f"⛔ {MAX_CONSECUTIVE_FAILURES} consecutive failures — "
                f"injecting external_wait via validator"
            )
            try:
                csrf_t = _csrf(server_base, auth)
                warn_body = (
                    f"⛔ [System] {next_actor.upper()} の応答取得が "
                    f"{MAX_CONSECUTIVE_FAILURES}回連続失敗 (last: {str(e)[:120]}) "
                    f"— 自動relayを external_wait で停止しました。 "
                    f"Shuji 介入後、 worker再起動 or status=idle に手動更新で復帰。\n"
                    f"consensus_candidate: external_wait\n"
                    f"[Validator-Verify: R60-AUTOSTOP-N-FAILURES]"
                )
                _http(
                    server_base,
                    f"/api/rooms/{room_id}/inject_ai_message", "POST",
                    body={"actor": "validator", "body": warn_body},
                    csrf=csrf_t, auth=auth,
                )
                _consecutive_failures[room_id] = 0  # reset
            except Exception as e2:
                _log(f"⚠ external_wait inject失敗: {e2}")
        return {"error": str(e), "actor": next_actor}
    # 成功 → カウンタreset
    _consecutive_failures[room_id] = 0
    _record_turn_duration(next_actor, time.time() - _turn_t0)  # タブ安定運用

    _log(f"← {next_actor} {len(resp_text)} chars ({int(time.time() - _turn_t0)}s)")

    # stale-dup guard: 過去にinject済みの応答と同一 = 古い応答の再取得 → inject禁止
    if _is_stale_duplicate(next_actor, resp_text):
        _log(f"⛔ stale duplicate検出 [{next_actor}] — 過去応答と同一。再送1回")
        retry_prompt = (
            prompt
            + "\n\n⚠️ [Clerk] 直前に抽出された応答はあなたの過去の応答と同一でした"
            + " (画面の古い応答を再取得した可能性)。本プロンプトに改めて回答してください。"
        )
        try:
            resp_text = await chrome_relay.relay_turn(cdp_port, next_actor, retry_prompt)
        except Exception as e:
            _log(f"⚠ stale-dup再送失敗: {e}")
            _consecutive_failures[room_id] = _consecutive_failures.get(room_id, 0) + 1
            return {"error": "stale_duplicate_retry_failed", "actor": next_actor}
        if _is_stale_duplicate(next_actor, resp_text):
            _consecutive_failures[room_id] = _consecutive_failures.get(room_id, 0) + 1
            _log(f"⛔ stale duplicate継続 [{next_actor}] — injectせず再ポーリング")
            return {"error": "stale_duplicate", "actor": next_actor}

    # R67 routing_validation: 部屋トークン検証 — 別部屋応答の混入を遮断
    check = _validate_room_token(resp_text, room_id)
    if check != "ok":
        _log(f"⚠ R67 routing_validation={check} [room={room_id}] — 再送1回")
        retry_prompt = (
            prompt
            + f"\n\n⚠️ [Clerk] 直前の応答は部屋トークン検証に失敗しました ({check})。"
            + f"これは部屋『{room_id}』のターンです。本プロンプトの議題にのみ回答し、"
            + f"最終行に [Room: {room_id}] を必ず含めて回答し直してください。"
        )
        try:
            resp_text2 = await chrome_relay.relay_turn(cdp_port, next_actor, retry_prompt)
            if _validate_room_token(resp_text2, room_id) in ("ok",):
                resp_text = resp_text2
                check = "ok"
            elif not _validate_room_token(resp_text2, room_id).startswith("wrong"):
                # missing×2 → 別部屋トークンでは無いので注記付きで継続 (会議停止より継続優先)
                resp_text = resp_text2
                check = "missing"
        except Exception as e:
            _log(f"⚠ R67 再送失敗: {e}")
        if check.startswith("wrong"):
            # 別部屋トークン = 混入確定 → 絶対に inject しない
            _consecutive_failures[room_id] = _consecutive_failures.get(room_id, 0) + 1
            _log(f"⛔ R67 別部屋応答を遮断 ({check}) — inject せず再ポーリング")
            return {"error": f"routing_validation_failed:{check}", "actor": next_actor}
        if check == "missing":
            _log(f"⚠ R67 token欠落のまま採用 (wrongではないため継続優先) [room={room_id}]")

    # R63 inject堅牢化: 200確認 + 失敗時1回リトライ (応答消失防止 — 発言Claude R57報告由来)
    status, j = 0, {}
    for attempt in (1, 2):
        try:
            csrf = _csrf(server_base, auth)
            status, j = _http(
                server_base,
                f"/api/rooms/{room_id}/inject_ai_message", "POST",
                body={"actor": next_actor, "body": resp_text, "raw": resp_text},
                csrf=csrf, auth=auth,
            )
        except Exception as e:
            status, j = 0, {"detail": f"inject_exception: {e}"}
        if status == 200:
            break
        _log(f"⚠ inject_ai_message attempt {attempt}/2 status={status}: {str(j)[:200]}")
        if status == 409:  # turn guard: 論理的拒否 → リトライしない
            break
        if attempt == 1:
            await asyncio.sleep(2.0)
    if status != 200:
        return {"error": f"inject_failed:{status}", "detail": j}

    _remember_resp(next_actor, resp_text)  # stale-dup guard: inject成功分を記録
    _log(
        f"✓ turn complete room={room_id} actor={j.get('actor')} loop={j.get('loop')} "
        f"cons={j.get('consensus_candidate')} "
        f"next={j.get('next_actor')} "
        f"established={j.get('is_consensus_established')}"
    )
    return j


_worker_start_ts: dict[str, float] = {}


def _write_router_active(
    base: Path, room_id: str | None, queue: list[str] | None = None,
) -> None:
    """R65: worker処理中roomを書出し → rooms_overview が is_processing に変換。

    room_id=None は idle (処理中なし)。updated が30秒超過で stale扱い (server側判定)。
    UX改善 (2026-06-12): queue=FIFO待機room一覧 → PWA「待機#N」バッジの実データ。
    """
    try:
        p = base / "data" / "router_state.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps({
                "active_room": room_id,
                "queue": list(queue or []),
                "updated": time.time(),
            }),
            encoding="utf-8",
        )
    except Exception:
        pass


def _heartbeat(base: Path, room_id: str) -> None:
    """R58 Must Fix B: server.py が mtime < 5sで running と判定するためのtouch。

    R61 bug fix: start_ts (worker uptime算出用) を 持つ → Watchdog 猶予判定で使う。
    """
    try:
        import time as _time
        import os as _os
        if room_id not in _worker_start_ts:
            _worker_start_ts[room_id] = _time.time()
        hb_path = base / "data" / "projects" / room_id / "relay_heartbeat.json"
        hb_path.parent.mkdir(parents=True, exist_ok=True)
        hb_path.write_text(
            json.dumps({
                "ts": _time.time(),
                "pid": _os.getpid(),
                "start_ts": _worker_start_ts[room_id],
            }),
            encoding="utf-8",
        )
    except Exception:
        pass


async def run_room(
    room_id: str, base: Path, cdp_port: int | None,
    poll: float, server_base: str, auth: tuple[str, str] | None,
    max_loops: int = DEFAULT_MAX_LOOPS,
) -> None:
    _log(f"start room={room_id} base={base} cdp={cdp_port} poll={poll}s "
         f"server={server_base} max_loops={max_loops}")
    while True:
        try:
            _heartbeat(base, room_id)
            state = read_state(room_id, base)
            if state.get("is_consensus_established"):
                _write_router_active(base, None)  # R65: 収束中 = 処理中ではない
                _log("✅ consensus_established — pausing 30s")
                await asyncio.sleep(30)
                continue
            # R59 Q3: blocked / external_wait なら 自動pause (人間介入待ち)
            if state.get("status") in ("blocked", "external_wait"):
                _write_router_active(base, None)
                _log(f"⏸ status={state['status']} — pausing 60s, awaiting Shuji intervention")
                await asyncio.sleep(60)
                continue
            # R59 Q4: archived なら無限pause
            if state.get("archived"):
                _write_router_active(base, None)
                _log("📦 room archived — pausing 120s")
                await asyncio.sleep(120)
                continue
            # R58.2: max_loops 超過 → 強制停止 (runaway防止)
            cur_loops = state.get("total_loops", 0)
            if cur_loops >= max_loops:
                _write_router_active(base, None)
                _notify_max_loops(room_id, base, state, max_loops, server_base, auth)  # R66
                _log(f"⚠ max_loops {max_loops} reached (current={cur_loops}) — pausing 60s, awaiting Shuji")
                await asyncio.sleep(60)
                continue
            _write_router_active(base, room_id)  # R65: 処理中
            port = cdp_port or state.get("chrome_cdp_port") or 9222
            result = await _drive_one_turn(room_id, base, port, server_base, auth)
            if result.get("done"):
                _log(f"done: {result.get('reason')}")
                await asyncio.sleep(30)
            elif result.get("error"):
                await asyncio.sleep(max(poll, 5.0))
            elif result.get("skip"):
                # R61 fix #5: silent skip 撲滅 — 理由が変わった時だけ log
                reason = result.get("reason", "?")
                if getattr(run_room, "_last_skip", None) != reason:
                    _log(f"⏭ skip: {reason}")
                    run_room._last_skip = reason
                await asyncio.sleep(poll)
            else:
                run_room._last_skip = None
                await asyncio.sleep(poll)
        except KeyboardInterrupt:
            _log("interrupted")
            return
        except Exception as e:
            _log(f"⚠ loop error: {e}")
            await asyncio.sleep(max(poll, 5.0))


async def run_router(
    base: Path, cdp_port: int | None,
    poll: float, server_base: str, auth: tuple[str, str] | None,
    max_loops: int = DEFAULT_MAX_LOOPS,
) -> None:
    """R63: 自動roomルーター — FIFO最古優先で room へアタッチ、 収束まで切替禁止"""
    _log(f"start ROUTER mode (R63 auto room switching) base={base} cdp={cdp_port} "
         f"poll={poll}s server={server_base} max_loops={max_loops}")
    current: str | None = None
    last_served: str | None = None
    while True:
        try:
            if current is None:
                # R66: worker再起動の取りこぼし救済 — 到達済み未マークroomを通知
                for orphan in _find_orphan_max_loops(base, max_loops):
                    _notify_max_loops(
                        orphan, base, read_state(orphan, base), max_loops,
                        server_base, auth,
                    )
                pending = _scan_pending_rooms(base, max_loops)
                if not pending:
                    # idle: 直前に処理したroomへheartbeat (PWA lamp維持)
                    if last_served:
                        _heartbeat(base, last_served)
                    _write_router_active(base, None)  # R65: idle = 強調なし
                    await asyncio.sleep(poll)
                    continue
                current = pending[0][1]
                queue_view = [(r, ts.strftime("%H:%M:%S")) for ts, r in pending]
                _log(f"🔀 attach room={current} (FIFO oldest) queue={queue_view}")

            _heartbeat(base, current)
            # R65: 処理中room + FIFO待機列 書出し (待機バッジ用に毎iteration更新)
            waiting = [r for _, r in _scan_pending_rooms(base, max_loops)
                       if r != current]
            _write_router_active(base, current, waiting)
            state = read_state(current, base)
            reason = _converged_reason(state, max_loops)
            if reason:
                if reason.startswith("max_loops"):
                    # R66: 上限到達は通知付きで停止
                    _notify_max_loops(current, base, state, max_loops, server_base, auth)
                _log(f"🏁 room={current} converged ({reason}) — detach、 次のFIFO roomへ")
                last_served = current
                current = None
                _write_router_active(base, None)
                await asyncio.sleep(1.0)
                continue

            port = cdp_port or state.get("chrome_cdp_port") or 9222
            result = await _drive_one_turn(current, base, port, server_base, auth)
            if result.get("error"):
                await asyncio.sleep(max(poll, 5.0))
            elif result.get("skip"):
                reason_s = result.get("reason", "?")
                if getattr(run_router, "_last_skip", None) != reason_s:
                    _log(f"⏭ skip [{current}]: {reason_s}")
                    run_router._last_skip = reason_s
                await asyncio.sleep(poll)
            else:
                run_router._last_skip = None
                await asyncio.sleep(poll)
        except KeyboardInterrupt:
            _log("interrupted")
            return
        except Exception as e:
            _log(f"⚠ router loop error: {e}")
            await asyncio.sleep(max(poll, 5.0))


def main() -> int:
    p = argparse.ArgumentParser(description="relay_worker (R57 Phase C + R63 router)")
    p.add_argument("--room", default=None,
                   help="固定room (省略時: R63自動roomルーター FIFO最古優先)")
    p.add_argument("--cdp-port", type=int, default=None)
    p.add_argument("--base", default=str(DEFAULT_BASE))
    p.add_argument("--poll", type=float, default=DEFAULT_POLL_INTERVAL)
    p.add_argument("--server", default=DEFAULT_SERVER_BASE,
                   help="server.py base URL (default: https://100.70.20.113:8765)")
    p.add_argument("--max-loops", type=int, default=DEFAULT_MAX_LOOPS,
                   help=f"max loops before pause (default: {DEFAULT_MAX_LOOPS})")
    p.add_argument("--basic-user", default=None)
    p.add_argument("--basic-pass", default=None)
    args = p.parse_args()
    auth = ((args.basic_user, args.basic_pass)
            if args.basic_user and args.basic_pass else None)
    try:
        if args.room:
            asyncio.run(run_room(
                args.room, Path(args.base).resolve(), args.cdp_port,
                args.poll, args.server, auth, args.max_loops,
            ))
        else:
            asyncio.run(run_router(
                Path(args.base).resolve(), args.cdp_port,
                args.poll, args.server, auth, args.max_loops,
            ))
    except KeyboardInterrupt:
        return 0
    return 0


def self_test() -> bool:
    """構造のみ検証 (CDP接続なしでテスト)"""
    sample_state = {"total_loops": 1, "current_turn_in_loop": 1, "current_topic": "Test",
                    "room_id": "room_x"}
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

    # --- R67: routing_validation ---
    assert "部屋分離 (R67)" in prompt and "『room_x』" in prompt
    assert "[Room: room_x]" in prompt  # token指示行
    assert _validate_room_token("回答です\n[Room: room_x]", "room_x") == "ok"
    assert _validate_room_token("回答です (tokenなし)", "room_x") == "missing"
    assert _validate_room_token("回答\n[Room: btc_auto_trade]", "room_x") == "wrong:btc_auto_trade"
    # 複数tokenは最後を採用 (引用内の他部屋tokenに耐性)
    assert _validate_room_token("引用[Room: other]を含む\n[Room: room_x]", "room_x") == "ok"
    print("PASS: relay_worker self_test (R67 routing_validation)")

    # --- タブ安定運用: 会話リフレッシュ判定 ---
    _turns_since_reset.clear(); _slow_streak.clear()
    assert _needs_conversation_reset("claude") is None  # code session保護
    assert _needs_conversation_reset("gpt") is None
    for _ in range(CONV_RESET_TURNS):
        _record_turn_duration("gpt", 10.0)
    assert _needs_conversation_reset("gpt") is not None  # ターン数到達
    _turns_since_reset.clear(); _slow_streak.clear()
    _record_turn_duration("gemini", 130.0)
    assert _needs_conversation_reset("gemini") is None   # スロー1回ではまだ
    _record_turn_duration("gemini", 130.0)
    assert _needs_conversation_reset("gemini") is not None  # 連続2回で発火
    _record_turn_duration("gemini", 10.0)
    assert _slow_streak["gemini"] == 0  # 速い応答でstreakリセット
    _turns_since_reset.clear(); _slow_streak.clear()
    print("PASS: relay_worker self_test (タブ安定運用: 会話リフレッシュ判定)")

    # --- stale-dup guard ---
    assert not _is_stale_duplicate("gpt", "応答A")
    _remember_resp("gpt", "応答A")
    assert _is_stale_duplicate("gpt", "応答A")           # 同一 → stale
    assert _is_stale_duplicate("gpt", "  応答A  ")        # 空白差は同一視
    assert not _is_stale_duplicate("gpt", "応答B")        # 新規はOK
    assert not _is_stale_duplicate("gemini", "応答A")     # actor別管理
    for i in range(6):
        _remember_resp("gpt", f"resp{i}")
    assert not _is_stale_duplicate("gpt", "応答A")        # 5件超で古いhashは失効
    print("PASS: relay_worker self_test (stale-dup guard)")

    # --- R63: router unit tests ---
    # _parse_ts 両形式
    t1 = _parse_ts("2026-06-11 06:57:05 JST")
    t2 = _parse_ts("2026-06-11T07:02:03.985535+09:00")
    assert t1 and t2 and t2 > t1, f"_parse_ts: {t1} / {t2}"
    assert _parse_ts(None) is None
    assert _parse_ts("garbage") is None

    # _room_pending
    base_state = {"archived": False, "is_consensus_established": False,
                  "status": "idle", "total_loops": 1,
                  "last_shuji_input_ts": "2026-06-11T06:00:00+09:00"}
    assert _room_pending(dict(base_state), 5)
    assert not _room_pending({**base_state, "archived": True}, 5)
    assert not _room_pending({**base_state, "is_consensus_established": True}, 5)
    assert not _room_pending({**base_state, "status": "external_wait"}, 5)
    assert not _room_pending({**base_state, "status": "consensus_reached"}, 5)
    assert not _room_pending({**base_state, "total_loops": 5}, 5)
    assert not _room_pending({**base_state, "last_shuji_input_ts": None}, 5)
    print("PASS: relay_worker self_test (R63 _room_pending / _parse_ts)")

    # _scan_pending_rooms FIFO順 (temp baseに2 room作成、 古いsubmit部屋が先頭)
    import shutil
    import tempfile
    sys.path.insert(0, str(REPO_ROOT))
    from meeting_system import state_schema as _ss
    tmp = Path(tempfile.mkdtemp(prefix="r63_router_test_"))
    try:
        for rid, sub_ts in (("room_new", "2026-06-11T07:30:00+09:00"),
                            ("room_old", "2026-06-11T07:10:00+09:00")):
            st = _ss.default_state(rid)
            st["last_shuji_input_ts"] = sub_ts
            _ss.write_state_atomic(rid, st, tmp)
        tl = tmp / "data" / "timeline.jsonl"
        tl.parent.mkdir(parents=True, exist_ok=True)
        tl.write_text(
            json.dumps({"room_id": "room_old", "actor": "shuji",
                        "ts": "2026-06-11 07:10:00 JST"}) + "\n"
            + json.dumps({"room_id": "room_new", "actor": "shuji",
                          "ts": "2026-06-11 07:30:00 JST"}) + "\n",
            encoding="utf-8")
        pending = _scan_pending_rooms(tmp, 5)
        assert [r for _, r in pending] == ["room_old", "room_new"], \
            f"FIFO order wrong: {pending}"
        # 収束したroomは除外
        st_old = _ss.read_state("room_old", tmp)
        st_old["status"] = "consensus_reached"
        st_old["is_consensus_established"] = True
        _ss.write_state_atomic("room_old", st_old, tmp)
        pending2 = _scan_pending_rooms(tmp, 5)
        assert [r for _, r in pending2] == ["room_new"], f"converged除外失敗: {pending2}"
        # _converged_reason
        assert _converged_reason(st_old, 5) == "consensus_established"
        assert _converged_reason({"status": "external_wait"}, 5) == "status=external_wait"
        assert _converged_reason({"status": "idle", "total_loops": 5}, 5) == "max_loops=5"
        assert _converged_reason({"status": "idle", "total_loops": 1}, 5) is None
        print("PASS: relay_worker self_test (R63 FIFO scan + converged)")

        # --- R66: max_loops到達 → status書込 → resume相当で復帰 ---
        assert "max_loops_reached" in STOP_STATUSES
        st_new = _ss.read_state("room_new", tmp)
        st_new["total_loops"] = 5
        _ss.write_state_atomic("room_new", st_new, tmp)
        # 到達roomはpending除外 + 孤児検出に載る
        assert _scan_pending_rooms(tmp, 5) == []
        assert _find_orphan_max_loops(tmp, 5) == ["room_new"]
        # status書込 (1回目True / 2回目False = 冪等)
        assert _mark_max_loops_status("room_new", tmp) is True
        assert _ss.read_state("room_new", tmp)["status"] == "max_loops_reached"
        assert _mark_max_loops_status("room_new", tmp) is False
        assert _find_orphan_max_loops(tmp, 5) == []  # マーク済みは孤児ではない
        # resume_relay相当 (status=idle + loops=0) → pending復帰
        st_new = _ss.read_state("room_new", tmp)
        st_new["status"] = "idle"
        st_new["total_loops"] = 0
        _ss.write_state_atomic("room_new", st_new, tmp)
        assert [r for _, r in _scan_pending_rooms(tmp, 5)] == ["room_new"]
        print("PASS: relay_worker self_test (R66 max_loops 到達→mark→resume復帰)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return True


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        raise SystemExit(0 if self_test() else 1)
    raise SystemExit(main())
