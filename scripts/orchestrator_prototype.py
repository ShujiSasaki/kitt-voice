#!/usr/bin/env python3
"""
R50 Auto Meeting Orchestrator - Prototype

GPT指示: R50-CMD-CREATE-ORCHESTRATOR-PROTOTYPE (R50-AUTO-ORCHESTRATOR-PROTOTYPE-2251)
仕様書: logs/rounds/R50_AUTO_MEETING_ORCHESTRATOR_SPEC.md
由来: Shuji#27 → GPT第33 → Gemini第19 (案B+Playwright GREEN) → GPT第35 (Local Playwright Orchestrator採択)

Phase 1 雛形 (仕様確認用): Playwright実打鍵は placeholder のみ
"""
import json
import os
import re
import time
from enum import Enum
from pathlib import Path

# =====================
# State Machine (Spec Section 5)
# =====================
class State(str, Enum):
    IDLE = "IDLE"
    NEW_TOPIC = "NEW_TOPIC"
    SEND_TO_GPT = "SEND_TO_GPT"
    WAIT_GPT = "WAIT_GPT"
    LOG_GPT = "LOG_GPT"
    SEND_TO_GEMINI = "SEND_TO_GEMINI"
    WAIT_GEMINI = "WAIT_GEMINI"
    LOG_GEMINI = "LOG_GEMINI"
    SEND_TO_CLAUDE = "SEND_TO_CLAUDE"
    WAIT_CLAUDE = "WAIT_CLAUDE"
    LOG_CLAUDE = "LOG_CLAUDE"
    CHECK_CONSENSUS = "CHECK_CONSENSUS"
    NEXT_LOOP = "NEXT_LOOP"
    SHUJI_CONFIRM = "SHUJI_CONFIRM"
    ERROR = "ERROR"


# =====================
# Paths
# =====================
REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_JSON = REPO_ROOT / "logs" / "state.json"
QUEUE_JSON = REPO_ROOT / "logs" / "queue.json"
ROUND_LOG = REPO_ROOT / "logs" / "rounds" / "round_50_part2.md"
BELL_PROTOCOL = REPO_ROOT / "logs" / "rounds" / "R50_BELL_PROTOCOL.md"


# =====================
# State I/O (Spec Section 6: Single Lock Rule)
# =====================
def load_state() -> dict:
    with open(STATE_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state: dict) -> None:
    tmp = STATE_JSON.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_JSON)


def acquire_lock(state: dict) -> bool:
    if state.get("lock") is True:
        return False
    state["lock"] = True
    state["lock_acquired_epoch"] = int(time.time())
    save_state(state)
    return True


def release_lock(state: dict) -> None:
    state["lock"] = False
    state.pop("lock_acquired_epoch", None)
    save_state(state)


# =====================
# Actor Detection
# =====================
def detect_next_actor(state: dict) -> str | None:
    return state.get("next_actor")


def build_prompt_for_actor(actor: str, context: dict) -> str:
    return f"[Orchestrator] {actor} へのプロンプト placeholder (context={list(context.keys())})"


# =====================
# Playwright Placeholders (TODO: 実装)
# =====================
def send_message_placeholder(actor: str, prompt: str) -> dict:
    return {"status": "PLACEHOLDER_SEND_NOT_IMPLEMENTED", "actor": actor, "len": len(prompt)}


def fetch_response_placeholder(actor: str) -> dict:
    return {"status": "PLACEHOLDER_FETCH_NOT_IMPLEMENTED", "actor": actor, "verbatim": None}


# =====================
# Log Append
# =====================
def append_log_placeholder(section_title: str, verbatim: str) -> bool:
    with open(ROUND_LOG, "a", encoding="utf-8") as f:
        f.write(f"\n\n---\n\n## {section_title}\n\n{verbatim}\n")
    return True


# =====================
# Response Validation (Spec Section 8)
# =====================
VERIFY_TOKEN_RE = re.compile(r"\[(GPT|Gemini|Claude)-(Verify|Audit):\s*([^\]]+)\]")
NEXT_ACTOR_RE = re.compile(r"\[NextActor:\s*(GPT|Gemini|Claude|Shuji)\]")
ENDTIME_JST_RE = re.compile(r"\[EndTime-JST:\s*(\d{1,2}:\d{2}:\d{2})\]")


def validate_response(text: str) -> dict:
    verify = VERIFY_TOKEN_RE.search(text or "")
    next_actor = NEXT_ACTOR_RE.search(text or "")
    end_time = ENDTIME_JST_RE.search(text or "")
    missing = []
    if not verify:
        missing.append("VERIFY_TOKEN_MISSING")
    if not next_actor:
        missing.append("NEXTACTOR_MISSING")
    if not end_time:
        missing.append("ENDTIME_MISSING")
    return {
        "valid": not missing,
        "missing": missing,
        "verify_token": verify.group(0) if verify else None,
        "next_actor": next_actor.group(1) if next_actor else None,
        "end_time_jst": end_time.group(1) if end_time else None,
    }


# =====================
# Main Loop (Phase 1: GPT→Gemini→GPT)
# =====================
def main_loop_once() -> dict:
    state = load_state()
    if not acquire_lock(state):
        return {"status": "LOCK_HELD"}
    try:
        current_state = state.get("orchestrator_state", State.IDLE.value)
        next_actor = detect_next_actor(state)
        report = {
            "orchestrator_state": current_state,
            "next_actor": next_actor,
            "action": "PLACEHOLDER_NO_REAL_PLAYWRIGHT_YET",
        }
        return report
    finally:
        release_lock(load_state())


if __name__ == "__main__":
    print(json.dumps(main_loop_once(), ensure_ascii=False, indent=2))


# =====================
# TODO (GPT第35指定)
# =====================
# - PlaywrightでChatGPT/Gemini/Claudeタブ検出
# - editor selector確定 (ChatGPT: #prompt-textarea / Gemini: rich-textarea .ql-editor)
# - send button selector確定 (ChatGPT: button[data-testid="send-button"] / Gemini: button[aria-label="プロンプトを送信"])
# - userCount/respCount取得 (ChatGPT: [data-testid^="conversation-turn-"] / Gemini: user-query, model-response)
# - Verify Token / NextActor / EndTime-JST 抽出 (本ファイルの VERIFY_TOKEN_RE / NEXT_ACTOR_RE / ENDTIME_JST_RE で実装済み)
# - round log append連携 (本ファイルの append_log_placeholder で雛形あり、 PR形式に拡張)
# - dashboard連携 (logs/dashboard.html, Phase 1.5以降)
# - 実弾テスト (GPT→Gemini→GPT 2者循環、 Phase 1)
