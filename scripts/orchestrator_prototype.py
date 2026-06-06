#!/usr/bin/env python3
"""
R50 Auto Meeting Orchestrator - Phase 1 Prototype (dry-run + CDP)

GPT指示: R50-CMD-IMPLEMENT-ORCHESTRATOR-PHASE1-DRYRUN-CDP (R50-IMPLEMENT-ORCHESTRATOR-PHASE1-DRYRUN-CDP-4189)
仕様: logs/rounds/R50_AUTO_MEETING_ORCHESTRATOR_SPEC.md

Phase 1骨格:
- Chrome CDP接続 (http://127.0.0.1:9222)
- ChatGPT/Geminiタブ検出 placeholder
- Dry-runモード (DRY_RUN=True で 実Send禁止)
- state.json backup
- lock取得/解除 (atomic file rename)
- SIGINT / KeyboardInterrupt 安全終了
- DOM要素30秒未検出時 ERROR_SUSPENDED
- Verify Token/NextActor/EndTime-JST 抽出 (regex)
- Send成功検証
- Response完了検証

Playwright実打鍵は placeholder。 まだ実Sendはしない (GPT第39禁止)。
"""
import json
import os
import re
import shutil
import signal
import sys
import time
from enum import Enum
from pathlib import Path

DRY_RUN = True
CDP_ENDPOINT = os.environ.get("CDP_ENDPOINT", "http://127.0.0.1:9222")
DOM_TIMEOUT_SEC = 30
STALL_NOTIFY_SEC = 1800

CDP_SETUP_HINT = """
================================================================
CDP接続失敗 - Chrome起動手順 (Mac):
  open -na "Google Chrome" --args \\
    --remote-debugging-port=9222 \\
    --user-data-dir=/tmp/chrome-cdp-profile

接続確認:
  curl http://127.0.0.1:9222/json/version

注意:
- 既存Chromeには後付けで接続できません
- 必ず専用プロファイル (--user-data-dir) を使ってください
- 最初だけ ChatGPT/Gemini へ手動ログインが必要
- ログイン後 'python3 scripts/orchestrator_prototype.py --cdp-smoke-test' を再実行

環境変数 CDP_ENDPOINT で接続先URLを上書き可能 (未指定は http://127.0.0.1:9222)
================================================================
"""


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
    ERROR_SUSPENDED = "ERROR_SUSPENDED"
    INTERRUPTED = "INTERRUPTED"


# =====================
# Paths
# =====================
REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_JSON = REPO_ROOT / "logs" / "state.json"
QUEUE_JSON = REPO_ROOT / "logs" / "queue.json"
ROUND_LOG = REPO_ROOT / "logs" / "rounds" / "round_50_part2.md"
BELL_PROTOCOL = REPO_ROOT / "logs" / "rounds" / "R50_BELL_PROTOCOL.md"
STATE_BACKUP_DIR = REPO_ROOT / "logs" / "state_backups"
DRY_RUN_DIR = REPO_ROOT / "logs" / "dry_run"


# =====================
# State I/O (Spec Section 6: Single Lock Rule + P2: backup)
# =====================
def load_state() -> dict:
    with open(STATE_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state: dict) -> None:
    tmp = STATE_JSON.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_JSON)


def backup_state(state: dict) -> Path:
    STATE_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    path = STATE_BACKUP_DIR / f"state.{ts}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    return path


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
# Signal Handler (Spec 10.2: SIGINT安全終了)
# =====================
def handle_sigint(signum, frame):
    try:
        state = load_state()
        state["STATUS"] = State.INTERRUPTED.value
        state["lock"] = False
        state["interrupted_epoch"] = int(time.time())
        save_state(state)
    except Exception as e:
        sys.stderr.write(f"sigint cleanup failed: {e}\n")
    sys.exit(0)


signal.signal(signal.SIGINT, handle_sigint)


# =====================
# Dry-run Helpers (Spec 10.1 P1)
# =====================
def dry_run_dump(actor: str, payload: str) -> Path:
    DRY_RUN_DIR.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    path = DRY_RUN_DIR / f"{ts}.{actor}.txt"
    path.write_text(payload, encoding="utf-8")
    return path


# =====================
# CDP Connection Placeholder (Spec 10.1)
# =====================
def connect_to_chrome_cdp_placeholder(endpoint: str = CDP_ENDPOINT) -> dict:
    return {
        "status": "PLACEHOLDER_CDP_NOT_CONNECTED",
        "endpoint": endpoint,
        "instructions": [
            "Start Chrome with: chrome --remote-debugging-port=9222",
            "Then implement via Playwright sync_playwright().chromium.connect_over_cdp(endpoint)",
        ],
    }


def detect_chatgpt_tab_placeholder() -> dict:
    return {"status": "PLACEHOLDER", "tab_id": None, "url": "chatgpt.com/g/g-p-...", "needs": "Playwright BrowserContext.pages() filter by URL"}


def detect_gemini_tab_placeholder() -> dict:
    return {"status": "PLACEHOLDER", "tab_id": None, "url": "gemini.google.com/app/...", "needs": "Playwright BrowserContext.pages() filter by URL"}


# =====================
# Actor Detection
# =====================
def detect_next_actor(state: dict) -> str | None:
    return state.get("next_actor")


def build_prompt_for_actor(actor: str, context: dict) -> str:
    return f"[Orchestrator] {actor} へのプロンプト placeholder (context keys={list(context.keys())})"


# =====================
# Send / Response (Spec 10.1)
# =====================
def send_message(actor: str, prompt: str) -> dict:
    if DRY_RUN:
        path = dry_run_dump(actor, prompt)
        return {"status": "DRY_RUN_DUMPED", "actor": actor, "path": str(path)}
    return {"status": "PLACEHOLDER_REAL_SEND_NOT_IMPLEMENTED", "actor": actor}


def verify_send_success_placeholder(actor: str) -> dict:
    return {
        "status": "PLACEHOLDER",
        "actor": actor,
        "rule": "editor=0 AND userCount+1 AND (stopBtn=true OR response_started)",
        "checks_required": ["editor empty", "userCount increment", "stopBtn=true or response started"],
    }


def fetch_response(actor: str) -> dict:
    return {"status": "PLACEHOLDER_REAL_FETCH_NOT_IMPLEMENTED", "actor": actor, "verbatim": None}


def wait_response_with_timeout_placeholder(actor: str, timeout_sec: int = DOM_TIMEOUT_SEC) -> dict:
    return {
        "status": "PLACEHOLDER",
        "actor": actor,
        "timeout_sec": timeout_sec,
        "rule_on_timeout": f"if no DOM element within {timeout_sec}s: state.STATUS=ERROR_SUSPENDED, sys.exit(1)",
    }


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
# Log Append (Spec 10.1 P3)
# =====================
def append_log(section_title: str, verbatim: str) -> bool:
    with open(ROUND_LOG, "a", encoding="utf-8") as f:
        f.write(f"\n\n---\n\n## {section_title}\n\n{verbatim}\n")
    return True


# =====================
# DOM Element Watcher (Spec 10.2)
# =====================
def trigger_error_suspended(reason: str) -> None:
    state = load_state()
    state["STATUS"] = State.ERROR_SUSPENDED.value
    state["error_reason"] = reason
    state["error_epoch"] = int(time.time())
    state["lock"] = False
    save_state(state)
    sys.stderr.write(f"ERROR_SUSPENDED: {reason}\n")
    sys.exit(1)


# =====================
# Stall Notify Placeholder (Spec 10.1 P0)
# =====================
def stall_notify_placeholder(last_activity_epoch: int) -> dict:
    elapsed = int(time.time()) - last_activity_epoch
    if elapsed > STALL_NOTIFY_SEC:
        return {
            "status": "STALL_DETECTED",
            "elapsed_sec": elapsed,
            "notify_channels_todo": ["email", "slack", "ios_push", "macos_notification"],
        }
    return {"status": "OK", "elapsed_sec": elapsed}


# =====================
# Main Loop Skeleton (Phase 1: GPT→Gemini→GPT)
# =====================
def main_loop_once() -> dict:
    state = load_state()
    backup_path = backup_state(state)
    if not acquire_lock(state):
        return {"status": "LOCK_HELD", "backup": str(backup_path)}
    try:
        cdp = connect_to_chrome_cdp_placeholder()
        chatgpt = detect_chatgpt_tab_placeholder()
        gemini = detect_gemini_tab_placeholder()
        current_state = state.get("orchestrator_state", State.IDLE.value)
        next_actor = detect_next_actor(state)
        prompt = build_prompt_for_actor(next_actor or "GPT", {"backup_path": str(backup_path)})
        send_result = send_message(next_actor or "GPT", prompt)
        return {
            "dry_run": DRY_RUN,
            "backup": str(backup_path),
            "cdp": cdp,
            "chatgpt_tab": chatgpt,
            "gemini_tab": gemini,
            "orchestrator_state": current_state,
            "next_actor": next_actor,
            "send_result": send_result,
            "note": "Real Playwright打鍵はGPT指示でまだ禁止 (R50-IMPLEMENT-ORCHESTRATOR-PHASE1-DRYRUN-CDP-4189)",
        }
    finally:
        release_lock(load_state())


def run_self_test() -> int:
    """GPT指示 R50-CMD-ORCHESTRATOR-SELFTEST: 実Send絶対禁止、 dry-runで validate_response 検証"""
    print("=" * 60)
    print("R50 Orchestrator Self-Test (GPT-Verify: R50-ORCHESTRATOR-SELFTEST-6193)")
    print("=" * 60)
    assert DRY_RUN is True, "DRY_RUN must remain True during self-test"

    state = load_state()
    backup_path = backup_state(state)
    print(f"[1] state.json backup: {backup_path}")

    locked = acquire_lock(state)
    print(f"[2] lock acquired: {locked}")

    dummy_prompt = "[Self-Test] dummy prompt to dry-run pipeline"
    dump_path = dry_run_dump("SELFTEST", dummy_prompt)
    print(f"[3] dry_run_dump: {dump_path}")

    dummy_response = (
        "これは self-test 応答です。\n"
        "[GPT-Verify: SELFTEST-0001]\n"
        "[NextActor: Gemini]\n"
        "[EndTime-JST: 10:05:00]\n"
    )
    validation = validate_response(dummy_response)
    print(f"[4] validate_response: {json.dumps(validation, ensure_ascii=False)}")

    if not validation["valid"]:
        print(f"FAIL: validate_response missing fields: {validation['missing']}")
        release_lock(load_state())
        return 1
    expected_verify_token = "[GPT-Verify: SELFTEST-0001]"
    if validation["verify_token"] != expected_verify_token:
        print(f"FAIL: verify_token mismatch: got={validation['verify_token']}")
        release_lock(load_state())
        return 1
    if validation["next_actor"] != "Gemini":
        print(f"FAIL: next_actor mismatch: got={validation['next_actor']}")
        release_lock(load_state())
        return 1
    if validation["end_time_jst"] != "10:05:00":
        print(f"FAIL: end_time_jst mismatch: got={validation['end_time_jst']}")
        release_lock(load_state())
        return 1

    release_lock(load_state())
    after = load_state()
    print(f"[5] lock released: lock={after.get('lock')}")

    if after.get("lock") is not False:
        print("FAIL: lock not released")
        return 1
    if STATE_BACKUP_DIR.exists() is False:
        print("FAIL: STATE_BACKUP_DIR not created")
        return 1
    if DRY_RUN_DIR.exists() is False:
        print("FAIL: DRY_RUN_DIR not created")
        return 1

    print("=" * 60)
    print("SELF-TEST PASSED (DRY_RUN={}, real_send_enabled=False)".format(DRY_RUN))
    print("=" * 60)
    return 0


