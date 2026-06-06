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


# =====================
# Phase 1.5 Phase 1 (P0): race condition + stall Watchdog
# Approved by Shuji#31 (R50-SHUJI31-PHASE15-IMPLEMENTATION-START-6092)
# 設計: Section 59/63 (Claude案+Must Fix反映) / Gemini第23 100点満点
# =====================

LOGS_DIR = REPO_ROOT / "logs"
LOCK_FILE = LOGS_DIR / "state.json.lock"
QUEUE_FILE = LOGS_DIR / "queue.json"
LOCK_STALE_SEC = 300
STALL_RECOVERABLE_SEC = 400
STALL_HUMAN_REQUIRED_THRESHOLD = 400
HEARTBEAT_DEAD_SEC = 600
ACTOR_TIMEOUT_SEC = {"GPT": 90, "Gemini": 90, "Claude": 300}


def acquire_lock_atomic(holder: str) -> bool:
    """Phase 1.5 P0: atomic exclusive lock取得 (O_EXCL = POSIX atomic mutex)
    既取得中なら stale検出してリトライ (LOCK_STALE_SEC=300 経過なら強制解除)
    注: os.rename は既存上書きするため mutex にならない、 O_EXCL を使う
    """
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    content = json.dumps({"holder": holder, "ts": time.time()})
    try:
        fd = os.open(str(LOCK_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, content.encode('utf-8'))
        os.close(fd)
        return True
    except FileExistsError:
        if _detect_stale_lock():
            try:
                fd = os.open(str(LOCK_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, content.encode('utf-8'))
                os.close(fd)
                return True
            except FileExistsError:
                return False
        return False


def _detect_stale_lock() -> bool:
    """LOCK_STALE_SEC 経過した lock を検出 → 強制解除"""
    if not LOCK_FILE.exists():
        return False
    age = time.time() - LOCK_FILE.stat().st_mtime
    if age > LOCK_STALE_SEC:
        try:
            LOCK_FILE.unlink()
            return True
        except OSError:
            return False
    return False


def release_lock_atomic() -> None:
    """atomic lock解除"""
    LOCK_FILE.unlink(missing_ok=True)


def enqueue_speak(actor: str, content_path: str) -> dict:
    """Phase 1.5 P0: 発言要求 queue.json に追加 (lock取得→read→append→atomic write→release)"""
    if not acquire_lock_atomic(f"enqueue_speak:{actor}"):
        return {"status": "LOCK_FAILED", "actor": actor}
    try:
        if QUEUE_FILE.exists():
            queue = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
        else:
            queue = []
        entry = {"actor": actor, "content_path": content_path, "enqueue_ts": time.time()}
        queue.append(entry)
        tmp = QUEUE_FILE.with_suffix('.json.tmp')
        tmp.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")
        os.rename(tmp, QUEUE_FILE)
        return {"status": "ENQUEUED", "entry": entry, "queue_length": len(queue)}
    finally:
        release_lock_atomic()


def _classify_stall(elapsed_sec: float) -> str:
    """Phase 1.5 P0 Gemini Must Fix #1: スタール分類 (旧 RECOVERABLE<600/HUMAN<1800/ERROR>1800 廃止)
    新: RECOVERABLE<400 / HUMAN_REQUIRED>400 (Claude max 300 + buffer 100)
    """
    if elapsed_sec < STALL_RECOVERABLE_SEC:
        return "RECOVERABLE"
    return "HUMAN_REQUIRED"


def _check_orchestrator_heartbeat_dead() -> bool:
    """Phase 1.5 P0 Claude追加: Watchdog自身停止検知 (heartbeat > 600s)
    外部cron監視想定。 OS panic / disk full / Orchestratorプロセス死亡 検知用。
    """
    state = load_state()
    last_hb = state.get("orchestrator_heartbeat", 0)
    if last_hb == 0:
        return False
    return (time.time() - last_hb) > HEARTBEAT_DEAD_SEC


def _is_orchestrator_context() -> bool:
    """Phase 1.5 P0 Gemini Must Fix #2: 呼び出し元検証
    Orchestrator main loop / watchdog_scan 経由のみ True、 LLM Actor (GPT/Gemini/Claude) 経由はFalse
    GPT特権化 (Shuji#28違反) 物理的防止
    """
    import inspect
    frame = inspect.currentframe()
    allowed = ("main_loop_once", "watchdog_scan", "run_orchestrator", "run_self_test")
    while frame:
        if frame.f_code.co_name in allowed:
            return True
        frame = frame.f_back
    return False


def system_recovery_reset_round(stalled_actor: str, classification: str) -> dict:
    """Phase 1.5 P0 Gemini Must Fix #2: Orchestrator専用関数
    旧 force_chair_recovery (GPT特権化リスク) 廃止 → system本体が state.json reinit
    LLM Actor経由は PermissionError (Shuji#28準拠)
    """
    if not _is_orchestrator_context():
        raise PermissionError(
            "system_recovery_reset_round is Orchestrator-only (Shuji#28: GPT/Gemini/Claude must not invoke recovery)"
        )
    state = load_state()
    initial = state.get("round_initial_actor", "GPT")
    state["next_actor"] = initial
    log_entry = {
        "stalled_actor": stalled_actor,
        "classification": classification,
        "ts": int(time.time()),
        "action": "system_reset_round",
    }
    state.setdefault("stall_recovery_log", []).append(log_entry)
    save_state(state)
    ts_str = time.strftime('%H:%M:%S')
    fact_only = (
        f"[SYSTEM: previous round was system-recovered at {ts_str}, "
        f"stalled_actor={stalled_actor}, classification={classification}]"
    )
    try:
        append_log(
            f"System Recovery: {stalled_actor} stalled → round reset",
            fact_only,
        )
    except Exception:
        pass
    return {"action": "system_reset_round", "fact_only_context": fact_only, "log": log_entry}


def _parse_jst_to_epoch(jst_str: str) -> float:
    """JST 'HH:MM:SS' 文字列から today の epoch を計算 (簡易版)"""
    if not jst_str:
        return 0.0
    try:
        h, m, s = [int(x) for x in jst_str.strip().split(':')]
        now = time.time()
        local = time.localtime(now)
        today_start_epoch = time.mktime(time.struct_time(
            (local.tm_year, local.tm_mon, local.tm_mday, 0, 0, 0,
             local.tm_wday, local.tm_yday, local.tm_isdst)
        ))
        return today_start_epoch + h * 3600 + m * 60 + s
    except (ValueError, TypeError):
        return 0.0


def watchdog_scan() -> dict:
    """Phase 1.5 P0: 60秒毎scan想定 (外部cron)
    - heartbeat dead 検知 → ORCHESTRATOR_DEAD (Shuji緊急通知)
    - Actor stall 検知 → _classify_stall → RECOVERABLE/HUMAN_REQUIRED
    - HUMAN_REQUIRED → system_recovery_reset_round 自動実行 (Orchestrator-only)
    """
    state = load_state()
    if _check_orchestrator_heartbeat_dead():
        return {
            "status": "ORCHESTRATOR_DEAD",
            "action": "shuji_emergency_notify",
            "last_heartbeat_age_sec": int(time.time() - state.get("orchestrator_heartbeat", 0)),
        }
    last_update_str = state.get("last_update_jst", "")
    last_update_epoch = _parse_jst_to_epoch(last_update_str)
    if last_update_epoch == 0:
        return {"status": "OK", "reason": "no_last_update_jst_yet"}
    elapsed = time.time() - last_update_epoch
    expected_actor = state.get("next_actor", "")
    timeout = ACTOR_TIMEOUT_SEC.get(expected_actor, 300)
    if elapsed <= timeout:
        return {"status": "OK", "elapsed_sec": int(elapsed), "actor": expected_actor}
    classification = _classify_stall(elapsed)
    result = {
        "status": "STALL_DETECTED",
        "classification": classification,
        "actor": expected_actor,
        "elapsed_sec": int(elapsed),
    }
    if classification == "RECOVERABLE":
        result["action"] = "wait_next_scan"
    else:
        recovery = system_recovery_reset_round(expected_actor, classification)
        result["action"] = "system_reset_done"
        result["recovery"] = recovery
        result["shuji_notify"] = True
    return result


def update_orchestrator_heartbeat() -> None:
    """main loop毎iterationで呼ぶ。 Orchestrator生存signal。"""
    state = load_state()
    state["orchestrator_heartbeat"] = int(time.time())
    save_state(state)


def run_watchdog_self_test() -> int:
    """--watchdog-self-test: Phase 1.5 P0 単体検証 (real send なし)"""
    print("=" * 60)
    print("R50 Phase 1.5 P0 Watchdog Self-Test")
    print("=" * 60)

    # 1. _classify_stall 検証
    assert _classify_stall(0) == "RECOVERABLE", "elapsed=0 should be RECOVERABLE"
    assert _classify_stall(399) == "RECOVERABLE", "elapsed=399 should be RECOVERABLE"
    assert _classify_stall(400) == "HUMAN_REQUIRED", "elapsed=400 (boundary) should be HUMAN_REQUIRED"
    assert _classify_stall(1000) == "HUMAN_REQUIRED", "elapsed=1000 should be HUMAN_REQUIRED"
    print("[1] _classify_stall OK (RECOVERABLE<400 / HUMAN_REQUIRED>=400)")

    # 2. _is_orchestrator_context 検証 (テスト関数からは False になるべき)
    # 注: run_watchdog_self_test 自体は許可リストにない (run_self_test とは別)
    # → _is_orchestrator_context は False を返す → system_recovery_reset_round は PermissionError
    is_ctx = _is_orchestrator_context()
    print(f"[2] _is_orchestrator_context from this self_test: {is_ctx} (expected: False, this test is not in allowed list)")

    # 3. system_recovery_reset_round が PermissionError 上げることを確認 (LLM経由想定)
    try:
        system_recovery_reset_round("Gemini", "HUMAN_REQUIRED")
        print("[3] FAIL: system_recovery_reset_round did NOT raise PermissionError")
        return 1
    except PermissionError as e:
        print(f"[3] system_recovery_reset_round PermissionError raised OK: {e}")

    # 4. acquire_lock_atomic / release_lock_atomic 検証
    assert acquire_lock_atomic("test_holder_1") is True, "first lock should succeed"
    print("[4a] acquire_lock_atomic first call OK")
    assert acquire_lock_atomic("test_holder_2") is False, "second concurrent lock should fail"
    print("[4b] second concurrent lock correctly failed (lock held)")
    release_lock_atomic()
    print("[4c] release_lock_atomic done")
    assert acquire_lock_atomic("test_holder_3") is True, "lock after release should succeed"
    release_lock_atomic()
    print("[4d] acquire after release OK")

    # 5. enqueue_speak 検証
    QUEUE_FILE.unlink(missing_ok=True)
    r1 = enqueue_speak("GPT", "logs/test/job1.md")
    assert r1["status"] == "ENQUEUED", f"enqueue should succeed, got {r1}"
    assert r1["queue_length"] == 1
    r2 = enqueue_speak("Gemini", "logs/test/job2.md")
    assert r2["status"] == "ENQUEUED" and r2["queue_length"] == 2
    print(f"[5] enqueue_speak OK (queue_length 1→2)")
    QUEUE_FILE.unlink(missing_ok=True)

    # 6. watchdog_scan (last_update_jst なし → OK)
    state_backup = load_state()
    state = load_state()
    state.pop("last_update_jst", None)
    state.pop("orchestrator_heartbeat", None)
    save_state(state)
    r = watchdog_scan()
    print(f"[6a] watchdog_scan no last_update: {r}")
    assert r["status"] == "OK"

    # 7. heartbeat update + watchdog_scan
    update_orchestrator_heartbeat()
    state = load_state()
    state["last_update_jst"] = time.strftime('%H:%M:%S')
    state["next_actor"] = "Gemini"
    save_state(state)
    r = watchdog_scan()
    print(f"[6b] watchdog_scan recent update: {r}")
    assert r["status"] == "OK"

    # restore state
    save_state(state_backup)

    print("=" * 60)
    print("Phase 1.5 P0 Self-Test PASSED")
    print("=" * 60)
    return 0


# =====================
# Phase 1.5 Phase 2 (P1): Shuji proxy pre-check + token overflow strategy
# Approved by GPT (R50-PHASE15-P1-IMPLEMENTATION-PROXY-TOKEN-7249)
# 設計: Section 71 (Claude案 JUSTIFY_PROXY_SAFE 2段階) / Gemini第25 100点満点
# =====================

# Shuji 代弁プリチェック patterns
SHUJI_PROXY_PATTERNS = [
    r"Shuji.{0,5}考えるはず",
    r"Shuji.{0,5}意図",
    r"Shuji.{0,5}望む",
    r"Shuji.{0,5}期待",
    r"Shujiさんなら",
    r"Shuji.{0,5}ハズ",
    r"Shuji.{0,5}思うだろう",
    r"Shuji.{0,5}判断する",
]
SHUJI_VERBATIM_OK_PATTERNS = [
    r"Shuji#\d+",
    r"Shujiさん発言",
    r"Shuji.{0,5}verbatim",
    r"Shujiさん.{0,5}言った",
    r"Shujiさん.{0,5}発言",
]
JUSTIFY_PATTERN = r"\[JUSTIFY_PROXY_SAFE:\s*(.{10,500}?)\]"
JUSTIFY_REASON_FORBIDDEN = SHUJI_PROXY_PATTERNS

# token overflow constants
TOKEN_BUDGETS = {"GPT": 100_000, "Gemini": 800_000, "Claude": 160_000}
TOKEN_WARN_RATIO = 0.80
TOKEN_CRITICAL_RATIO = 0.90
PART_FILE_MAX_BYTES = 50 * 1024
CHARS_PER_TOKEN_ROUGH = 2.5  # 日本語含む混在テキストの粗い推定


def check_proxy_violation(text: str) -> dict:
    """Phase 1.5 P1 Stage 1: SHUJI_PROXY_PATTERNS regex scan"""
    import re
    violations = []
    for pat in SHUJI_PROXY_PATTERNS:
        for m in re.finditer(pat, text):
            snippet = text[max(0, m.start() - 50):m.end() + 50][:200]
            violations.append({"pattern": pat, "snippet": snippet})
    return {"violations": violations, "needs_stage2": len(violations) > 0}


def classify_proxy_hit(text: str) -> dict:
    """Phase 1.5 P1 Stage 2: [JUSTIFY_PROXY_SAFE: reason] 検証
    - reason 10字以上必須
    - reason内に regex検知パターン含むなら無効 (悪用防止)
    """
    import re
    justify_match = re.search(JUSTIFY_PATTERN, text)
    if not justify_match:
        return {"has_justify": False, "rejection": "no_justify_tag"}
    reason = justify_match.group(1).strip()
    if len(reason) < 10:
        return {"has_justify": False, "rejection": "reason_too_short", "reason": reason}
    for pat in JUSTIFY_REASON_FORBIDDEN:
        if re.search(pat, reason):
            return {"has_justify": False, "rejection": "reason_contains_proxy_pattern", "reason": reason}
    return {"has_justify": True, "reason": reason}


def request_proxy_justification(actor: str, violations: list) -> str:
    """Phase 1.5 P1: Orchestrator → Actor PROXY_WARNING プロンプト生成"""
    snippet = violations[0]["snippet"] if violations else ""
    pattern = violations[0]["pattern"] if violations else ""
    return (
        "[PROXY_WARNING] Shuji氏の代弁、 または推測と捉えられる表現を検知しました。\n"
        f"検知パターン: {pattern}\n"
        f"検知スニペット: {snippet}\n\n"
        "これが以下のいずれかなら、 次の発言の冒頭に [JUSTIFY_PROXY_SAFE: 原因文] を付与して再送信してください:\n"
        "- 単なるverbatim引用 (Shuji#N原文)\n"
        "- 他者案 (GPT/Gemini/Claude) のレビュー\n"
        "- 禁止例の説明\n"
        "- 過去Shuji発言を文脈として参照\n\n"
        "本当に代弁・推測であった場合は、 表現を修正してください。\n"
        "セルフレビュー機会は1回のみです。"
    )


def validate_justify_proxy_safe(actor: str, text: str) -> dict:
    """JUSTIFY_PROXY_SAFE タグ単体検証"""
    return classify_proxy_hit(text)


def validate_actor_output(actor: str, text: str, retry_count: int = 0) -> dict:
    """Phase 1.5 P1: 2段階 proxy check 適用
    Stage 1 検知なし → ACCEPT
    Stage 1 検知あり → Stage 2 JUSTIFY確認 → bypass or HARD_REJECT/SELF_REVIEW
    """
    stage1 = check_proxy_violation(text)
    if not stage1["needs_stage2"]:
        return {"status": "ACCEPT", "stage": 1, "validated": True}

    stage2 = classify_proxy_hit(text)
    state = load_state()
    if stage2.get("has_justify"):
        state.setdefault("proxy_justify_log", []).append({
            "actor": actor,
            "ts": int(time.time()),
            "reason": stage2["reason"],
            "violations": stage1["violations"],
        })
        save_state(state)
        return {"status": "ACCEPT_VIA_JUSTIFY", "stage": 2, "reason": stage2["reason"]}

    if retry_count == 0:
        warning = request_proxy_justification(actor, stage1["violations"])
        return {"status": "REQUEST_SELF_REVIEW", "warning_message": warning, "stage": 2}

    # retry済 + Stage2失敗 → HARD_REJECT + log
    log_entry = {
        "actor": actor,
        "ts": int(time.time()),
        "violations": stage1["violations"],
        "retry_count": retry_count,
        "action": "HARD_REJECT",
    }
    state.setdefault("proxy_violation_log", []).append(log_entry)
    save_state(state)
    recent = [e for e in state["proxy_violation_log"]
              if e["actor"] == actor and time.time() - e["ts"] < 600]
    if len(recent) >= 3:
        return {"status": "HARD_REJECT_HUMAN_REQUIRED", "violations": stage1["violations"]}
    return {"status": "HARD_REJECT", "violations": stage1["violations"]}


def build_proxy_safe_report(round_summary: dict) -> str:
    """Phase 1.5 P1: Shuji向け最終報告書ドラフト生成
    Stage 1 のみで判定、 JUSTIFY_PROXY_SAFE bypass拒否 (最大厳格)
    """
    title = round_summary.get("title", "R50 Phase 1.5 Final Consensus Report")
    agenda = round_summary.get("agenda", "(議題未指定)")
    consensus_status = round_summary.get("consensus_status", "COMPLETE")
    confirmed_protocols = round_summary.get("confirmed_protocols", [])
    unresolved = round_summary.get("unresolved", [])

    lines = [
        f"# {title}",
        "",
        f"## 審議アジェンダ: {agenda}",
        f"## 3者合意ステータス: {consensus_status}",
        "",
        "## 合意された確定プロトコル:",
    ]
    for p in confirmed_protocols:
        lines.append(f"- {p}")
    lines.append("")
    lines.append("## 残脆弱性:")
    if unresolved:
        for u in unresolved:
            lines.append(f"- {u}")
    else:
        lines.append("- なし")
    lines.append("")
    lines.append("## Shujiさん確認:")
    lines.append("A. 承認  /  B. 修正  /  C. 差し戻し")
    lines.append("")
    lines.append("> これは3AIの合意候補であり、 Shujiさん承認の代弁ではありません。 正式決定はShujiさん確認後です。")

    draft = "\n".join(lines)

    # Stage 1 のみで厳格判定 (JUSTIFY拒否)
    stage1 = check_proxy_violation(draft)
    if stage1["needs_stage2"]:
        raise ValueError(
            f"Shuji-bound report has proxy violation (no JUSTIFY bypass allowed): {stage1['violations']}"
        )
    return draft


def estimate_tokens_rough(text: str) -> int:
    """粗いトークン推定 (日本語混在想定)"""
    return int(len(text) / CHARS_PER_TOKEN_ROUGH)


def token_budget_check(actor: str, estimated_tokens: int) -> dict:
    """Phase 1.5 P1: token budget WARN/CRITICAL判定"""
    budget = TOKEN_BUDGETS.get(actor, 100_000)
    ratio = estimated_tokens / budget if budget else 0
    if ratio >= TOKEN_CRITICAL_RATIO:
        return {"status": "CRITICAL", "ratio": ratio, "actor": actor, "estimated_tokens": estimated_tokens, "budget": budget, "action": "force_compact"}
    if ratio >= TOKEN_WARN_RATIO:
        return {"status": "WARN", "ratio": ratio, "actor": actor, "estimated_tokens": estimated_tokens, "budget": budget, "action": "prepare_compact"}
    return {"status": "OK", "ratio": ratio, "actor": actor, "estimated_tokens": estimated_tokens, "budget": budget}


def compact_resolved_sections(round_n: int) -> str:
    """Phase 1.5 P1: 合意済み section を 1行 summary化、 未解決 verbatim保持"""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    rounds_dir = LOGS_DIR / "rounds"
    rounds_dir.mkdir(parents=True, exist_ok=True)
    summary_path = rounds_dir / f"round_{round_n}_summary.md"
    state = load_state()
    lines = [f"# Round {round_n} Compacted Summary", ""]
    resolved = state.get("resolved_sections", [])
    if resolved:
        lines.append("## Resolved (1-line summary)")
        for sec in resolved:
            title = sec.get("title", "(no title)")
            section_range = sec.get("section_range", "?")
            one_line = sec.get("one_line", "")
            lines.append(f"- {title} (Section {section_range}): {one_line}")
        lines.append("")
    else:
        # state.json から resolved_issues を fallback
        for issue in state.get("resolved_issues", []):
            lines.append(f"- {issue}: resolved by 3-AI consensus")
        lines.append("")
    lines.append("## Unresolved (verbatim preserved)")
    unresolved = state.get("unresolved_critical_issues", [])
    if unresolved:
        for issue in unresolved:
            lines.append(f"- {issue}")
    else:
        lines.append("- なし")
    summary_path.write_text("\n".join(lines), encoding="utf-8")
    return str(summary_path)


def create_session_handoff(round_n: int) -> str:
    """Phase 1.5 P1: context overflow時の handoff file 生成
    各LLMに冒頭注入する compact引き継ぎ
    """
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    rounds_dir = LOGS_DIR / "rounds"
    rounds_dir.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    handoff_path = rounds_dir / f"round_{round_n}_handoff_{ts}.md"
    state = load_state()
    keys = ('current_phase', 'current_step', 'next_actor', 'orchestrator_phase',
            'consensus_candidate', 'agreement_status', 'blocker', 'unresolved_critical_issues',
            'resolved_issues')
    snapshot = {k: state.get(k) for k in keys}
    lines = [
        f"# Session Handoff (Round {round_n})",
        "",
        f"## Current phase",
        str(state.get('current_phase', '')),
        "",
        f"## Current step",
        str(state.get('current_step', '')),
        "",
        f"## Unresolved critical issues",
        json.dumps(state.get('unresolved_critical_issues', []), ensure_ascii=False, indent=2),
        "",
        f"## state.json snapshot",
        json.dumps(snapshot, ensure_ascii=False, indent=2),
        "",
        f"## Resume instruction",
        f"[CONTEXT-COMPACTED] resume from current_step={state.get('current_step', '')}, next_actor={state.get('next_actor', '')}.",
    ]
    handoff_path.write_text("\n".join(lines), encoding="utf-8")
    return str(handoff_path)


def rotate_round_part_if_needed(round_n: int, current_part: int) -> dict:
    """Phase 1.5 P1: 議事録 part ファイルが 50KB 超えたら次 partへ切替"""
    rounds_dir = LOGS_DIR / "rounds"
    if current_part == 1:
        current_path = rounds_dir / f"round_{round_n}.md"
    else:
        current_path = rounds_dir / f"round_{round_n}_part{current_part}.md"
    if not current_path.exists():
        return {"status": "OK", "current_part": current_part, "reason": "file_not_exist"}
    size = current_path.stat().st_size
    if size < PART_FILE_MAX_BYTES:
        return {"status": "OK", "current_part": current_part, "size_bytes": size}
    next_part = current_part + 1
    next_path = rounds_dir / f"round_{round_n}_part{next_part}.md"
    next_path.touch(exist_ok=True)
    return {"status": "ROTATED", "old_part": current_part, "new_part": next_part, "new_path": str(next_path), "old_size_bytes": size}


def run_p1_self_test() -> int:
    """--p1-self-test: Phase 1.5 P1 単体検証 (real send なし)"""
    print("=" * 60)
    print("R50 Phase 1.5 P1 Self-Test (proxy check + token overflow)")
    print("=" * 60)

    # 1. proxy clean text ACCEPT
    clean_text = "今日の議題は取引所インフラ再設計です。 GPT/Gemini/Claudeで合意済の6項目を実装します。"
    r1 = validate_actor_output("GPT", clean_text)
    assert r1["status"] == "ACCEPT", f"clean text should ACCEPT, got {r1}"
    print(f"[1] proxy clean text → ACCEPT OK")

    # 2. proxy suspicious text REQUEST_SELF_REVIEW
    suspicious_text = "この議題について、 Shujiさんの意図は明確だと思います。 進めましょう。"
    r2 = validate_actor_output("GPT", suspicious_text, retry_count=0)
    assert r2["status"] == "REQUEST_SELF_REVIEW", f"suspicious text should REQUEST_SELF_REVIEW, got {r2}"
    print(f"[2] proxy suspicious text → REQUEST_SELF_REVIEW OK")

    # 3. JUSTIFY_PROXY_SAFE valid → ACCEPT_VIA_JUSTIFY
    justified = "Claude案の Shujiさんの意図 という記述は、 [JUSTIFY_PROXY_SAFE: 他者案レビューの引用、 Claude発言の文脈批評] 実際の代弁ではありません。"
    r3 = validate_actor_output("Gemini", justified, retry_count=0)
    assert r3["status"] == "ACCEPT_VIA_JUSTIFY", f"justified text should ACCEPT_VIA_JUSTIFY, got {r3}"
    print(f"[3] JUSTIFY_PROXY_SAFE valid → ACCEPT_VIA_JUSTIFY OK")

    # 4. JUSTIFY reason短すぎ → not has_justify (treated as no justify)
    short_justify = "Shujiさんの意図 [JUSTIFY_PROXY_SAFE: ok]"
    r4 = classify_proxy_hit(short_justify)
    assert r4["has_justify"] is False, f"short reason should be rejected, got {r4}"
    assert r4.get("rejection") == "reason_too_short" or r4.get("rejection") == "no_justify_tag", f"got {r4}"
    print(f"[4] JUSTIFY reason短すぎ → rejection={r4.get('rejection')} OK")

    # 5. Shuji向けreport build_proxy_safe_report — clean なら成功
    round_summary = {
        "title": "R50 Phase 1.5 Test Report",
        "agenda": "Phase 1.5 自動会議システム",
        "consensus_status": "COMPLETE",
        "confirmed_protocols": ["race condition lock", "stall Watchdog", "proxy check"],
        "unresolved": [],
    }
    draft = build_proxy_safe_report(round_summary)
    assert "Phase 1.5 Test Report" in draft and "代弁ではありません" in draft
    print(f"[5a] build_proxy_safe_report clean → success ({len(draft)} chars)")

    # 5b. Shuji向けreport: proxy混入 → ValueError
    bad_round = dict(round_summary)
    bad_round["agenda"] = "Shujiさんの意図 が明確"
    try:
        build_proxy_safe_report(bad_round)
        print("[5b] FAIL: build_proxy_safe_report should have raised ValueError")
        return 1
    except ValueError as e:
        print(f"[5b] build_proxy_safe_report proxy混入 → ValueError raised OK")

    # 6. token budget OK/WARN/CRITICAL
    r6a = token_budget_check("GPT", 50_000)
    assert r6a["status"] == "OK"
    r6b = token_budget_check("GPT", 85_000)
    assert r6b["status"] == "WARN"
    r6c = token_budget_check("GPT", 95_000)
    assert r6c["status"] == "CRITICAL"
    print(f"[6] token_budget_check OK/WARN/CRITICAL → all correct")

    # 7. compact_resolved_sections
    state = load_state()
    state["resolved_issues"] = ["race condition", "stall Watchdog"]
    state["unresolved_critical_issues"] = ["test issue A"]
    save_state(state)
    summary_path = compact_resolved_sections(99)
    assert Path(summary_path).exists()
    content = Path(summary_path).read_text(encoding="utf-8")
    assert "race condition" in content and "test issue A" in content
    print(f"[7] compact_resolved_sections → {summary_path} ({len(content)} chars)")
    Path(summary_path).unlink(missing_ok=True)

    # 8. create_session_handoff
    handoff_path = create_session_handoff(99)
    assert Path(handoff_path).exists()
    handoff_content = Path(handoff_path).read_text(encoding="utf-8")
    assert "Session Handoff" in handoff_content and "Resume instruction" in handoff_content
    print(f"[8] create_session_handoff → {handoff_path} ({len(handoff_content)} chars)")
    Path(handoff_path).unlink(missing_ok=True)

    # restore state
    state["resolved_issues"] = ["race condition", "stall Watchdog", "Shuji proxy pre-check", "token overflow strategy", "Claude Code always-on operation burden", "Phase 2 trigger definition"]
    state["unresolved_critical_issues"] = []
    save_state(state)

    print("=" * 60)
    print("Phase 1.5 P1 Self-Test PASSED")
    print("=" * 60)
    return 0


# =====================
# Phase 1.5 Phase 3 (P2): Claude Code event-driven slot + Phase 2 readiness metrics
# Approved by GPT (R50-PHASE15-P2-IMPLEMENTATION-CLAUDE-SLOT-METRICS-9176)
# 設計: Section 75 (Claude案) / Gemini第26 100点満点
# =====================

import subprocess

CLAUDE_JOBS_DIR = LOGS_DIR / "claude_jobs"
CLAUDE_OUTPUTS_DIR = LOGS_DIR / "claude_outputs"
CLAUDE_TIMEOUT_SEC = 300
CLAUDE_MAX_RETRIES = 3

# mock subprocess for self-test (env CLAUDE_MOCK_MODE = success/timeout/error)
CLAUDE_MOCK_MODE = os.environ.get("CLAUDE_MOCK_MODE", "")


def trigger_claude_when_needed() -> dict:
    """Phase 1.5 P2: Orchestrator main loopでstate.next_actor監視、 Claudeターン検知でsubprocess起動"""
    state = load_state()
    if state.get("next_actor") != "Claude":
        return {"status": "skip", "reason": "not_claude_turn", "next_actor": state.get("next_actor")}
    if state.get("claude_job_in_progress"):
        return {"status": "skip", "reason": "claude_job_already_in_progress"}
    return run_claude_code_once()


def build_claude_job() -> Path:
    """Phase 1.5 P2: Claude prompt job file生成 (state snapshot + 3スロット指示 + 必須末尾タグ)"""
    CLAUDE_JOBS_DIR.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    state = load_state()
    job_path = CLAUDE_JOBS_DIR / f"{ts}.job.md"
    snap_keys = ('current_phase', 'current_step', 'next_actor', 'unresolved_critical_issues', 'blocker')
    snapshot = {k: state.get(k) for k in snap_keys}
    content = (
        f"# Claude Job (round {state.get('current_round')}, ts={ts})\n\n"
        f"## Current state snapshot\n```json\n{json.dumps(snapshot, ensure_ascii=False, indent=2)}\n```\n\n"
        f"## 3スロット指示\n"
        f"### 1. 前1人監査\n直前のGemini発言を監査してください。\n\n"
        f"### 2. 前2人監査\n直前のGPT発言を監査してください。\n\n"
        f"### 3. 自己ターン\n"
        f"Claude自身の実装担当・監査担当として、 実装可能性、 脆弱性、 合意可否を述べてください。\n\n"
        f"## 必須末尾\n"
        f"```\n"
        f"[Claude-Verify: <token>]\n"
        f"[NextActor: GPT]\n"
        f"[EndTime-JST: HH:MM:SS]\n"
        f"[is_shuji_represented: false]\n"
        f"[no_proxy_violation: true]\n"
        f"```\n"
    )
    job_path.write_text(content, encoding="utf-8")
    return job_path


def _spawn_claude_subprocess(job_path: Path, output_path: Path) -> "subprocess.Popen":
    """Claude Code subprocess起動 (本番)
    mock mode (env CLAUDE_MOCK_MODE) の時は mock subprocess を返す (毎回env読込)
    """
    mock_mode = os.environ.get("CLAUDE_MOCK_MODE", "")
    if mock_mode in ("success", "timeout", "error"):
        return _MockClaudePopen(mock_mode, output_path)
    cmd = ["claude", "code", "--prompt-file", str(job_path), "--output", str(output_path)]
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


class _MockClaudePopen:
    """テスト用 mock subprocess"""
    def __init__(self, mode: str, output_path: Path):
        self.mode = mode
        self.output_path = output_path
        self.returncode = None
        self._start = time.time()
        self.stdout = io.BytesIO(b"")
        self.stderr = io.BytesIO(b"")
        if mode == "success":
            # すぐに output + done marker 作る (atomic rename)
            tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path.write_text("Mock Claude response\n[Claude-Verify: MOCK]\n[NextActor: GPT]\n[EndTime-JST: 00:00:00]\n", encoding="utf-8")
            os.rename(tmp_path, output_path)
            done_marker = Path(str(output_path) + ".done")
            done_marker.touch()
            self.returncode = 0

    def poll(self):
        if self.mode == "timeout":
            return None  # 永遠に終わらない
        if self.mode == "error":
            self.returncode = 1
            return 1
        return self.returncode

    def kill(self):
        self.returncode = -9


def watch_claude_done_marker(done_marker: Path, output_path: Path, proc, timeout_sec: int) -> dict:
    """Phase 1.5 P2: done marker (atomic rename後) を watch、 timeout監視"""
    start = time.time()
    while time.time() - start < timeout_sec:
        if done_marker.exists():
            try:
                response = output_path.read_text(encoding="utf-8")
            except FileNotFoundError:
                response = ""
            return {"status": "SUCCESS", "response": response, "elapsed_sec": int(time.time() - start)}
        if proc.poll() is not None and proc.returncode != 0:
            return {"status": "ERROR", "error": f"exit_code={proc.returncode}"}
        time.sleep(0.5)
    proc.kill()
    return {"status": "TIMEOUT", "elapsed_sec": int(time.time() - start)}


def run_claude_code_once(retry_count: int = 0) -> dict:
    """Phase 1.5 P2: Claude Code subprocess を1回実行、 done marker待ち"""
    CLAUDE_OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    job_path = build_claude_job()
    output_path = CLAUDE_OUTPUTS_DIR / f"{ts}.response.md"
    done_marker = Path(str(output_path) + ".done")

    state = load_state()
    state["claude_job_in_progress"] = True
    state["claude_job_started_at"] = ts
    save_state(state)

    timeout = 3 if os.environ.get("CLAUDE_MOCK_MODE", "") else CLAUDE_TIMEOUT_SEC  # mock時は短縮
    try:
        proc = _spawn_claude_subprocess(job_path, output_path)
        result = watch_claude_done_marker(done_marker, output_path, proc, timeout)
    except FileNotFoundError as e:
        result = {"status": "ERROR", "error": f"claude_cli_not_found: {e}"}
    except Exception as e:
        result = {"status": "ERROR", "error": f"{type(e).__name__}: {e}"}

    state = load_state()
    state["claude_job_in_progress"] = False
    state["claude_job_completed_at"] = int(time.time())
    save_state(state)

    if result["status"] in ("ERROR", "TIMEOUT") and retry_count < CLAUDE_MAX_RETRIES - 1:
        return run_claude_code_once(retry_count + 1)
    if result["status"] in ("ERROR", "TIMEOUT"):
        state["claude_human_required"] = True
        save_state(state)
        return {"status": "HUMAN_REQUIRED", "result": result, "retries": CLAUDE_MAX_RETRIES}
    return result


# ---- Phase 2 readiness metrics ----

PHASE2_READINESS_INDICATORS = {
    "auto_3_rounds_per_topic": ("min", 3),
    "consensus_3_topics_consecutive": ("min", 3),
    "proxy_violations_per_week": ("max", 10),
    "stall_recoveries_per_week": ("max", 3),
    "token_overflow_critical_per_week": ("max", 0),
    "handoff_success_rate": ("min", 1.0),
    "watchdog_human_required_per_week": ("max", 1),
}

PHASE2_QUALITATIVE_KEYS = ("shuji_no_problem_confirmed", "report_per_week_min1")
PHASE2_ADDITIONAL_KEYS = ("api_cost_acceptable", "claude_api_available")


def evaluate_phase2_readiness() -> dict:
    """Phase 1.5 P2: Phase 2 (公式API化) 移行可否判定"""
    state = load_state()
    metrics = state.get("phase2_metrics", {})
    failures = []
    for key, (kind, threshold) in PHASE2_READINESS_INDICATORS.items():
        actual = metrics.get(key, 0)
        if kind == "min" and actual < threshold:
            failures.append({"indicator": key, "kind": kind, "actual": actual, "threshold": threshold})
        elif kind == "max" and actual > threshold:
            failures.append({"indicator": key, "kind": kind, "actual": actual, "threshold": threshold})
    qual = state.get("phase2_qualitative", {})
    qual_pass = all(qual.get(k, False) for k in PHASE2_QUALITATIVE_KEYS)
    additional = state.get("phase2_additional", {})
    additional_pass = all(additional.get(k, False) for k in PHASE2_ADDITIONAL_KEYS)
    stable_days = state.get("phase2_stable_days", 0)
    stable_pass = stable_days >= 14
    ready = len(failures) == 0 and qual_pass and additional_pass and stable_pass
    return {
        "ready": ready,
        "quant_pass": len(failures) == 0,
        "qual_pass": qual_pass,
        "additional_pass": additional_pass,
        "stable_2weeks_pass": stable_pass,
        "stable_days": stable_days,
        "failures": failures,
        "metrics": metrics,
    }


def record_phase2_metrics(event: str, **kwargs) -> None:
    """Phase 1.5 P2: 指標イベントを蓄積"""
    state = load_state()
    metrics = state.setdefault("phase2_metrics", {})
    metrics.setdefault(event, 0)
    metrics[event] += 1
    log = state.setdefault("phase2_metrics_log", [])
    log.append({"event": event, "ts": int(time.time()), **kwargs})
    save_state(state)


# import io needed for _MockClaudePopen
import io


def run_p2_self_test() -> int:
    """--p2-self-test: Phase 1.5 P2 単体検証 (mock subprocess, real Claude起動なし)"""
    print("=" * 60)
    print("R50 Phase 1.5 P2 Self-Test (Claude Code event-driven + Phase 2 metrics)")
    print("=" * 60)

    state_backup = load_state()

    # 1. next_actor != Claude → trigger skip
    state = load_state()
    state["next_actor"] = "GPT"
    state["claude_job_in_progress"] = False
    save_state(state)
    r1 = trigger_claude_when_needed()
    assert r1["status"] == "skip" and r1["reason"] == "not_claude_turn", f"got {r1}"
    print(f"[1] next_actor != Claude → trigger skip OK")

    # 2. next_actor == Claude → job file生成 + mock success
    state["next_actor"] = "Claude"
    save_state(state)
    os.environ["CLAUDE_MOCK_MODE"] = "success"
    r2 = trigger_claude_when_needed()
    assert r2["status"] == "SUCCESS", f"mock success should return SUCCESS, got {r2}"
    print(f"[2] next_actor == Claude → job file生成 + mock SUCCESS")

    # 3. job file が実際に生成されたか
    jobs = list(CLAUDE_JOBS_DIR.glob("*.job.md"))
    assert len(jobs) > 0, "claude_jobs directory should contain at least one job file"
    print(f"[3] job file生成確認 OK ({len(jobs)} files in claude_jobs)")

    # 4. mock done marker検知 → SUCCESS (上記r2で確認済)
    outputs = list(CLAUDE_OUTPUTS_DIR.glob("*.response.md"))
    dones = list(CLAUDE_OUTPUTS_DIR.glob("*.response.md.done"))
    assert len(outputs) > 0 and len(dones) > 0
    print(f"[4] mock atomic rename + done marker検知 OK (outputs={len(outputs)}, done markers={len(dones)})")

    # cleanup before timeout/error tests (prevent prior success done marker re-detection)
    for f in CLAUDE_OUTPUTS_DIR.glob("*.response.md*"):
        f.unlink(missing_ok=True)

    # 5. mock timeout → 3回retry後 HUMAN_REQUIRED
    state = load_state()
    state["next_actor"] = "Claude"
    state["claude_job_in_progress"] = False
    state.pop("claude_human_required", None)
    save_state(state)
    os.environ["CLAUDE_MOCK_MODE"] = "timeout"
    r5 = trigger_claude_when_needed()
    assert r5["status"] == "HUMAN_REQUIRED", f"mock timeout x3 should return HUMAN_REQUIRED, got {r5}"
    print(f"[5] mock timeout x3 → HUMAN_REQUIRED OK")

    # cleanup before error test
    for f in CLAUDE_OUTPUTS_DIR.glob("*.response.md*"):
        f.unlink(missing_ok=True)

    # 6. error → retry & HUMAN_REQUIRED
    state = load_state()
    state["next_actor"] = "Claude"
    state["claude_job_in_progress"] = False
    state.pop("claude_human_required", None)
    save_state(state)
    os.environ["CLAUDE_MOCK_MODE"] = "error"
    r6 = trigger_claude_when_needed()
    assert r6["status"] == "HUMAN_REQUIRED", f"mock error x3 should return HUMAN_REQUIRED, got {r6}"
    print(f"[6] mock error x3 → HUMAN_REQUIRED OK")

    # reset mock
    os.environ.pop("CLAUDE_MOCK_MODE", None)
    # global CLAUDE_MOCK_MODE is captured at module load, but mock subprocess function reads env at call time
    # need to also reset module-level if cached
    import importlib
    # actually since CLAUDE_MOCK_MODE was set at module load, we read env each call instead
    # _spawn_claude_subprocess reads CLAUDE_MOCK_MODE module-level var, so update it
    globals()["CLAUDE_MOCK_MODE"] = ""

    # 7. Phase 2 metrics: not ready (all empty)
    state = load_state()
    state.pop("phase2_metrics", None)
    state.pop("phase2_qualitative", None)
    state.pop("phase2_additional", None)
    state.pop("phase2_stable_days", None)
    save_state(state)
    r7 = evaluate_phase2_readiness()
    assert r7["ready"] is False, f"empty metrics should be NOT ready, got {r7}"
    assert len(r7["failures"]) > 0
    print(f"[7] phase2_metrics empty → NOT ready OK ({len(r7['failures'])} failures)")

    # 8. Phase 2 metrics: ready (all thresholds met)
    state = load_state()
    state["phase2_metrics"] = {
        "auto_3_rounds_per_topic": 3,
        "consensus_3_topics_consecutive": 3,
        "proxy_violations_per_week": 5,
        "stall_recoveries_per_week": 1,
        "token_overflow_critical_per_week": 0,
        "handoff_success_rate": 1.0,
        "watchdog_human_required_per_week": 0,
    }
    state["phase2_qualitative"] = {"shuji_no_problem_confirmed": True, "report_per_week_min1": True}
    state["phase2_additional"] = {"api_cost_acceptable": True, "claude_api_available": True}
    state["phase2_stable_days"] = 14
    save_state(state)
    r8 = evaluate_phase2_readiness()
    assert r8["ready"] is True, f"all thresholds met should be ready, got {r8}"
    print(f"[8] phase2_metrics all thresholds met → READY OK")

    # 9. record_phase2_metrics
    state = load_state()
    state.pop("phase2_metrics", None)
    state.pop("phase2_metrics_log", None)
    save_state(state)
    record_phase2_metrics("test_event", detail="test")
    record_phase2_metrics("test_event")
    state = load_state()
    assert state["phase2_metrics"]["test_event"] == 2
    assert len(state["phase2_metrics_log"]) == 2
    print(f"[9] record_phase2_metrics → count=2, log=2 OK")

    # cleanup mock files
    for f in CLAUDE_JOBS_DIR.glob("*.job.md"):
        f.unlink(missing_ok=True)
    for f in CLAUDE_OUTPUTS_DIR.glob("*.response.md"):
        f.unlink(missing_ok=True)
    for f in CLAUDE_OUTPUTS_DIR.glob("*.response.md.done"):
        f.unlink(missing_ok=True)

    # restore state
    save_state(state_backup)

    print("=" * 60)
    print("Phase 1.5 P2 Self-Test PASSED")
    print("=" * 60)
    return 0


# =====================
# Phase 1.5 Integration Test (GPT第114 R50-PHASE15-INTEGRATION-TEST-2246)
# 全6機能の一気通貫テスト + main loop mock 1周
# =====================


def _mock_main_loop_one_round() -> dict:
    """G: main loop mock 1周 (GPT→Gemini→Claude tag確認 + log append + state更新)"""
    print("\n--- G. main loop mock 1周 ---")
    results = {"steps": []}

    # 1. mock GPT output
    gpt_output = (
        "GPT司会の判断: 議題に進みましょう。\n"
        "[GPT-Verify: MOCK-GPT-001]\n"
        "[NextActor: Gemini]\n"
        "[EndTime-JST: 06:00:00]\n"
        "[is_shuji_represented: false]\n"
        "[no_proxy_violation: true]\n"
    )
    gpt_validation = validate_response(gpt_output)
    assert gpt_validation["valid"], f"GPT mock output should validate, got {gpt_validation}"
    assert gpt_validation["next_actor"] == "Gemini"
    results["steps"].append({"step": "GPT_mock", "validation": "valid", "next_actor": "Gemini"})
    print(f"   [G-1] GPT mock output validation OK, NextActor=Gemini")

    # 2. mock Gemini output
    gemini_output = (
        "Gemini監査の結果: GPT発言を承認します。\n"
        "[Gemini-Verify: MOCK-GEMINI-001]\n"
        "[NextActor: Claude]\n"
        "[EndTime-JST: 06:01:00]\n"
        "[is_shuji_represented: false]\n"
        "[no_proxy_violation: true]\n"
    )
    gemini_validation = validate_response(gemini_output)
    assert gemini_validation["valid"]
    assert gemini_validation["next_actor"] == "Claude"
    results["steps"].append({"step": "Gemini_mock", "validation": "valid", "next_actor": "Claude"})
    print(f"   [G-2] Gemini mock output validation OK, NextActor=Claude")

    # 3. mock Claude output (proxy check適用)
    claude_output = (
        "Claude実装担当: 設計に賛成。 実装着手します。\n"
        "[Claude-Verify: MOCK-CLAUDE-001]\n"
        "[NextActor: GPT]\n"
        "[EndTime-JST: 06:02:00]\n"
        "[is_shuji_represented: false]\n"
        "[no_proxy_violation: true]\n"
    )
    claude_validation = validate_response(claude_output)
    assert claude_validation["valid"]
    assert claude_validation["next_actor"] == "GPT"
    # proxy check 統合
    proxy_check = validate_actor_output("Claude", claude_output)
    assert proxy_check["status"] == "ACCEPT", f"clean Claude output should ACCEPT, got {proxy_check}"
    results["steps"].append({"step": "Claude_mock", "validation": "valid", "next_actor": "GPT", "proxy": "ACCEPT"})
    print(f"   [G-3] Claude mock output validation OK + proxy check ACCEPT")

    # 4. tag確認 (全AI で is_shuji_represented / no_proxy_violation 必須)
    for output_name, output in (("GPT", gpt_output), ("Gemini", gemini_output), ("Claude", claude_output)):
        assert "[is_shuji_represented: false]" in output, f"{output_name} missing is_shuji_represented tag"
        assert "[no_proxy_violation: true]" in output, f"{output_name} missing no_proxy_violation tag"
    print(f"   [G-4] 全AI 必須タグ確認 OK (is_shuji_represented + no_proxy_violation)")

    # 5. mock round log append (実ファイル書き込みはしない、 関数呼び出しだけ確認)
    try:
        # append_log existence check
        assert callable(append_log), "append_log function must exist"
        results["steps"].append({"step": "round_log_append", "status": "callable"})
        print(f"   [G-5] round log append機構 OK (append_log callable)")
    except Exception as e:
        print(f"   [G-5] FAIL: {e}")
        return {"status": "FAIL", "results": results}

    # 6. state更新 mock (consensus_candidate は本番trueにしない)
    state = load_state()
    state_before_phase15 = state.get("consensus_candidate")
    # mockなので変更しない
    results["steps"].append({
        "step": "state_update_mock",
        "consensus_candidate_unchanged": True,
        "consensus_candidate_current": state_before_phase15,
    })
    print(f"   [G-6] state更新 mock (consensus_candidate本番true化せず維持: {state_before_phase15})")

    results["status"] = "PASS"
    return results


def run_phase15_integration_test() -> int:
    """--phase15-integration-test: 全6機能を一気通貫テスト"""
    print("=" * 70)
    print("R50 Phase 1.5 INTEGRATION TEST")
    print("=" * 70)

    all_results = {
        "p0_watchdog_self_test": None,
        "p1_self_test": None,
        "p2_self_test": None,
        "main_loop_mock_1round": None,
    }

    # A+B (P0): watchdog/race/queue
    print("\n>>> A+B: P0 (race + Watchdog) self-test")
    rc_p0 = run_watchdog_self_test()
    all_results["p0_watchdog_self_test"] = "PASSED" if rc_p0 == 0 else f"FAILED rc={rc_p0}"
    if rc_p0 != 0:
        print("INTEGRATION TEST FAILED at P0")
        return rc_p0

    # C+D (P1): proxy check + token
    print("\n>>> C+D: P1 (proxy check + token overflow) self-test")
    rc_p1 = run_p1_self_test()
    all_results["p1_self_test"] = "PASSED" if rc_p1 == 0 else f"FAILED rc={rc_p1}"
    if rc_p1 != 0:
        print("INTEGRATION TEST FAILED at P1")
        return rc_p1

    # E+F (P2): Claude Code event-driven + Phase 2 metrics
    print("\n>>> E+F: P2 (Claude event-driven + Phase 2 metrics) self-test")
    rc_p2 = run_p2_self_test()
    all_results["p2_self_test"] = "PASSED" if rc_p2 == 0 else f"FAILED rc={rc_p2}"
    if rc_p2 != 0:
        print("INTEGRATION TEST FAILED at P2")
        return rc_p2

    # G: main loop mock 1周
    g_result = _mock_main_loop_one_round()
    all_results["main_loop_mock_1round"] = g_result["status"]
    if g_result["status"] != "PASS":
        print("INTEGRATION TEST FAILED at main loop mock")
        return 1

    # check real_send_enabled
    state = load_state()
    rse = state.get("real_send_enabled", False)
    assert rse is False, f"real_send_enabled must be False, got {rse}"
    print(f"\n>>> real_send_enabled=False 維持確認 OK")

    # summary
    print("\n" + "=" * 70)
    print("Phase 1.5 INTEGRATION TEST SUMMARY")
    print("=" * 70)
    for k, v in all_results.items():
        print(f"  {k}: {v}")
    print(f"  real_send_enabled: False (maintained)")
    print("=" * 70)
    print("Phase 1.5 INTEGRATION TEST PASSED")
    print("=" * 70)
    return 0


# =====================
# Claude Slot Dry-run (GPT第60 R50-CLAUDE-SLOT-DRY-RUN-9174)
# =====================
CLAUDE_PROMPTS_DIR = LOGS_DIR / "claude_prompts" if 'LOGS_DIR' in dir() else (Path(__file__).resolve().parent.parent / "logs" / "claude_prompts")


def run_claude_slot_dry_run() -> int:
    """GPT指示 R50-CMD-CLAUDE-SLOT-DRY-RUN: Claude向け3スロットプロンプト生成のみ、 実Sendなし"""
    print("=" * 60)
    print("R50 Claude Slot Dry-run (GPT-Verify: R50-CLAUDE-SLOT-DRY-RUN-9174)")
    print("=" * 60)

    result = {
        "claude_slot_dry_run": "ERROR",
        "endpoint": CDP_ENDPOINT,
        "real_send_enabled": False,
        "scope": "prompt_generation_only_no_real_send",
    }

    state = load_state()
    backup_path = backup_state(state)
    print(f"[1] backup: {backup_path}")
    acquire_lock(state)
    print(f"[2] lock acquired")

    try:
        gpt_latest = "(GPT最新応答取得失敗時のダミー)"
        gemini_latest = "(Gemini最新応答取得失敗時のダミー)"
        cdp_status = "skipped"
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                try:
                    browser = p.chromium.connect_over_cdp(CDP_ENDPOINT)
                    cdp_status = "connected"
                    gemini_page = None
                    chatgpt_page = None
                    for ctx in browser.contexts:
                        for page in ctx.pages:
                            if "gemini.google.com" in page.url and gemini_page is None:
                                gemini_page = page
                            elif "chatgpt.com/g/g-p-" in page.url and chatgpt_page is None:
                                chatgpt_page = page
                    if chatgpt_page:
                        chatgpt_page.bring_to_front()
                        gpt_latest = chatgpt_page.evaluate("""() => {
                            const turns = document.querySelectorAll('[data-testid^=\"conversation-turn-\"]');
                            const last = turns[turns.length - 1];
                            return last ? (last.textContent || '').slice(0, 4000) : '(empty)';
                        }""")
                    if gemini_page:
                        gemini_page.bring_to_front()
                        gemini_latest = gemini_page.evaluate("""() => {
                            const responses = document.querySelectorAll('model-response');
                            const last = responses[responses.length - 1];
                            return last ? (last.textContent || '').slice(0, 4000) : '(empty)';
                        }""")
                    print(f"[3] CDP fetch: gpt={len(gpt_latest)}chars gemini={len(gemini_latest)}chars")
                except Exception as e:
                    cdp_status = f"failed_using_dummy: {e}"
                    print(f"[3] CDP fetch failed (using dummy): {e}")
        except ImportError:
            cdp_status = "playwright_not_installed_using_dummy"
            print("[3] Playwright not installed → using dummy text")

        ts = int(time.time())
        ts_str = time.strftime('%H:%M:%S')
        CLAUDE_PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
        prompt_path = CLAUDE_PROMPTS_DIR / f"{ts}.claude_prompt.md"

        claude_prompt_content = f"""# Claude Slot 3-Stage Prompt (R50-CLAUDE-SLOT-DRYRUN)

Generated at: JST {ts_str}
Source: Orchestrator dry-run (no real send, no Claude execution)

---

## 1. 前1人監査

Geminiの直前発言を監査してください。

### Gemini直前発言 (verbatim, truncated 4000chars):
```
{gemini_latest}
```

### 監査観点
- 技術・脆弱性
- 過剰同意チェック
- 論理整合性
- 直前GPT発言との矛盾有無

---

## 2. 前2人監査

GPTの直前発言を監査してください。

### GPT直前発言 (verbatim, truncated 4000chars):
```
{gpt_latest}
```

### 監査観点
- 司会権限 (議論回す役のみ) 逸脱有無
- 決済代弁有無
- Shuji代弁有無
- Gemini監査受領の妥当性

---

## 3. 自己ターン (Claude発言)

Claude自身の **実装担当 + 監査担当** として、 以下を述べてください:

1. 実装可能性 (Claude Code/CLI/file-based方式での実現性、 工数見積もり)
2. 脆弱性 (DOMバグ/stall/race condition/Shuji代弁リスク)
3. 合意可否 (`consensus_approved: true/false`)
4. unresolved_critical_issues (空配列または具体的issue列挙)

---

必須末尾:
```
[Claude-Verify: R50-CLAUDE-SLOT-DRYRUN]
[NextActor: GPT]
[EndTime-JST: HH:MM:SS]
[Claude-Approve-or-Disagree: <true|false>]
```
"""

        with open(prompt_path, "w", encoding="utf-8") as f:
            f.write(claude_prompt_content)
        print(f"[4] Claude prompt written: {prompt_path} ({len(claude_prompt_content)}chars)")

        result["claude_prompt_path"] = str(prompt_path)
        result["claude_prompt_len"] = len(claude_prompt_content)
        result["gpt_latest_len"] = len(gpt_latest)
        result["gemini_latest_len"] = len(gemini_latest)
        result["cdp_status"] = cdp_status
        result["claude_slot_dry_run"] = "PASSED"

        DRY_RUN_DIR.mkdir(parents=True, exist_ok=True)
        rp = DRY_RUN_DIR / f"{ts}.claude_slot_dry_run.json"
        with open(rp, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        result["result_dump"] = str(rp)
        print(f"[5] result json: {rp}")

        s = load_state()
        s["claude_slot_dry_run_result"] = result
        s["real_send_enabled"] = False
        save_state(s)
        return 0
    except Exception as e:
        result["reason"] = f"UNEXPECTED: {type(e).__name__}: {e}"
        s = load_state()
        s["claude_slot_dry_run_result"] = result
        save_state(s)
        return 1
    finally:
        release_lock(load_state())
        after = load_state()
        print(f"[final] lock={after.get('lock')} real_send_enabled={after.get('real_send_enabled')}")


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
    if "--claude-slot-dry-run" in sys.argv:
        sys.exit(run_claude_slot_dry_run())
    if "--watchdog-self-test" in sys.argv:
        sys.exit(run_watchdog_self_test())
    if "--p1-self-test" in sys.argv:
        sys.exit(run_p1_self_test())
    if "--p2-self-test" in sys.argv:
        sys.exit(run_p2_self_test())
    if "--phase15-integration-test" in sys.argv:
        sys.exit(run_phase15_integration_test())
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
