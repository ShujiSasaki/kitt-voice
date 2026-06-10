"""
chrome_relay — Playwright connect_over_cdp + 3タブ動的探索 + Rate Limit対策

3者合意 (前々議題 R50-CHROME-ALTERNATIVE):
- connect_over_cdp(http://127.0.0.1:{port})
- 3タブ動的探索 (aria-label/data-testid/role 優先、 固定XPath回避)
- 無課金Gemini Rate Limit対策 (recent_log_diff のみ送信、 ~30,000文字超過時split)
- 各actor間 2秒インターバル
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

TAB_MATCHERS = {
    "gpt":    {"url_contains": ("chatgpt.com", "chat.openai.com")},
    "gemini": {"url_contains": ("gemini.google.com",)},
    "claude": {"url_contains": ("claude.ai",)},
}

SELECTORS = {
    "gpt": {
        "input": (
            'div[contenteditable="true"]#prompt-textarea, '
            'textarea#prompt-textarea, '
            'div.ProseMirror[contenteditable="true"]'
        ),
        "send": (
            'button[data-testid="send-button"], '
            'button[aria-label*="Send"], '
            'button[aria-label*="送信"]'
        ),
        "last_response": (
            'div[data-message-author-role="assistant"]:last-of-type'
        ),
    },
    "gemini": {
        "input": (
            'rich-textarea div[contenteditable="true"], '
            'div.ql-editor[contenteditable="true"]'
        ),
        "send": (
            'button[aria-label="プロンプトを送信"], '
            'button[aria-label="Send message"], '
            'button.send-button-container button'
        ),
        "last_response": (
            'message-content:last-of-type, '
            'div.model-response-text:last-of-type'
        ),
    },
    "claude": {
        "input": (
            'div.tiptap.ProseMirror[contenteditable="true"], '
            'div[contenteditable="true"].ProseMirror, '
            'div[contenteditable="true"]'
        ),
        "send": (
            'button[aria-label="Send Message"], '
            'button[aria-label*="送信"], '
            'button[aria-label*="Send"]'
        ),
        # R58 Must Fix G: claude.ai/code session (Claude Code) は data-is-streaming等を持たない
        # → markdownクラス last要素 / streaming無効fallback / message-content等を順に試す
        "last_response": (
            'div[data-is-streaming="false"]:last-of-type, '
            'div.font-claude-message:last-of-type, '
            'div[class*="markdown"]:last-of-type, '
            'article:last-of-type'
        ),
    },
}

RATE_LIMIT_INTERVAL_SEC = 2.0
GEMINI_FREE_MAX_CHARS = 30_000


async def attach_chrome(cdp_endpoint: str):
    from playwright.async_api import async_playwright
    pw = await async_playwright().start()
    browser = await pw.chromium.connect_over_cdp(cdp_endpoint)
    if not browser.contexts:
        raise RuntimeError("Chromeにcontextがない")
    return browser.contexts[0]


async def find_tab(ctx, actor: str):
    matcher = TAB_MATCHERS[actor]
    for page in ctx.pages:
        try:
            url = page.url
        except Exception:
            continue
        if any(s in url for s in matcher["url_contains"]):
            return page
    raise RuntimeError(
        f"{actor} タブが見つからない (URL照合失敗、 ログイン状態確認)"
    )


def _split_for_rate_limit(
    text: str, actor: str, max_chars: int = GEMINI_FREE_MAX_CHARS
) -> list[str]:
    if actor != "gemini" or len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    cur = ""
    for line in text.splitlines(keepends=True):
        if len(line) > max_chars:
            if cur:
                chunks.append(cur)
                cur = ""
            for i in range(0, len(line), max_chars):
                chunks.append(line[i:i + max_chars])
            continue
        if len(cur) + len(line) > max_chars and cur:
            chunks.append(cur)
            cur = line
        else:
            cur += line
    if cur:
        chunks.append(cur)
    return chunks


async def send_prompt(page, actor: str, text: str) -> None:
    sel = SELECTORS[actor]
    input_loc = page.locator(sel["input"]).first
    await input_loc.wait_for(state="visible", timeout=30_000)
    await input_loc.click()
    for chunk in _split_for_rate_limit(text, actor):
        try:
            await input_loc.fill(chunk)
        except Exception:
            await page.keyboard.insert_text(chunk)
        send_loc = page.locator(sel["send"]).first
        await send_loc.wait_for(state="visible", timeout=10_000)
        await send_loc.click()
        await asyncio.sleep(RATE_LIMIT_INTERVAL_SEC)


async def wait_and_extract(
    page,
    actor: str,
    stabilize_sec: float = 3.0,
    max_wait_sec: float = 180.0,
) -> str:
    sel = SELECTORS[actor]
    loc = page.locator(sel["last_response"]).last
    prev = ""
    stable_since: Optional[float] = None
    elapsed = 0.0
    interval = 1.0
    while elapsed < max_wait_sec:
        await asyncio.sleep(interval)
        elapsed += interval
        try:
            cur = await loc.inner_text(timeout=5_000)
        except Exception:
            continue
        if cur == prev and cur.strip():
            if stable_since is None:
                stable_since = elapsed
            elif elapsed - stable_since >= stabilize_sec:
                return cur
        else:
            prev = cur
            stable_since = None
    raise TimeoutError(f"{actor} 応答が {max_wait_sec}s 以内に安定せず")


async def relay_turn(
    cdp_port: int, actor: str, prompt_text: str
) -> str:
    ctx = await attach_chrome(f"http://127.0.0.1:{cdp_port}")
    page = await find_tab(ctx, actor)
    await send_prompt(page, actor, prompt_text)
    return await wait_and_extract(page, actor)


def self_test() -> bool:
    sample = "A" * 35000
    chunks = _split_for_rate_limit(sample, "gemini")
    assert len(chunks) >= 2, f"split should produce >=2 chunks: {len(chunks)}"
    assert all(len(c) <= GEMINI_FREE_MAX_CHARS for c in chunks)

    chunks_gpt = _split_for_rate_limit(sample, "gpt")
    assert len(chunks_gpt) == 1, "GPT/Claudeは分割しない"

    assert "url_contains" in TAB_MATCHERS["gpt"]
    assert "input" in SELECTORS["gemini"]
    assert "send" in SELECTORS["claude"]

    print("PASS: chrome_relay self_test (offline checks)")
    return True


if __name__ == "__main__":
    ok = self_test()
    raise SystemExit(0 if ok else 1)