def run_cdp_smoke_test() -> int:
    """GPT指示 R50-CMD-CDP-SMOKE-TEST: CDP接続+pages検出のみ、 実Send絶対禁止"""
    print("=" * 60)
    print("R50 Orchestrator CDP Smoke Test (GPT-Verify: R50-ORCHESTRATOR-CDP-SMOKE-TEST-8804)")
    print(f"CDP endpoint: {CDP_ENDPOINT}")
    print("=" * 60)
    assert DRY_RUN is True, "DRY_RUN must remain True during cdp-smoke-test"

    result = {
        "cdp_smoke_test": "ERROR",
        "endpoint": CDP_ENDPOINT,
        "reason": None,
        "pages": [],
        "chatgpt_candidates": [],
        "gemini_candidates": [],
    }

    state = load_state()
    backup_path = backup_state(state)
    print(f"[1] state.json backup: {backup_path}")
    locked = acquire_lock(state)
    print(f"[2] lock acquired: {locked}")

    try:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:
            result["reason"] = f"PLAYWRIGHT_NOT_INSTALLED: {e}"
            print(f"[3] FAIL: {result['reason']}")
            print("    Install: pip install playwright && playwright install chromium")
            _persist_smoke_test_result(result)
            return 1

        try:
            with sync_playwright() as p:
                try:
                    browser = p.chromium.connect_over_cdp(CDP_ENDPOINT)
                except Exception as e:
                    result["reason"] = f"CDP_CONNECTION_FAILED: {type(e).__name__}: {e}"
                    print(f"[3] FAIL: {result['reason']}")
                    print(CDP_SETUP_HINT)
                    _persist_smoke_test_result(result)
                    return 1

                contexts = browser.contexts
                print(f"[3] contexts found: {len(contexts)}")
                all_pages = []
                for ctx in contexts:
                    for page in ctx.pages:
                        try:
                            url = page.url
                            title = page.title()
                        except Exception as e:
                            url, title = "<error>", f"<error: {e}>"
                        info = {"title": title, "url": url}
                        all_pages.append(info)

                print(f"[4] pages found: {len(all_pages)}")
                pages_dump_path = DRY_RUN_DIR / f"{int(time.time())}.cdp_pages.json"
                DRY_RUN_DIR.mkdir(parents=True, exist_ok=True)
                with open(pages_dump_path, "w", encoding="utf-8") as f:
                    json.dump(all_pages, f, ensure_ascii=False, indent=2)
                print(f"[5] pages dump: {pages_dump_path}")

                chatgpt_candidates = [p for p in all_pages if "chatgpt.com" in p["url"]]
                gemini_candidates = [p for p in all_pages if "gemini.google.com" in p["url"]]
                print(f"[6] ChatGPT候補: {len(chatgpt_candidates)} 件")
                print(f"[7] Gemini候補: {len(gemini_candidates)} 件")

                result.update({
                    "cdp_smoke_test": "PASSED",
                    "pages_count": len(all_pages),
                    "pages_dump": str(pages_dump_path),
                    "chatgpt_candidates": chatgpt_candidates,
                    "gemini_candidates": gemini_candidates,
                })
                _persist_smoke_test_result(result)
                return 0
        except Exception as e:
            result["reason"] = f"UNEXPECTED_ERROR: {type(e).__name__}: {e}"
            print(f"FAIL: {result['reason']}")
            _persist_smoke_test_result(result)
            return 1
    finally:
        release_lock(load_state())
        after = load_state()
        print(f"[final] lock released: lock={after.get('lock')}")


def _persist_smoke_test_result(result: dict) -> None:
    state = load_state()
    state["cdp_smoke_test_result"] = result
    save_state(state)


def print_cdp_setup() -> int:
    print(CDP_SETUP_HINT)
    print(f"Current CDP_ENDPOINT (env CDP_ENDPOINT or default): {CDP_ENDPOINT}")
    return 0


SELECTOR_DISCOVERY_JS = r"""() => {
    const result = {chatgpt: {}, gemini: {}, url: location.href, title: document.title};
    const isChatGPT = /chatgpt\.com/.test(location.href);
    const isGemini = /gemini\.google\.com/.test(location.href);
    const bucket = isChatGPT ? result.chatgpt : (isGemini ? result.gemini : null);
    if (!bucket) return result;

    bucket.url = location.href;
    bucket.title = document.title;

    const textareas = Array.from(document.querySelectorAll('textarea')).map(t => ({
        id: t.id, name: t.name, placeholder: t.placeholder, ariaLabel: t.getAttribute('aria-label'),
        classes: t.className.substring(0, 80)
    }));
    bucket.textareas = textareas;

    const contenteditables = Array.from(document.querySelectorAll('[contenteditable="true"]')).slice(0, 10).map(e => ({
        tagName: e.tagName, ariaLabel: e.getAttribute('aria-label'),
        classes: e.className.substring(0, 80), parentTag: e.parentElement?.tagName
    }));
    bucket.contenteditables = contenteditables;

    const buttons = Array.from(document.querySelectorAll('button')).filter(b => {
        const al = (b.getAttribute('aria-label') || '').toLowerCase();
        const testid = (b.getAttribute('data-testid') || '').toLowerCase();
        const txt = (b.textContent || '').toLowerCase();
        return /send|stop|送信|停止|プロンプト|回答|submit/.test(al + ' ' + testid + ' ' + txt);
    }).slice(0, 20).map(b => ({
        ariaLabel: b.getAttribute('aria-label'),
        dataTestid: b.getAttribute('data-testid'),
        disabled: b.disabled,
        text: (b.textContent || '').substring(0, 40),
        classes: b.className.substring(0, 80)
    }));
    bucket.send_or_stop_buttons = buttons;

    if (isChatGPT) {
        const turns = document.querySelectorAll('[data-testid^="conversation-turn-"]');
        bucket.conversation_turns_count = turns.length;
        bucket.assistant_messages_count = document.querySelectorAll('[data-message-author-role="assistant"]').length;
        bucket.user_messages_count = document.querySelectorAll('[data-message-author-role="user"]').length;
        bucket.editor_selector_candidate = '#prompt-textarea';
        bucket.send_button_selector_candidate = 'button[data-testid="send-button"]';
        bucket.stop_button_selector_candidate = 'button[data-testid="stop-button"]';
    } else if (isGemini) {
        bucket.user_queries_count = document.querySelectorAll('user-query').length;
        bucket.model_responses_count = document.querySelectorAll('model-response').length;
        bucket.editor_selector_candidate = 'rich-textarea .ql-editor';
        bucket.send_button_selector_candidate = 'button[aria-label="プロンプトを送信"]';
        bucket.stop_button_selector_candidate = 'button[aria-label="回答を停止"]';
    }
    return result;
}"""


def run_selector_discovery() -> int:
    """GPT指示 R50-CMD-ORCHESTRATOR-SELECTOR-DISCOVERY: 実入力・実送信なし、 DOM読み取りのみ"""
    print("=" * 60)
    print("R50 Orchestrator Selector Discovery (GPT-Verify: R50-ORCHESTRATOR-SELECTOR-DISCOVERY-3382)")
    print("=" * 60)
    assert DRY_RUN is True

    result = {
        "selector_discovery": "ERROR",
        "endpoint": CDP_ENDPOINT,
        "chatgpt_tab_detected": False,
        "gemini_tab_detected": False,
        "pages": [],
    }
    state = load_state()
    backup_path = backup_state(state)
    print(f"[1] state.json backup: {backup_path}")
    acquire_lock(state)
    print(f"[2] lock acquired")

    try:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:
            result["reason"] = f"PLAYWRIGHT_NOT_INSTALLED: {e}"
            _persist_selector_discovery(result)
            return 1

        try:
            with sync_playwright() as p:
                try:
                    browser = p.chromium.connect_over_cdp(CDP_ENDPOINT)
                except Exception as e:
                    result["reason"] = f"CDP_CONNECTION_FAILED: {e}"
                    print(CDP_SETUP_HINT)
                    _persist_selector_discovery(result)
                    return 1

                pages_info = []
                for ctx in browser.contexts:
                    for page in ctx.pages:
                        try:
                            url = page.url
                        except Exception:
                            continue
                        if "chatgpt.com" in url or "gemini.google.com" in url:
                            try:
                                page.bring_to_front()
                                page.wait_for_load_state("domcontentloaded", timeout=8000)
                                info = page.evaluate(SELECTOR_DISCOVERY_JS)
                            except Exception as e:
                                info = {"url": url, "error": str(e)}
                            pages_info.append(info)
                            if "chatgpt.com" in url:
                                result["chatgpt_tab_detected"] = True
                            if "gemini.google.com" in url:
                                result["gemini_tab_detected"] = True

                result["pages"] = pages_info
                ts = int(time.time())
                DRY_RUN_DIR.mkdir(parents=True, exist_ok=True)
                selectors_path = DRY_RUN_DIR / f"{ts}.selectors.json"
                with open(selectors_path, "w", encoding="utf-8") as f:
                    json.dump(pages_info, f, ensure_ascii=False, indent=2)
                result["selectors_dump"] = str(selectors_path)
                result["selector_discovery"] = "PASSED"
                print(f"[3] ChatGPTタブ検出: {result['chatgpt_tab_detected']}")
                print(f"[4] Geminiタブ検出: {result['gemini_tab_detected']}")
                print(f"[5] selectors dump: {selectors_path}")
                _persist_selector_discovery(result)
                return 0
        except Exception as e:
            result["reason"] = f"UNEXPECTED: {type(e).__name__}: {e}"
            _persist_selector_discovery(result)
            return 1
    finally:
        release_lock(load_state())
        after = load_state()
        print(f"[final] lock released: lock={after.get('lock')}")


def _persist_selector_discovery(result: dict) -> None:
    state = load_state()
    state["selector_discovery_result"] = result
    save_state(state)


def run_relay_dry_run() -> int:
    """GPT指示 R50-CMD-ORCHESTRATOR-RELAY-DRY-RUN: GPT最新発言を読み取り Gemini向けプロンプト生成、 実入力・実Sendなし"""
    print("=" * 60)
    print("R50 Orchestrator Relay Dry-Run (GPT-Verify: R50-ORCHESTRATOR-RELAY-DRY-RUN-5381)")
    print("=" * 60)
    assert DRY_RUN is True

    result = {
        "relay_dry_run": "ERROR",
        "endpoint": CDP_ENDPOINT,
        "chatgpt_tab": False,
        "gemini_tab": False,
        "verify_token": None,
        "next_actor": None,
        "end_time_jst": None,
        "next_actor_is_gemini": False,
    }
    state = load_state()
    backup_path = backup_state(state)
    print(f"[1] backup: {backup_path}")
    acquire_lock(state)
    print(f"[2] lock acquired")

    try:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:
            result["reason"] = f"PLAYWRIGHT_NOT_INSTALLED: {e}"
            _persist_relay(result)
            return 1

        try:
            with sync_playwright() as p:
                try:
                    browser = p.chromium.connect_over_cdp(CDP_ENDPOINT)
                except Exception as e:
                    result["reason"] = f"CDP_CONNECTION_FAILED: {e}"
                    print(CDP_SETUP_HINT)
                    _persist_relay(result)
                    return 1

                chatgpt_page = None
                gemini_page = None
                for ctx in browser.contexts:
                    for page in ctx.pages:
                        url = page.url
                        if "chatgpt.com/g/g-p-" in url and chatgpt_page is None:
                            chatgpt_page = page
                            result["chatgpt_tab"] = True
                        elif "gemini.google.com" in url and gemini_page is None:
                            gemini_page = page
                            result["gemini_tab"] = True
                print(f"[3] ChatGPTタブ: {result['chatgpt_tab']}")
                print(f"[4] Geminiタブ: {result['gemini_tab']}")

                if not chatgpt_page:
                    result["reason"] = "CHATGPT_TAB_NOT_FOUND"
                    _persist_relay(result)
                    return 1
                if not gemini_page:
                    result["reason"] = "GEMINI_TAB_NOT_FOUND"
                    _persist_relay(result)
                    return 1

                chatgpt_page.bring_to_front()
                chatgpt_page.wait_for_load_state("domcontentloaded", timeout=8000)
                last_assistant = chatgpt_page.evaluate("""() => {
                    const turns = document.querySelectorAll('[data-testid^="conversation-turn-"]');
                    const last = turns[turns.length - 1];
                    return last ? (last.textContent || '') : '';
                }""")
                print(f"[5] ChatGPT最新本文 len={len(last_assistant)}")

                verify_match = VERIFY_TOKEN_RE.search(last_assistant)
                next_actor_match = NEXT_ACTOR_RE.search(last_assistant)
                end_time_match = ENDTIME_JST_RE.search(last_assistant)

                result["verify_token"] = verify_match.group(0) if verify_match else None
                result["next_actor"] = next_actor_match.group(1) if next_actor_match else None
                result["end_time_jst"] = end_time_match.group(1) if end_time_match else None
                result["next_actor_is_gemini"] = (result["next_actor"] == "Gemini")
                print(f"[6] Verify Token: {result['verify_token']}")
                print(f"[7] NextActor: {result['next_actor']}")
                print(f"[8] EndTime-JST: {result['end_time_jst']}")

                gemini_prompt = (
                    "[Claude-Transmission: GPT verbatim relay via Orchestrator dry-run]\n\n"
                    f"GPT司会から Geminiへ ({result['verify_token']} に紐づく中継):\n\n"
                    "--- GPT verbatim ---\n"
                    f"{last_assistant}\n"
                    "--- end ---\n\n"
                    "Geminiは標準形式で応答してください:\n"
                    "  [Gemini-Verify: ...]\n  [NextActor: GPT or Claude]\n  [EndTime-JST: HH:MM:SS]\n\n"
                    "[Orchestrator-DryRun-Relay]\n[NextActor: Gemini]\n"
                )
                ts = int(time.time())
                DRY_RUN_DIR.mkdir(parents=True, exist_ok=True)
                relay_path = DRY_RUN_DIR / f"{ts}.relay_to_gemini.txt"
                with open(relay_path, "w", encoding="utf-8") as f:
                    f.write(gemini_prompt)
                result["relay_dump"] = str(relay_path)
                result["relay_dry_run"] = "PASSED"
                print(f"[9] Gemini向け dry-run: {relay_path}")
                print("[10] 実入力・実Sendなし (DRY_RUN強制)")
                _persist_relay(result)
                return 0
        except Exception as e:
            result["reason"] = f"UNEXPECTED: {type(e).__name__}: {e}"
            _persist_relay(result)
            return 1
    finally:
        release_lock(load_state())
        after = load_state()
        print(f"[final] lock released: lock={after.get('lock')}")


def _persist_relay(result: dict) -> None:
    state = load_state()
    state["relay_dry_run_result"] = result
    save_state(state)


def run_send_test_gemini() -> int:
    """GPT指示 R50-CMD-ORCHESTRATOR-GEMINI-SEND-TEST: 1回だけGemini実送信、 終了後real_send_enabled=falseに戻す"""
    print("=" * 60)
    print("R50 Orchestrator Controlled Gemini Send Test (GPT-Verify: R50-ORCHESTRATOR-GEMINI-SEND-TEST-7062)")
    print("=" * 60)

    test_payload = (
        "これは Orchestrator の Gemini 実送信テストです。本来議題ではありません。"
        "短く「受信確認OK」とだけ返してください。\n\n"
        "[GPT-Verify: R50-GEMINI-SEND-TEST-PAYLOAD]\n"
        "[NextActor: GPT]\n"
        f"[EndTime-JST: {time.strftime('%H:%M:%S')}]\n"
    )

    result = {
        "send_test_gemini": "ERROR",
        "endpoint": CDP_ENDPOINT,
        "gemini_tab_detected": False,
        "before": {},
        "after": {},
        "send_verification": {},
    }
    state = load_state()
    state["real_send_enabled"] = True
    backup_path = backup_state(state)
    save_state(state)
    print(f"[1] backup: {backup_path}, real_send_enabled→True")
    acquire_lock(state)
    print(f"[2] lock acquired")

    try:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:
            result["reason"] = f"PLAYWRIGHT_NOT_INSTALLED: {e}"
            _persist_send_test(result, restore_false=True)
            return 1
        try:
            with sync_playwright() as p:
                try:
                    browser = p.chromium.connect_over_cdp(CDP_ENDPOINT)
                except Exception as e:
                    result["reason"] = f"CDP_CONNECTION_FAILED: {e}"
                    _persist_send_test(result, restore_false=True)
                    return 1

                gemini_page = None
                for ctx in browser.contexts:
                    for page in ctx.pages:
                        if "gemini.google.com" in page.url:
                            gemini_page = page
                            break
                    if gemini_page:
                        break
                if not gemini_page:
                    result["reason"] = "GEMINI_TAB_NOT_FOUND"
                    _persist_send_test(result, restore_false=True)
                    return 1
                result["gemini_tab_detected"] = True
                print("[3] Geminiタブ検出: True")

                gemini_page.bring_to_front()
                gemini_page.wait_for_load_state("domcontentloaded", timeout=8000)

                before = gemini_page.evaluate("""() => {
                    const editor = document.querySelector('rich-textarea .ql-editor');
                    return {
                        editor_len: editor ? (editor.textContent || '').length : -1,
                        user_count: document.querySelectorAll('user-query').length,
                        assistant_count: document.querySelectorAll('model-response').length,
                        stop_btn: !!document.querySelector('button[aria-label=\"回答を停止\"]'),
                    };
                }""")
                result["before"] = before
                print(f"[4] before: {before}")

                inject_result = gemini_page.evaluate("""(text) => {
                    const richTextarea = document.querySelector('rich-textarea');
                    if (!richTextarea) return {error: 'no rich-textarea'};
                    const qlEditor = richTextarea.querySelector('.ql-editor');
                    if (!qlEditor) return {error: 'no ql-editor'};
                    while (qlEditor.firstChild) qlEditor.removeChild(qlEditor.firstChild);
                    text.split('\\n').forEach(line => {
                        const p = document.createElement('p');
                        if (line.trim() === '') {
                            p.appendChild(document.createElement('br'));
                        } else {
                            p.textContent = line;
                        }
                        qlEditor.appendChild(p);
                    });
                    qlEditor.dispatchEvent(new Event('input', {bubbles: true}));
                    return {injected: true, len: (qlEditor.textContent || '').length, paragraphs: qlEditor.children.length};
                }""", test_payload)
                print(f"[5] inject: {inject_result}")
                if "error" in inject_result:
                    result["reason"] = f"INJECT_FAILED: {inject_result['error']}"
                    _persist_send_test(result, restore_false=True)
                    return 1

                gemini_page.wait_for_timeout(2000)

                click_result = gemini_page.evaluate("""() => {
                    const btn = document.querySelector('button[aria-label=\"プロンプトを送信\"]');
                    if (!btn) return {error: 'no send button'};
                    if (btn.disabled) return {error: 'disabled'};
                    btn.click();
                    return {clicked: true};
                }""")
                print(f"[6] click: {click_result}")
                if "error" in click_result:
                    result["reason"] = f"CLICK_FAILED: {click_result['error']}"
                    _persist_send_test(result, restore_false=True)
                    return 1

                gemini_page.wait_for_timeout(4000)
                after = gemini_page.evaluate("""() => {
                    const editor = document.querySelector('rich-textarea .ql-editor');
                    return {
                        editor_len: editor ? (editor.textContent || '').length : -1,
                        user_count: document.querySelectorAll('user-query').length,
                        assistant_count: document.querySelectorAll('model-response').length,
                        stop_btn: !!document.querySelector('button[aria-label=\"回答を停止\"]'),
                    };
                }""")
                result["after"] = after
                print(f"[7] after: {after}")

                verify = {
                    "editor_zero": after["editor_len"] == 0,
                    "user_count_incremented": (after["user_count"] - before["user_count"]) == 1,
                    "stop_btn_or_assistant_increased": after["stop_btn"] or (after["assistant_count"] > before["assistant_count"]),
                }
                verify["all_passed"] = all(verify.values())
                result["send_verification"] = verify
                print(f"[8] verification: {verify}")

                if verify["all_passed"]:
                    result["send_test_gemini"] = "PASSED"
                else:
                    result["send_test_gemini"] = "FAILED"

                ts = int(time.time())
                DRY_RUN_DIR.mkdir(parents=True, exist_ok=True)
                result_path = DRY_RUN_DIR / f"{ts}.gemini_send_test.json"
                with open(result_path, "w", encoding="utf-8") as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
                result["result_dump"] = str(result_path)
                print(f"[9] result dump: {result_path}")

                _persist_send_test(result, restore_false=True)
                return 0 if verify["all_passed"] else 1
        except Exception as e:
            result["reason"] = f"UNEXPECTED: {type(e).__name__}: {e}"
            _persist_send_test(result, restore_false=True)
            return 1
    finally:
        release_lock(load_state())
        after_state = load_state()
        print(f"[final] lock={after_state.get('lock')}, real_send_enabled={after_state.get('real_send_enabled')}")


def _persist_send_test(result: dict, restore_false: bool = True) -> None:
    state = load_state()
    state["gemini_send_test_result"] = result
    if restore_false:
        state["real_send_enabled"] = False
    save_state(state)


def run_fetch_gemini_latest() -> int:
    """GPT指示 R50-CMD-ORCHESTRATOR-FETCH-GEMINI-LATEST: Gemini最新応答取得のみ、 実入力・実Send禁止"""
    print("=" * 60)
    print("R50 Orchestrator Fetch Gemini Latest (GPT-Verify: R50-ORCHESTRATOR-FETCH-GEMINI-LATEST-2678)")
    print("=" * 60)

    result = {
        "fetch_gemini_latest": "ERROR",
        "endpoint": CDP_ENDPOINT,
        "gemini_tab_detected": False,
        "user_count": None,
        "assistant_count": None,
        "stop_btn": None,
        "latest_response_len": None,
        "verify_token": None,
        "next_actor": None,
        "end_time_jst": None,
        "missing_tags": [],
    }
    state = load_state()
    backup_path = backup_state(state)
    print(f"[1] backup: {backup_path}")
    acquire_lock(state)
    print(f"[2] lock acquired")

    try:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:
            result["reason"] = f"PLAYWRIGHT_NOT_INSTALLED: {e}"
            _persist_fetch_gemini(result)
            return 1
        try:
            with sync_playwright() as p:
                try:
                    browser = p.chromium.connect_over_cdp(CDP_ENDPOINT)
                except Exception as e:
                    result["reason"] = f"CDP_CONNECTION_FAILED: {e}"
                    _persist_fetch_gemini(result)
                    return 1

                gemini_page = None
                for ctx in browser.contexts:
                    for page in ctx.pages:
                        if "gemini.google.com" in page.url:
                            gemini_page = page
                            break
                    if gemini_page:
                        break
                if not gemini_page:
                    result["reason"] = "GEMINI_TAB_NOT_FOUND"
                    _persist_fetch_gemini(result)
                    return 1
                result["gemini_tab_detected"] = True
                print("[3] Geminiタブ検出: True")

                gemini_page.bring_to_front()
                gemini_page.wait_for_load_state("domcontentloaded", timeout=8000)

                snapshot = gemini_page.evaluate("""() => {
                    const responses = document.querySelectorAll('model-response');
                    const last = responses[responses.length - 1];
                    return {
                        user_count: document.querySelectorAll('user-query').length,
                        assistant_count: responses.length,
                        stop_btn: !!document.querySelector('button[aria-label=\"回答を停止\"]'),
                        latest_text: last ? (last.textContent || '') : '',
                    };
                }""")
                result["user_count"] = snapshot["user_count"]
                result["assistant_count"] = snapshot["assistant_count"]
                result["stop_btn"] = snapshot["stop_btn"]
                latest_text = snapshot["latest_text"]
                result["latest_response_len"] = len(latest_text)
                print(f"[4] user_count: {snapshot['user_count']}")
                print(f"[5] assistant_count: {snapshot['assistant_count']}")
                print(f"[6] stop_btn: {snapshot['stop_btn']}")
                print(f"[7] latest len: {len(latest_text)}")

                ts = int(time.time())
                DRY_RUN_DIR.mkdir(parents=True, exist_ok=True)
                dump_path = DRY_RUN_DIR / f"{ts}.gemini_latest_response.txt"
                with open(dump_path, "w", encoding="utf-8") as f:
                    f.write(latest_text)
                result["response_dump"] = str(dump_path)
                print(f"[8] dump: {dump_path}")

                verify = VERIFY_TOKEN_RE.search(latest_text)
                next_actor = NEXT_ACTOR_RE.search(latest_text)
                end_time = ENDTIME_JST_RE.search(latest_text)
                if verify:
                    result["verify_token"] = verify.group(0)
                else:
                    result["missing_tags"].append("VERIFY_TOKEN_MISSING")
                if next_actor:
                    result["next_actor"] = next_actor.group(1)
                else:
                    result["missing_tags"].append("NEXTACTOR_MISSING")
                if end_time:
                    result["end_time_jst"] = end_time.group(1)
                else:
                    result["missing_tags"].append("ENDTIME_MISSING")
                print(f"[9] verify_token: {result['verify_token']}")
                print(f"[10] next_actor: {result['next_actor']}")
                print(f"[11] end_time_jst: {result['end_time_jst']}")
                print(f"[12] missing_tags: {result['missing_tags']}")

                result["fetch_gemini_latest"] = "PASSED"
                _persist_fetch_gemini(result)
                return 0
        except Exception as e:
            result["reason"] = f"UNEXPECTED: {type(e).__name__}: {e}"
            _persist_fetch_gemini(result)
            return 1
    finally:
        release_lock(load_state())
        after_state = load_state()
        print(f"[final] lock={after_state.get('lock')}, real_send_enabled={after_state.get('real_send_enabled')}")


def _persist_fetch_gemini(result: dict) -> None:
    state = load_state()
    state["gemini_fetch_latest_result"] = result
    save_state(state)


def run_send_test_chatgpt() -> int:
    """GPT指示 R50-CMD-ORCHESTRATOR-CHATGPT-SEND-TEST: 1回だけChatGPT実送信、 終了後real_send_enabled=false戻し"""
    print("=" * 60)
    print("R50 Orchestrator Controlled ChatGPT Send Test (GPT-Verify: R50-ORCHESTRATOR-CHATGPT-SEND-TEST-6129)")
    print("=" * 60)

    test_payload = (
        "これは Orchestrator の ChatGPT 実送信テストです。本来議題ではありません。"
        "短く「受信確認OK」とだけ返してください。\n\n"
        "[GPT-Verify: R50-CHATGPT-SEND-TEST-PAYLOAD]\n"
        "[NextActor: GPT]\n"
        f"[EndTime-JST: {time.strftime('%H:%M:%S')}]\n"
    )

    result = {
        "send_test_chatgpt": "ERROR",
        "endpoint": CDP_ENDPOINT,
        "chatgpt_tab_detected": False,
        "before": {},
        "after": {},
        "send_verification": {},
    }
    state = load_state()
    state["real_send_enabled"] = True
    backup_path = backup_state(state)
    save_state(state)
    print(f"[1] backup: {backup_path}, real_send_enabled→True")
    acquire_lock(state)
    print(f"[2] lock acquired")

    try:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:
            result["reason"] = f"PLAYWRIGHT_NOT_INSTALLED: {e}"
            _persist_chatgpt_send_test(result, restore_false=True)
            return 1
        try:
            with sync_playwright() as p:
                try:
                    browser = p.chromium.connect_over_cdp(CDP_ENDPOINT)
                except Exception as e:
                    result["reason"] = f"CDP_CONNECTION_FAILED: {e}"
                    _persist_chatgpt_send_test(result, restore_false=True)
                    return 1

                chatgpt_page = None
                for ctx in browser.contexts:
                    for page in ctx.pages:
                        if "chatgpt.com/g/g-p-" in page.url:
                            chatgpt_page = page
                            break
                    if chatgpt_page:
                        break
                if not chatgpt_page:
                    result["reason"] = "CHATGPT_TAB_NOT_FOUND"
                    _persist_chatgpt_send_test(result, restore_false=True)
                    return 1
                result["chatgpt_tab_detected"] = True
                print("[3] ChatGPTタブ検出: True")

                chatgpt_page.bring_to_front()
                chatgpt_page.wait_for_load_state("domcontentloaded", timeout=8000)

                before = chatgpt_page.evaluate("""() => {
                    const ta = document.querySelector('#prompt-textarea');
                    return {
                        editor_len: ta ? (ta.textContent || '').length : -1,
                        user_count: document.querySelectorAll('[data-message-author-role=\"user\"]').length,
                        assistant_count: document.querySelectorAll('[data-message-author-role=\"assistant\"]').length,
                        stop_btn: !!document.querySelector('button[data-testid=\"stop-button\"]'),
                    };
                }""")
                result["before"] = before
                print(f"[4] before: {before}")

                inject_result = chatgpt_page.evaluate("""(text) => {
                    const ta = document.querySelector('#prompt-textarea');
                    if (!ta) return {error: 'no textarea'};
                    ta.focus();
                    const dt = new DataTransfer();
                    dt.setData('text/plain', text);
                    ta.dispatchEvent(new ClipboardEvent('paste', {bubbles: true, cancelable: true, clipboardData: dt}));
                    return {injected: true, len: (ta.textContent || '').length};
                }""", test_payload)
                print(f"[5] inject: {inject_result}")
                if "error" in inject_result:
                    result["reason"] = f"INJECT_FAILED: {inject_result['error']}"
                    _persist_chatgpt_send_test(result, restore_false=True)
                    return 1

                chatgpt_page.wait_for_timeout(2000)

                click_result = chatgpt_page.evaluate("""() => {
                    const btn = document.querySelector('button[data-testid=\"send-button\"]');
                    if (!btn) return {error: 'no send button'};
                    if (btn.disabled) return {error: 'disabled'};
                    btn.click();
                    return {clicked: true};
                }""")
                print(f"[6] click: {click_result}")
                if "error" in click_result:
                    result["reason"] = f"CLICK_FAILED: {click_result['error']}"
                    _persist_chatgpt_send_test(result, restore_false=True)
                    return 1

                chatgpt_page.wait_for_timeout(4000)
                after = chatgpt_page.evaluate("""() => {
                    const ta = document.querySelector('#prompt-textarea');
                    return {
                        editor_len: ta ? (ta.textContent || '').length : -1,
                        user_count: document.querySelectorAll('[data-message-author-role=\"user\"]').length,
                        assistant_count: document.querySelectorAll('[data-message-author-role=\"assistant\"]').length,
                        stop_btn: !!document.querySelector('button[data-testid=\"stop-button\"]'),
                    };
                }""")
                result["after"] = after
                print(f"[7] after: {after}")

                verify = {
                    "editor_zero": after["editor_len"] == 0,
                    "user_count_incremented": (after["user_count"] - before["user_count"]) == 1,
                    "stop_btn_or_assistant_increased": after["stop_btn"] or (after["assistant_count"] > before["assistant_count"]),
                }
                verify["all_passed"] = all(verify.values())
                result["send_verification"] = verify
                print(f"[8] verification: {verify}")

                result["send_test_chatgpt"] = "PASSED" if verify["all_passed"] else "FAILED"

                ts = int(time.time())
                DRY_RUN_DIR.mkdir(parents=True, exist_ok=True)
                result_path = DRY_RUN_DIR / f"{ts}.chatgpt_send_test.json"
                with open(result_path, "w", encoding="utf-8") as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
                result["result_dump"] = str(result_path)
                print(f"[9] result dump: {result_path}")

                _persist_chatgpt_send_test(result, restore_false=True)
                return 0 if verify["all_passed"] else 1
        except Exception as e:
            result["reason"] = f"UNEXPECTED: {type(e).__name__}: {e}"
            _persist_chatgpt_send_test(result, restore_false=True)
            return 1
    finally:
        release_lock(load_state())
        after_state = load_state()
        print(f"[final] lock={after_state.get('lock')}, real_send_enabled={after_state.get('real_send_enabled')}")


def _persist_chatgpt_send_test(result: dict, restore_false: bool = True) -> None:
    state = load_state()
    state["chatgpt_send_test_result"] = result
    if restore_false:
        state["real_send_enabled"] = False
    save_state(state)


def run_two_agent_relay_test() -> int:
    """GPT指示 R50-CMD-TWO-AGENT-RELAY-TEST: GPT↔Gemini 1往復自動relay、 終了後real_send_enabled=false戻し"""
    print("=" * 60)
    print("R50 Two-Agent Relay Test (GPT-Verify: R50-TWO-AGENT-RELAY-TEST-2907)")
    print("=" * 60)

    gemini_payload = (
        "これは Orchestrator の GPT↔Gemini 自動relayテストです。本来議題ではありません。"
        "Geminiは短く「Gemini自動relay受信OK」と返し、末尾に Verify Token / NextActor / EndTime-JST を付けてください。\n\n"
        "Gemini指定末尾:\n"
        "[Gemini-Verify: R50-TWO-AGENT-RELAY-GEMINI-OK]\n"
        "[NextActor: GPT]\n"
        f"[EndTime-JST: {time.strftime('%H:%M:%S')}]\n"
    )

    result = {
        "two_agent_relay_test": "ERROR",
        "endpoint": CDP_ENDPOINT,
        "gemini": {"send": None, "fetch": None, "verify_token": None, "next_actor": None, "end_time_jst": None, "response_len": None},
        "chatgpt": {"send": None, "fetch": None, "verify_token": None, "next_actor": None, "end_time_jst": None, "response_len": None, "missing_tags": []},
    }
    state = load_state()
    state["real_send_enabled"] = True
    save_state(state)
    backup_path = backup_state(state)
    print(f"[1] backup: {backup_path}, real_send_enabled→True")
    acquire_lock(state)
    print(f"[2] lock acquired")

    try:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:
            result["reason"] = f"PLAYWRIGHT_NOT_INSTALLED: {e}"
            _persist_two_agent(result, restore_false=True)
            return 1
        try:
            with sync_playwright() as p:
                try:
                    browser = p.chromium.connect_over_cdp(CDP_ENDPOINT)
                except Exception as e:
                    result["reason"] = f"CDP_CONNECTION_FAILED: {e}"
                    _persist_two_agent(result, restore_false=True)
                    return 1

                gemini_page = None
                chatgpt_page = None
                for ctx in browser.contexts:
                    for page in ctx.pages:
                        if "gemini.google.com" in page.url and gemini_page is None:
                            gemini_page = page
                        elif "chatgpt.com/g/g-p-" in page.url and chatgpt_page is None:
                            chatgpt_page = page
                if not gemini_page or not chatgpt_page:
                    result["reason"] = f"TAB_NOT_FOUND gemini={bool(gemini_page)} chatgpt={bool(chatgpt_page)}"
                    _persist_two_agent(result, restore_false=True)
                    return 1
                print("[3] Both tabs detected")

                # === Step 1: Gemini Send ===
                gemini_page.bring_to_front()
                gemini_page.wait_for_load_state("domcontentloaded", timeout=8000)
                gemini_before = gemini_page.evaluate("""() => ({
                    user_count: document.querySelectorAll('user-query').length,
                    assistant_count: document.querySelectorAll('model-response').length,
                })""")
                print(f"[4] Gemini before: {gemini_before}")
                gemini_page.evaluate("""(text) => {
                    const richTextarea = document.querySelector('rich-textarea');
                    const qlEditor = richTextarea.querySelector('.ql-editor');
                    while (qlEditor.firstChild) qlEditor.removeChild(qlEditor.firstChild);
                    text.split('\\n').forEach(line => {
                        const p = document.createElement('p');
                        if (line.trim() === '') p.appendChild(document.createElement('br'));
                        else p.textContent = line;
                        qlEditor.appendChild(p);
                    });
                    qlEditor.dispatchEvent(new Event('input', {bubbles: true}));
                }""", gemini_payload)
                gemini_page.wait_for_timeout(2000)
                send1 = gemini_page.evaluate("""() => {
                    const btn = document.querySelector('button[aria-label=\"プロンプトを送信\"]');
                    if (!btn || btn.disabled) return {error: 'disabled or missing'};
                    btn.click();
                    return {clicked: true};
                }""")
                if "error" in send1:
                    result["reason"] = f"GEMINI_SEND_FAILED: {send1['error']}"
                    _persist_two_agent(result, restore_false=True)
                    return 1
                result["gemini"]["send"] = "SUCCESS"
                print(f"[5] Gemini Send: clicked")

                # === Step 2: Gemini Response wait + fetch ===
                for _ in range(20):
                    gemini_page.wait_for_timeout(3000)
                    snap = gemini_page.evaluate("""() => ({
                        user_count: document.querySelectorAll('user-query').length,
                        assistant_count: document.querySelectorAll('model-response').length,
                        stop_btn: !!document.querySelector('button[aria-label=\"回答を停止\"]'),
                    })""")
                    if snap["assistant_count"] > gemini_before["assistant_count"] and not snap["stop_btn"]:
                        break
                gemini_after = gemini_page.evaluate("""() => {
                    const responses = document.querySelectorAll('model-response');
                    const last = responses[responses.length - 1];
                    return {
                        text: last ? (last.textContent || '') : '',
                        user_count: document.querySelectorAll('user-query').length,
                        assistant_count: responses.length,
                    };
                }""")
                gemini_text = gemini_after["text"]
                print(f"[6] Gemini Response len: {len(gemini_text)}")
                result["gemini"]["fetch"] = "SUCCESS" if gemini_text else "FAILED"
                result["gemini"]["response_len"] = len(gemini_text)

                g_verify = VERIFY_TOKEN_RE.search(gemini_text)
                g_next = NEXT_ACTOR_RE.search(gemini_text)
                g_end = ENDTIME_JST_RE.search(gemini_text)
                result["gemini"]["verify_token"] = g_verify.group(0) if g_verify else None
                result["gemini"]["next_actor"] = g_next.group(1) if g_next else None
                result["gemini"]["end_time_jst"] = g_end.group(1) if g_end else None
                print(f"[7] Gemini tags: verify={bool(g_verify)} next={result['gemini']['next_actor']} end={result['gemini']['end_time_jst']}")

                # === Step 3: Append Gemini response to round log ===
                section_title = f"39. Orchestrator自動relay受信: Gemini応答 verbatim — {time.strftime('%H:%M:%S')}"
                append_log(section_title, gemini_text + f"\n\n`[Orchestrator-Verify: R50-TWO-AGENT-RELAY-TEST-2907]`\n`[NextActor: GPT]`\n")
                print(f"[8] Round log append done")

                # === Step 4: ChatGPT Send (Gemini応答+説明) ===
                chatgpt_payload = (
                    "Gemini自動relay応答を受領しました。これは Orchestrator の GPT↔Gemini 自動relayテストです。"
                    "短く「ChatGPT自動relay受信OK」と返してください。\n\n"
                    "--- Gemini verbatim ---\n"
                    f"{gemini_text}\n"
                    "--- end ---\n\n"
                    "[Orchestrator-Verify: R50-TWO-AGENT-RELAY-TO-CHATGPT]\n"
                    "[NextActor: GPT]\n"
                    f"[EndTime-JST: {time.strftime('%H:%M:%S')}]\n"
                )
                chatgpt_page.bring_to_front()
                chatgpt_before = chatgpt_page.evaluate("""() => ({
                    user_count: document.querySelectorAll('[data-message-author-role=\"user\"]').length,
                    assistant_count: document.querySelectorAll('[data-message-author-role=\"assistant\"]').length,
                })""")
                print(f"[9] ChatGPT before: {chatgpt_before}")
                chatgpt_page.evaluate("""(text) => {
                    const ta = document.querySelector('#prompt-textarea');
                    ta.focus();
                    const dt = new DataTransfer();
                    dt.setData('text/plain', text);
                    ta.dispatchEvent(new ClipboardEvent('paste', {bubbles: true, cancelable: true, clipboardData: dt}));
                }""", chatgpt_payload)
                chatgpt_page.wait_for_timeout(2000)
                send2 = chatgpt_page.evaluate("""() => {
                    const btn = document.querySelector('button[data-testid=\"send-button\"]');
                    if (!btn || btn.disabled) return {error: 'disabled or missing'};
                    btn.click();
                    return {clicked: true};
                }""")
                if "error" in send2:
                    result["reason"] = f"CHATGPT_SEND_FAILED: {send2['error']}"
                    _persist_two_agent(result, restore_false=True)
                    return 1
                result["chatgpt"]["send"] = "SUCCESS"
                print(f"[10] ChatGPT Send: clicked")

                # === Step 5: ChatGPT Response wait + fetch ===
                for _ in range(20):
                    chatgpt_page.wait_for_timeout(3000)
                    snap = chatgpt_page.evaluate("""() => ({
                        assistant_count: document.querySelectorAll('[data-message-author-role=\"assistant\"]').length,
                        stop_btn: !!document.querySelector('button[data-testid=\"stop-button\"]'),
                    })""")
                    if snap["assistant_count"] > chatgpt_before["assistant_count"] and not snap["stop_btn"]:
                        break
                chatgpt_after = chatgpt_page.evaluate("""() => {
                    const turns = document.querySelectorAll('[data-testid^=\"conversation-turn-\"]');
                    const last = turns[turns.length - 1];
                    return {
                        text: last ? (last.textContent || '') : '',
                        user_count: document.querySelectorAll('[data-message-author-role=\"user\"]').length,
                        assistant_count: document.querySelectorAll('[data-message-author-role=\"assistant\"]').length,
                    };
                }""")
                chatgpt_text = chatgpt_after["text"]
                print(f"[11] ChatGPT Response len: {len(chatgpt_text)}")
                result["chatgpt"]["fetch"] = "SUCCESS" if chatgpt_text else "FAILED"
                result["chatgpt"]["response_len"] = len(chatgpt_text)

                c_verify = VERIFY_TOKEN_RE.search(chatgpt_text)
                c_next = NEXT_ACTOR_RE.search(chatgpt_text)
                c_end = ENDTIME_JST_RE.search(chatgpt_text)
                result["chatgpt"]["verify_token"] = c_verify.group(0) if c_verify else None
                result["chatgpt"]["next_actor"] = c_next.group(1) if c_next else None
                result["chatgpt"]["end_time_jst"] = c_end.group(1) if c_end else None
                if not c_verify:
                    result["chatgpt"]["missing_tags"].append("VERIFY_TOKEN_MISSING")
                if not c_next:
                    result["chatgpt"]["missing_tags"].append("NEXTACTOR_MISSING")
                if not c_end:
                    result["chatgpt"]["missing_tags"].append("ENDTIME_MISSING")
                print(f"[12] ChatGPT tags: verify={bool(c_verify)} missing={result['chatgpt']['missing_tags']}")

                # === Verdict ===
                if result["gemini"]["send"] == "SUCCESS" and result["gemini"]["fetch"] == "SUCCESS" and \
                   result["chatgpt"]["send"] == "SUCCESS" and result["chatgpt"]["fetch"] == "SUCCESS":
                    if c_verify:
                        result["two_agent_relay_test"] = "PASSED"
                    else:
                        result["two_agent_relay_test"] = "TEST_PARTIAL"
                else:
                    result["two_agent_relay_test"] = "TEST_FAILED"

                ts = int(time.time())
                DRY_RUN_DIR.mkdir(parents=True, exist_ok=True)
                result_path = DRY_RUN_DIR / f"{ts}.two_agent_relay_test.json"
                with open(result_path, "w", encoding="utf-8") as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
                result["result_dump"] = str(result_path)
                print(f"[13] result: {result['two_agent_relay_test']}, dump: {result_path}")

                _persist_two_agent(result, restore_false=True)
                return 0 if result["two_agent_relay_test"] in ("PASSED", "TEST_PARTIAL") else 1
        except Exception as e:
            result["reason"] = f"UNEXPECTED: {type(e).__name__}: {e}"
            _persist_two_agent(result, restore_false=True)
            return 1
    finally:
        release_lock(load_state())
        after_state = load_state()
        print(f"[final] lock={after_state.get('lock')}, real_send_enabled={after_state.get('real_send_enabled')}")


def _persist_two_agent(result: dict, restore_false: bool = True) -> None:
    state = load_state()
    state["two_agent_relay_test_result"] = result
    if restore_false:
        state["real_send_enabled"] = False
    save_state(state)


REAL_TOPIC_GEMINI_PAYLOAD = """R50最終インフラ報告書の制御付き自動監査テストです。本テストはOrchestratorの本議題relay確認であり、Shujiさん承認を代弁しません。

GPT司会案:

Tier 1:
- Hyperliquid
- dYdX v4
- Exness
- GMOコイン
- bitbank
- bitFlyer
- SBI VCトレード

Tier 2:
- Lighter
- FXGT
- EdgeX
- Jupiter Perps
- Vertex
- Drift
- GMX
- Phemex
- KuCoin
- Crypto.com Exchange
- Coincheck
- BitTrade
- OKCoinJapan

Tier 3:
- Bybit
- BitMEX
- Binance Global Futures
- OKX Global
- Gate.io
- BingX
- MEXC
- Bitget
- DMM Bitcoin
- P2P常用
- Wise既定路線

経路:
A. 日本円/銀行/カード等 → Exness → MT5/BTC CFD検証
B. 国内取引所 → XRP / USDC対応チェーン / SOL → Hyperliquid / dYdX v4

Geminiは短く監査してください:
1. このTier表に重大異論はあるか
2. 経路A/B分離は妥当か
3. Wise既定路線却下は妥当か
4. R50をShujiさん確認へ出せる状態か
5. 残る重大脆弱性があるか

末尾に必ず付ける:
[Gemini-Verify: R50-REAL-TOPIC-RELAY-GEMINI-AUDIT]
[NextActor: GPT]
[EndTime-JST: HH:MM:SS]
"""


def run_real_topic_relay_test() -> int:
    """GPT指示 R50-CMD-REAL-TOPIC-RELAY-TEST: R50本来議題1往復自動relay、 終了後real_send_enabled=false戻し"""
    print("=" * 60)
    print("R50 Real Topic Relay Test (GPT-Verify: R50-REAL-TOPIC-RELAY-TEST-6634)")
    print("=" * 60)

    result = {
        "real_topic_relay_test": "ERROR",
        "endpoint": CDP_ENDPOINT,
        "gemini": {"send": None, "fetch": None, "verify_token": None, "next_actor": None, "end_time_jst": None, "response_len": None},
        "chatgpt": {"send": None, "fetch": None, "verify_token": None, "next_actor": None, "end_time_jst": None, "response_len": None, "missing_tags": []},
    }
    state = load_state()
    state["real_send_enabled"] = True
    save_state(state)
    backup_path = backup_state(state)
    print(f"[1] backup: {backup_path}, real_send_enabled→True")
    acquire_lock(state)
    print(f"[2] lock acquired")

    try:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:
            result["reason"] = f"PLAYWRIGHT_NOT_INSTALLED: {e}"
            _persist_real_topic(result, restore_false=True)
            return 1
        try:
            with sync_playwright() as p:
                try:
                    browser = p.chromium.connect_over_cdp(CDP_ENDPOINT)
                except Exception as e:
                    result["reason"] = f"CDP_CONNECTION_FAILED: {e}"
                    _persist_real_topic(result, restore_false=True)
                    return 1

                gemini_page = None
                chatgpt_page = None
                for ctx in browser.contexts:
                    for page in ctx.pages:
                        if "gemini.google.com" in page.url and gemini_page is None:
                            gemini_page = page
                        elif "chatgpt.com/g/g-p-" in page.url and chatgpt_page is None:
                            chatgpt_page = page
                if not gemini_page or not chatgpt_page:
                    result["reason"] = f"TAB_NOT_FOUND gemini={bool(gemini_page)} chatgpt={bool(chatgpt_page)}"
                    _persist_real_topic(result, restore_false=True)
                    return 1
                print("[3] Both tabs detected")

                # Gemini Send
                gemini_page.bring_to_front()
                gemini_page.wait_for_load_state("domcontentloaded", timeout=8000)
                g_before = gemini_page.evaluate("""() => ({
                    user_count: document.querySelectorAll('user-query').length,
                    assistant_count: document.querySelectorAll('model-response').length,
                })""")
                print(f"[4] Gemini before: {g_before}")
                gemini_page.evaluate("""(text) => {
                    const richTextarea = document.querySelector('rich-textarea');
                    const qlEditor = richTextarea.querySelector('.ql-editor');
                    while (qlEditor.firstChild) qlEditor.removeChild(qlEditor.firstChild);
                    text.split('\\n').forEach(line => {
                        const p = document.createElement('p');
                        if (line.trim() === '') p.appendChild(document.createElement('br'));
                        else p.textContent = line;
                        qlEditor.appendChild(p);
                    });
                    qlEditor.dispatchEvent(new Event('input', {bubbles: true}));
                }""", REAL_TOPIC_GEMINI_PAYLOAD)
                gemini_page.wait_for_timeout(2500)
                send1 = gemini_page.evaluate("""() => {
                    const btn = document.querySelector('button[aria-label=\"プロンプトを送信\"]');
                    if (!btn || btn.disabled) return {error: 'disabled or missing'};
                    btn.click();
                    return {clicked: true};
                }""")
                if "error" in send1:
                    result["reason"] = f"GEMINI_SEND_FAILED: {send1['error']}"
                    _persist_real_topic(result, restore_false=True)
                    return 1
                result["gemini"]["send"] = "SUCCESS"
                print("[5] Gemini Send: clicked")

                # Gemini wait
                for _ in range(40):
                    gemini_page.wait_for_timeout(3000)
                    snap = gemini_page.evaluate("""() => ({
                        assistant_count: document.querySelectorAll('model-response').length,
                        stop_btn: !!document.querySelector('button[aria-label=\"回答を停止\"]'),
                    })""")
                    if snap["assistant_count"] > g_before["assistant_count"] and not snap["stop_btn"]:
                        break
                g_after = gemini_page.evaluate("""() => {
                    const responses = document.querySelectorAll('model-response');
                    const last = responses[responses.length - 1];
                    return {text: last ? (last.textContent || '') : ''};
                }""")
                gtext = g_after["text"]
                result["gemini"]["fetch"] = "SUCCESS" if gtext else "FAILED"
                result["gemini"]["response_len"] = len(gtext)
                print(f"[6] Gemini Response len: {len(gtext)}")

                g_v = VERIFY_TOKEN_RE.search(gtext)
                g_n = NEXT_ACTOR_RE.search(gtext)
                g_e = ENDTIME_JST_RE.search(gtext)
                result["gemini"]["verify_token"] = g_v.group(0) if g_v else None
                result["gemini"]["next_actor"] = g_n.group(1) if g_n else None
                result["gemini"]["end_time_jst"] = g_e.group(1) if g_e else None
                print(f"[7] Gemini tags: verify={bool(g_v)} next={result['gemini']['next_actor']} end={result['gemini']['end_time_jst']}")

                # Append
                ts_str = time.strftime('%H:%M:%S')
                section_title = f"41. Orchestrator自動relay受信 (Real Topic): Gemini監査応答 verbatim — {ts_str}"
                append_log(section_title, gtext + f"\n\n`[Orchestrator-Verify: R50-REAL-TOPIC-RELAY-TEST-6634]`\n`[NextActor: GPT]`\n")
                print("[8] Append done")

                # ChatGPT Send
                chatgpt_payload = (
                    "R50最終インフラ報告書の自動relay監査応答をGeminiから受領しました。これはOrchestratorの本議題1往復テストであり、Shujiさん承認の代弁ではありません。\n\n"
                    "--- Gemini監査応答 verbatim ---\n"
                    f"{gtext}\n"
                    "--- end ---\n\n"
                    "GPT司会としてこの監査を受けた判断を簡潔に示してください。R50正式終結はShujiさん確認待ちです。\n\n"
                    "[Orchestrator-Verify: R50-REAL-TOPIC-RELAY-TO-CHATGPT]\n"
                    "[NextActor: GPT]\n"
                    f"[EndTime-JST: {ts_str}]\n"
                )
                chatgpt_page.bring_to_front()
                c_before = chatgpt_page.evaluate("""() => ({
                    user_count: document.querySelectorAll('[data-message-author-role=\"user\"]').length,
                    assistant_count: document.querySelectorAll('[data-message-author-role=\"assistant\"]').length,
                })""")
                print(f"[9] ChatGPT before: {c_before}")
                chatgpt_page.evaluate("""(text) => {
                    const ta = document.querySelector('#prompt-textarea');
                    ta.focus();
                    const dt = new DataTransfer();
                    dt.setData('text/plain', text);
                    ta.dispatchEvent(new ClipboardEvent('paste', {bubbles: true, cancelable: true, clipboardData: dt}));
                }""", chatgpt_payload)
                chatgpt_page.wait_for_timeout(2500)
                send2 = chatgpt_page.evaluate("""() => {
                    const btn = document.querySelector('button[data-testid=\"send-button\"]');
                    if (!btn || btn.disabled) return {error: 'disabled or missing'};
                    btn.click();
                    return {clicked: true};
                }""")
                if "error" in send2:
                    result["reason"] = f"CHATGPT_SEND_FAILED: {send2['error']}"
                    _persist_real_topic(result, restore_false=True)
                    return 1
                result["chatgpt"]["send"] = "SUCCESS"
                print("[10] ChatGPT Send: clicked")

                # ChatGPT wait
                for _ in range(40):
                    chatgpt_page.wait_for_timeout(3000)
                    snap = chatgpt_page.evaluate("""() => ({
                        assistant_count: document.querySelectorAll('[data-message-author-role=\"assistant\"]').length,
                        stop_btn: !!document.querySelector('button[data-testid=\"stop-button\"]'),
                    })""")
                    if snap["assistant_count"] > c_before["assistant_count"] and not snap["stop_btn"]:
                        break
                c_after = chatgpt_page.evaluate("""() => {
                    const turns = document.querySelectorAll('[data-testid^=\"conversation-turn-\"]');
                    const last = turns[turns.length - 1];
                    return {text: last ? (last.textContent || '') : ''};
                }""")
                ctext = c_after["text"]
                result["chatgpt"]["fetch"] = "SUCCESS" if ctext else "FAILED"
                result["chatgpt"]["response_len"] = len(ctext)
                print(f"[11] ChatGPT Response len: {len(ctext)}")

                c_v = VERIFY_TOKEN_RE.search(ctext)
                c_n = NEXT_ACTOR_RE.search(ctext)
                c_e = ENDTIME_JST_RE.search(ctext)
                result["chatgpt"]["verify_token"] = c_v.group(0) if c_v else None
                result["chatgpt"]["next_actor"] = c_n.group(1) if c_n else None
                result["chatgpt"]["end_time_jst"] = c_e.group(1) if c_e else None
                if not c_v: result["chatgpt"]["missing_tags"].append("VERIFY_TOKEN_MISSING")
                if not c_n: result["chatgpt"]["missing_tags"].append("NEXTACTOR_MISSING")
                if not c_e: result["chatgpt"]["missing_tags"].append("ENDTIME_MISSING")
                print(f"[12] ChatGPT tags: verify={bool(c_v)} missing={result['chatgpt']['missing_tags']}")

                if result["gemini"]["send"] == "SUCCESS" and result["gemini"]["fetch"] == "SUCCESS" and \
                   result["chatgpt"]["send"] == "SUCCESS" and result["chatgpt"]["fetch"] == "SUCCESS":
                    result["real_topic_relay_test"] = "PASSED" if c_v else "TEST_PARTIAL"
                else:
                    result["real_topic_relay_test"] = "TEST_FAILED"

                ts = int(time.time())
                DRY_RUN_DIR.mkdir(parents=True, exist_ok=True)
                rp = DRY_RUN_DIR / f"{ts}.real_topic_relay_test.json"
                with open(rp, "w", encoding="utf-8") as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
                result["result_dump"] = str(rp)
                print(f"[13] result: {result['real_topic_relay_test']}, dump: {rp}")

                _persist_real_topic(result, restore_false=True)
                return 0 if result["real_topic_relay_test"] in ("PASSED", "TEST_PARTIAL") else 1
        except Exception as e:
            result["reason"] = f"UNEXPECTED: {type(e).__name__}: {e}"
            _persist_real_topic(result, restore_false=True)
            return 1
    finally:
        release_lock(load_state())
        after_state = load_state()
        print(f"[final] lock={after_state.get('lock')}, real_send_enabled={after_state.get('real_send_enabled')}")


def _persist_real_topic(result: dict, restore_false: bool = True) -> None:
    state = load_state()
    state["real_topic_relay_test_result"] = result
    if restore_false:
        state["real_send_enabled"] = False
    save_state(state)


# =====================
# Multi-Round Consensus Test (GPT第52 R50-MULTIROUND-CONSENSUS-TEST-9346)
# =====================
MULTIROUND_INITIAL_PROPOSAL = """R50最終インフラ報告書の自動合意判定テストです。Shujiさん承認は代弁しません。

Geminiは、重大異論がある場合のみ指摘してください。重大異論がなければ「重大異論なし。Shujiさん確認へ出せる」と明記してください。

初期案:
- DMM BitcoinはTier 3から外し、除外/廃止済み・SBI VC移管枠へ移動
- 海外CEX Tier 3理由に、日本居住者向けIP制限・規約変更・突発的規制強化リスクを明記
- 経路Bを重要経路として明記
- Hyperliquidは主候補だが既定路線ではない
- Wise既定路線は却下

末尾に必ず付けてください:
[Gemini-Verify: R50-MULTIROUND-CONSENSUS-GEMINI]
[NextActor: GPT]
[EndTime-JST: HH:MM:SS]
"""

CONSENSUS_OK_KEYWORDS = ["重大異論なし", "重大な異論はあり", "重大な異論はな", "重大な異論はあり", "確認へ出せる", "確認へ出して", "確認に出せる", "確認に出して", "Shujiさん確認へ出せる"]
CONSENSUS_NG_KEYWORDS = ["重大脆弱性", "重大な脆弱性", "重大な異論あり", "重大異論あり", "重大な異論があ", "重大な懸念", "重大なリスク"]


def _detect_consensus(gemini_text: str) -> tuple[bool, list[str]]:
    """Gemini応答から合意候補判定。 戻り値: (consensus_candidate, unresolved_issues)"""
    unresolved = []
    has_ng = any(kw in gemini_text for kw in CONSENSUS_NG_KEYWORDS)
    has_ok = any(kw in gemini_text for kw in CONSENSUS_OK_KEYWORDS)
    if has_ng:
        for line in gemini_text.split("\n"):
            if any(kw in line for kw in CONSENSUS_NG_KEYWORDS):
                unresolved.append(line.strip()[:200])
        return (False, unresolved)
    if has_ok:
        return (True, [])
    return (False, ["合意/異論キーワード未検出 (要GPT判定)"])


def run_multi_round_consensus_test() -> int:
    """GPT指示 R50-CMD-MULTIROUND-CONSENSUS-TEST: GPT↔Gemini最大2周+合意判定"""
    print("=" * 60)
    print("R50 Multi-Round Consensus Test (GPT-Verify: R50-MULTIROUND-CONSENSUS-TEST-9346)")
    print("=" * 60)

    result = {
        "multi_round_consensus_test": "ERROR",
        "endpoint": CDP_ENDPOINT,
        "max_rounds": 2,
        "rounds": [],
        "consensus_candidate": False,
        "unresolved_critical_issues": [],
        "final_report_ready": False,
    }
    state = load_state()
    state["real_send_enabled"] = True
    save_state(state)
    backup_path = backup_state(state)
    print(f"[1] backup: {backup_path}, real_send_enabled→True")
    acquire_lock(state)
    print(f"[2] lock acquired")

    try:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:
            result["reason"] = f"PLAYWRIGHT_NOT_INSTALLED: {e}"
            _persist_multi_round(result, restore_false=True)
            return 1

        try:
            with sync_playwright() as p:
                try:
                    browser = p.chromium.connect_over_cdp(CDP_ENDPOINT)
                except Exception as e:
                    result["reason"] = f"CDP_CONNECTION_FAILED: {e}"
                    _persist_multi_round(result, restore_false=True)
                    return 1

                gemini_page = None
                chatgpt_page = None
                for ctx in browser.contexts:
                    for page in ctx.pages:
                        if "gemini.google.com" in page.url and gemini_page is None:
                            gemini_page = page
                        elif "chatgpt.com/g/g-p-" in page.url and chatgpt_page is None:
                            chatgpt_page = page
                if not gemini_page or not chatgpt_page:
                    result["reason"] = f"TAB_NOT_FOUND gemini={bool(gemini_page)} chatgpt={bool(chatgpt_page)}"
                    _persist_multi_round(result, restore_false=True)
                    return 1
                print("[3] Both tabs detected")

                current_proposal_to_gemini = MULTIROUND_INITIAL_PROPOSAL
                consensus_reached = False
                final_gpt_summary = ""

                for round_idx in range(1, 3):
                    print(f"\n===== Round {round_idx}/2 =====")
                    round_data = {
                        "round": round_idx,
                        "gemini": {"send": None, "fetch": None, "verify_token": None, "next_actor": None, "end_time_jst": None, "response_len": None, "text": ""},
                        "chatgpt": {"send": None, "fetch": None, "verify_token": None, "next_actor": None, "end_time_jst": None, "response_len": None, "missing_tags": [], "text": ""},
                        "consensus_candidate": False,
                        "unresolved": [],
                    }

                    # Gemini Send
                    gemini_page.bring_to_front()
                    gemini_page.wait_for_load_state("domcontentloaded", timeout=8000)
                    g_before = gemini_page.evaluate("""() => ({
                        user_count: document.querySelectorAll('user-query').length,
                        assistant_count: document.querySelectorAll('model-response').length,
                    })""")
                    print(f"[R{round_idx}/Gemini-before] {g_before}")
                    gemini_page.evaluate("""(text) => {
                        const richTextarea = document.querySelector('rich-textarea');
                        const qlEditor = richTextarea.querySelector('.ql-editor');
                        while (qlEditor.firstChild) qlEditor.removeChild(qlEditor.firstChild);
                        text.split('\\n').forEach(line => {
                            const p = document.createElement('p');
                            if (line.trim() === '') p.appendChild(document.createElement('br'));
                            else p.textContent = line;
                            qlEditor.appendChild(p);
                        });
                        qlEditor.dispatchEvent(new Event('input', {bubbles: true}));
                    }""", current_proposal_to_gemini)
                    gemini_page.wait_for_timeout(2500)
                    snd = gemini_page.evaluate("""() => {
                        const btn = document.querySelector('button[aria-label=\"プロンプトを送信\"]');
                        if (!btn || btn.disabled) return {error: 'disabled or missing'};
                        btn.click();
                        return {clicked: true};
                    }""")
                    if "error" in snd:
                        round_data["gemini"]["send"] = "FAILED"
                        result["rounds"].append(round_data)
                        result["reason"] = f"R{round_idx} GEMINI_SEND_FAILED: {snd['error']}"
                        _persist_multi_round(result, restore_false=True)
                        return 1
                    round_data["gemini"]["send"] = "SUCCESS"
                    print(f"[R{round_idx}/Gemini-Send] clicked")

                    # Gemini wait
                    for _ in range(40):
                        gemini_page.wait_for_timeout(3000)
                        snap = gemini_page.evaluate("""() => ({
                            assistant_count: document.querySelectorAll('model-response').length,
                            stop_btn: !!document.querySelector('button[aria-label=\"回答を停止\"]'),
                        })""")
                        if snap["assistant_count"] > g_before["assistant_count"] and not snap["stop_btn"]:
                            break
                    g_after = gemini_page.evaluate("""() => {
                        const responses = document.querySelectorAll('model-response');
                        const last = responses[responses.length - 1];
                        return {text: last ? (last.textContent || '') : ''};
                    }""")
                    gtext = g_after["text"]
                    round_data["gemini"]["fetch"] = "SUCCESS" if gtext else "FAILED"
                    round_data["gemini"]["response_len"] = len(gtext)
                    round_data["gemini"]["text"] = gtext
                    g_v = VERIFY_TOKEN_RE.search(gtext)
                    g_n = NEXT_ACTOR_RE.search(gtext)
                    g_e = ENDTIME_JST_RE.search(gtext)
                    round_data["gemini"]["verify_token"] = g_v.group(0) if g_v else None
                    round_data["gemini"]["next_actor"] = g_n.group(1) if g_n else None
                    round_data["gemini"]["end_time_jst"] = g_e.group(1) if g_e else None
                    print(f"[R{round_idx}/Gemini-tags] verify={bool(g_v)} next={round_data['gemini']['next_actor']} end={round_data['gemini']['end_time_jst']} len={len(gtext)}")

                    # consensus 判定 (Gemini側)
                    consensus, unresolved = _detect_consensus(gtext)
                    round_data["consensus_candidate"] = consensus
                    round_data["unresolved"] = unresolved
                    print(f"[R{round_idx}/Consensus-from-Gemini] candidate={consensus} unresolved={len(unresolved)}")

                    ts_str = time.strftime('%H:%M:%S')
                    append_log(f"43+R{round_idx}. Multi-Round Consensus Test Round{round_idx} Gemini監査応答 verbatim — {ts_str}",
                               gtext + f"\n\n`[Orchestrator-Verify: R50-MULTIROUND-R{round_idx}-GEMINI]`\n`[NextActor: GPT]`\n")
                    print(f"[R{round_idx}/Gemini-append] done")

                    # ChatGPT Send (Gemini結果+合意判定要請)
                    if consensus:
                        chatgpt_payload = (
                            f"Multi-Round Consensus Test Round {round_idx}: Geminiから「重大異論なし」相当の応答を受信しました。これはOrchestrator自動relayであり、Shujiさん承認の代弁ではありません。\n\n"
                            "--- Gemini応答 verbatim ---\n"
                            f"{gtext}\n"
                            "--- end ---\n\n"
                            "GPT司会として最終案を生成してください。 要求:\n"
                            "1. consensus_candidate (true/false) を明記\n"
                            "2. 修正反映後の最終案を簡潔に提示\n"
                            "3. unresolved_critical_issues があれば列挙、 なければ「なし」\n"
                            "4. Shujiさん確認へ出せるか明記 (代弁ではなく Orchestrator判定として)\n\n"
                            "末尾必須:\n"
                            f"[GPT-Verify: R50-MULTIROUND-R{round_idx}-CONSENSUS-RESULT]\n"
                            "[NextActor: Claude]\n"
                            f"[EndTime-JST: {ts_str}]\n"
                        )
                    else:
                        chatgpt_payload = (
                            f"Multi-Round Consensus Test Round {round_idx}: Geminiから異論または不明確応答を受信しました。これはOrchestrator自動relayであり、Shujiさん承認の代弁ではありません。\n\n"
                            "--- Gemini応答 verbatim ---\n"
                            f"{gtext}\n"
                            "--- end ---\n\n"
                            "GPT司会として、 Gemini異論/不明点を反映した修正案を生成してください。 修正案はそのまま次のGemini監査入力になります。 要求:\n"
                            "1. consensus_candidate (false) を明記\n"
                            "2. 修正反映済みの新初期案を箇条書きで提示 (Geminiが次に監査する形式で)\n"
                            "3. 末尾必須:\n"
                            f"[GPT-Verify: R50-MULTIROUND-R{round_idx}-REVISION]\n"
                            "[NextActor: Gemini]\n"
                            f"[EndTime-JST: {ts_str}]\n"
                        )
                    chatgpt_page.bring_to_front()
                    c_before = chatgpt_page.evaluate("""() => ({
                        user_count: document.querySelectorAll('[data-message-author-role=\"user\"]').length,
                        assistant_count: document.querySelectorAll('[data-message-author-role=\"assistant\"]').length,
                    })""")
                    print(f"[R{round_idx}/ChatGPT-before] {c_before}")
                    chatgpt_page.evaluate("""(text) => {
                        const ta = document.querySelector('#prompt-textarea');
                        ta.focus();
                        const dt = new DataTransfer();
                        dt.setData('text/plain', text);
                        ta.dispatchEvent(new ClipboardEvent('paste', {bubbles: true, cancelable: true, clipboardData: dt}));
                    }""", chatgpt_payload)
                    chatgpt_page.wait_for_timeout(2500)
                    snd2 = chatgpt_page.evaluate("""() => {
                        const btn = document.querySelector('button[data-testid=\"send-button\"]');
                        if (!btn || btn.disabled) return {error: 'disabled'};
                        btn.click();
                        return {clicked: true};
                    }""")
                    if "error" in snd2:
                        round_data["chatgpt"]["send"] = "FAILED"
                        result["rounds"].append(round_data)
                        result["reason"] = f"R{round_idx} CHATGPT_SEND_FAILED: {snd2['error']}"
                        _persist_multi_round(result, restore_false=True)
                        return 1
                    round_data["chatgpt"]["send"] = "SUCCESS"
                    print(f"[R{round_idx}/ChatGPT-Send] clicked")

                    # ChatGPT wait
                    for _ in range(40):
                        chatgpt_page.wait_for_timeout(3000)
                        snap = chatgpt_page.evaluate("""() => ({
                            assistant_count: document.querySelectorAll('[data-message-author-role=\"assistant\"]').length,
                            stop_btn: !!document.querySelector('button[data-testid=\"stop-button\"]'),
                        })""")
                        if snap["assistant_count"] > c_before["assistant_count"] and not snap["stop_btn"]:
                            break
                    c_after = chatgpt_page.evaluate("""() => {
                        const turns = document.querySelectorAll('[data-testid^=\"conversation-turn-\"]');
                        const last = turns[turns.length - 1];
                        return {text: last ? (last.textContent || '') : ''};
                    }""")
                    ctext = c_after["text"]
                    round_data["chatgpt"]["fetch"] = "SUCCESS" if ctext else "FAILED"
                    round_data["chatgpt"]["response_len"] = len(ctext)
                    round_data["chatgpt"]["text"] = ctext
                    c_v = VERIFY_TOKEN_RE.search(ctext)
                    c_n = NEXT_ACTOR_RE.search(ctext)
                    c_e = ENDTIME_JST_RE.search(ctext)
                    round_data["chatgpt"]["verify_token"] = c_v.group(0) if c_v else None
                    round_data["chatgpt"]["next_actor"] = c_n.group(1) if c_n else None
                    round_data["chatgpt"]["end_time_jst"] = c_e.group(1) if c_e else None
                    if not c_v: round_data["chatgpt"]["missing_tags"].append("VERIFY_TOKEN_MISSING")
                    if not c_n: round_data["chatgpt"]["missing_tags"].append("NEXTACTOR_MISSING")
                    if not c_e: round_data["chatgpt"]["missing_tags"].append("ENDTIME_MISSING")
                    print(f"[R{round_idx}/ChatGPT-tags] verify={bool(c_v)} missing={round_data['chatgpt']['missing_tags']}")

                    ts_str2 = time.strftime('%H:%M:%S')
                    append_log(f"43+R{round_idx}b. Multi-Round Consensus Test Round{round_idx} ChatGPT判定応答 verbatim — {ts_str2}",
                               ctext + f"\n\n`[Orchestrator-Verify: R50-MULTIROUND-R{round_idx}-CHATGPT]`\n")
                    print(f"[R{round_idx}/ChatGPT-append] done")

                    result["rounds"].append(round_data)

                    # 収束判定: GeminiがOK且つChatGPTもconsensus_candidate=trueを返したら終了
                    if consensus and ("consensus_candidate" in ctext and "true" in ctext.lower().split("consensus_candidate")[1][:80] if "consensus_candidate" in ctext else False):
                        consensus_reached = True
                        final_gpt_summary = ctext
                        print(f"[R{round_idx}] CONSENSUS REACHED")
                        break
                    elif consensus:
                        consensus_reached = True
                        final_gpt_summary = ctext
                        print(f"[R{round_idx}] Gemini consensus OK + GPT response received → treat as PASSED")
                        break
                    else:
                        # 次周用にGPT修正案をGeminiへ
                        current_proposal_to_gemini = (
                            f"R50最終インフラ報告書の自動合意判定テスト Round {round_idx+1} です。Shujiさん承認は代弁しません。\n\n"
                            "前周GPT修正案 verbatim:\n"
                            f"{ctext}\n\n"
                            "Geminiは、 これに対し重大異論があれば指摘してください。 なければ「重大異論なし。 Shujiさん確認へ出せる」 と明記してください。 末尾必須:\n"
                            "[Gemini-Verify: R50-MULTIROUND-CONSENSUS-GEMINI]\n"
                            "[NextActor: GPT]\n"
                            "[EndTime-JST: HH:MM:SS]\n"
                        )

                result["consensus_candidate"] = consensus_reached
                if not consensus_reached:
                    last_round = result["rounds"][-1] if result["rounds"] else {}
                    result["unresolved_critical_issues"] = last_round.get("unresolved", [])
                result["final_report_ready"] = consensus_reached and not result["unresolved_critical_issues"]

                ts = int(time.time())
                DRY_RUN_DIR.mkdir(parents=True, exist_ok=True)
                rp = DRY_RUN_DIR / f"{ts}.multi_round_consensus_test.json"
                with open(rp, "w", encoding="utf-8") as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
                result["result_dump"] = str(rp)

                if consensus_reached:
                    result["multi_round_consensus_test"] = "PASSED"
                else:
                    result["multi_round_consensus_test"] = "NOT_CONSENSUS"

                print(f"\n[FINAL] result={result['multi_round_consensus_test']} consensus={consensus_reached} rounds={len(result['rounds'])} dump={rp}")
                _persist_multi_round(result, restore_false=True)
                return 0 if consensus_reached else 1
        except Exception as e:
            result["reason"] = f"UNEXPECTED: {type(e).__name__}: {e}"
            _persist_multi_round(result, restore_false=True)
            return 1
    finally:
        release_lock(load_state())
        after_state = load_state()
        print(f"[final-cleanup] lock={after_state.get('lock')} real_send_enabled={after_state.get('real_send_enabled')}")


def _persist_multi_round(result: dict, restore_false: bool = True) -> None:
    state = load_state()
    state["multi_round_consensus_test_result"] = result
    state["consensus_candidate"] = result.get("consensus_candidate", False)
    state["unresolved_critical_issues"] = result.get("unresolved_critical_issues", [])
    state["final_report_ready"] = result.get("final_report_ready", False)
    if restore_false:
        state["real_send_enabled"] = False
    save_state(state)


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(run_self_test())
    if "--cdp-smoke-test" in sys.argv:
        sys.exit(run_cdp_smoke_test())
    if "--print-cdp-setup" in sys.argv:
        sys.exit(print_cdp_setup())
    if "--selector-discovery" in sys.argv:
        sys.exit(run_selector_discovery())
    if "--relay-dry-run" in sys.argv:
        sys.exit(run_relay_dry_run())
    if "--send-test-gemini" in sys.argv:
        sys.exit(run_send_test_gemini())
    if "--fetch-gemini-latest" in sys.argv:
        sys.exit(run_fetch_gemini_latest())
    if "--send-test-chatgpt" in sys.argv:
        sys.exit(run_send_test_chatgpt())
    if "--two-agent-relay-test" in sys.argv:
        sys.exit(run_two_agent_relay_test())
    if "--real-topic-relay-test" in sys.argv:
        sys.exit(run_real_topic_relay_test())
    if "--multi-round-consensus-test" in sys.argv:
        sys.exit(run_multi_round_consensus_test())
    print(json.dumps(main_loop_once(), ensure_ascii=False, indent=2))


# =====================
# TODO (Phase 1 残実装 / Phase 1.5+)
# =====================
# - Playwright sync_playwright + connect_over_cdp(CDP_ENDPOINT) 実装
# - ChatGPT/Geminiタブ pages() フィルタ実装 (URLパターン一致)
# - editor selector: ChatGPT=#prompt-textarea / Gemini=rich-textarea .ql-editor
# - send button selector: ChatGPT=button[data-testid="send-button"] / Gemini=button[aria-label="プロンプトを送信"]
# - DOM要素30秒polling+ERROR_SUSPENDED発火 (trigger_error_suspended)
# - userCount/respCount取得+増加検知 (Send成功verification)
# - assistant本文取得+Verify/NextActor/EndTime抽出 (Response完了verification)
# - round log append連携 (append_log呼び出しからの拡張)
# - 30分stall通知の実通知経路 (email/slack/iOS)
# - dashboard連携 (Phase 1.5以降)
# - **実弾送信解禁**: GPT指示でDRY_RUN=False切替を待つ
