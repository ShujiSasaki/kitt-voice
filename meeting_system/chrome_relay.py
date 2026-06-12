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
            'button[data-testid="composer-send-button"], '
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


# タブ安定運用 (2026-06-12): 新規会話URL。
# claude は claude.ai/code 専用session (発言Claude) のため対象外 — 新規会話化するとsession喪失
NEW_CHAT_URLS = {
    "gpt": "https://chatgpt.com/",
    "gemini": "https://gemini.google.com/app",
}


async def find_tab(ctx, actor: str):
    matcher = TAB_MATCHERS[actor]
    for page in ctx.pages:
        try:
            url = page.url
        except Exception:
            continue
        if any(s in url for s in matcher["url_contains"]):
            return page
    # タブ自動復旧 (2026-06-12): gpt/gemini はタブが閉じられても新規作成して継続
    if actor in NEW_CHAT_URLS:
        logger.warning("%s タブ無し — 新規タブを自動作成して復旧", actor)
        page = await ctx.new_page()
        await page.goto(NEW_CHAT_URLS[actor], wait_until="domcontentloaded",
                        timeout=30_000)
        await asyncio.sleep(2.0)
        return page
    raise RuntimeError(
        f"{actor} タブが見つからない (URL照合失敗、 ログイン状態確認)"
    )


async def reset_conversation(cdp_port: int, actor: str) -> bool:
    """会話肥大の自動対策: gpt/gemini を新規会話へ navigate。

    プロンプトは毎ターン自己完結 (R58.2: 議題+直近発言を同梱) のため文脈損失なし。
    2026-06-12 実害: 2日分・全部屋を1会話に蓄積したChatGPTが生成4分超+
    古い応答の再取得 (重複inject) に陥った — 新規会話化で2-3秒応答に回復。
    """
    url = NEW_CHAT_URLS.get(actor)
    if not url:
        return False
    ctx = await attach_chrome(f"http://127.0.0.1:{cdp_port}")
    page = await find_tab(ctx, actor)
    await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
    await asyncio.sleep(3.0)
    # 検証は advisory (2026-06-12実測: locatorが「resolved to visible」でも
    # wait_forがtimeoutするplaywright癖があり、gotoは成功しているのに失敗扱いに
    # なってカウンタが残り毎ターン再試行する劣化ループが発生した)
    try:
        await page.locator(SELECTORS[actor]["input"]).first.wait_for(
            state="visible", timeout=10_000)
    except Exception:
        logger.warning("%s reset_conversation: composer可視検証はflake — goto成功とみなす", actor)
    return True


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
    """R61 fix #3+#4:
    - GPTの ProseMirror では fill() が text入らず → keyboard.insert_text 優先
    - keyboard events は 前面tabにのみ届く → bring_to_front 必須
    """
    # R61 fix #4: keyboard events を効かせるため tab前面化 (5秒timeout)
    try:
        await asyncio.wait_for(page.bring_to_front(), timeout=5.0)
    except Exception:
        pass
    sel = SELECTORS[actor]
    input_loc = page.locator(sel["input"]).first
    await input_loc.wait_for(state="visible", timeout=30_000)
    await input_loc.click()
    for chunk in _split_for_rate_limit(text, actor):
        # R61 fix #3: ProseMirror系 (GPT/Claude) は keyboard.insert_text を優先
        inserted = False
        try:
            await page.keyboard.insert_text(chunk)
            inserted = True
        except Exception:
            pass
        if not inserted:
            try:
                await input_loc.fill(chunk)
            except Exception:
                pass
        # 送信btn appear待ち (text入力後だから現れるはず)
        send_loc = page.locator(sel["send"]).first
        sent = False
        try:
            await send_loc.wait_for(state="visible", timeout=10_000)
            # btn disabled (空入力) チェック避け
            try:
                disabled = await send_loc.get_attribute("disabled")
            except Exception:
                disabled = None
            if disabled is not None:
                # disabled なら 別 click trigger試行
                await page.keyboard.press("End")
            await send_loc.click()
            sent = True
        except Exception:
            pass
        if not sent:
            # 2026-06-12: ChatGPT UI更新で send button selector不一致が発生
            # (GPT全ターン送信不能の実害)。composer上の Enter は送信として機能する
            # (実機検証済み) → keyboard送信fallback
            logger.warning("%s: send button不可視 — Enter送信fallback", actor)
            await input_loc.click()
            await page.keyboard.press("Enter")
        await asyncio.sleep(RATE_LIMIT_INTERVAL_SEC)


# R59.2: thinking mode で placeholder/短文を stable判定しない 閾値
MIN_RESPONSE_CHARS = 80
# R59.2: 一定経過で reload試行 (GPT Thinking が DOMにrenderingされない bug)
RELOAD_AFTER_SEC = 90.0


async def get_last_response_text(page, actor: str) -> str:
    """R62 fix #7: 送信前の最終応答 (baseline) を取得。 応答鮮度検知用。"""
    sel = SELECTORS[actor]
    try:
        loc = page.locator(sel["last_response"]).last
        return await loc.inner_text(timeout=3_000)
    except Exception:
        return ""


STOP_BUTTON_SELECTORS = (
    'button[aria-label="回答を停止"], '
    'button[aria-label="Stop"], '
    'button[data-testid="stop-button"], '
    'button[aria-label*="stop" i]'
)


async def _verify_generation_started(
    page, actor: str, baseline: str, check_sec: float = 20.0,
) -> bool:
    """R62 fix #8: 送信後に生成が実際に始まったか確認。

    生成開始の証拠 (どちらか):
    - 停止ボタンが可視 (生成中UI)
    - last_response テキストが baseline から変化

    20秒以内に確認できなければ False (送信click空振りの可能性)。
    """
    baseline_strip = (baseline or "").strip()
    elapsed = 0.0
    while elapsed < check_sec:
        await asyncio.sleep(2.0)
        elapsed += 2.0
        # 1. 停止ボタン可視 = 生成中
        try:
            stop = page.locator(STOP_BUTTON_SELECTORS).first
            if await stop.is_visible(timeout=1_000):
                return True
        except Exception:
            pass
        # 2. 応答テキスト変化
        try:
            cur = await get_last_response_text(page, actor)
            if cur.strip() and cur.strip() != baseline_strip:
                return True
        except Exception:
            pass
    return False


async def wait_and_extract(
    page,
    actor: str,
    stabilize_sec: float = 3.0,
    max_wait_sec: float = 240.0,  # R59.2: 180→240 (Thinking余裕)
    baseline_text: str = "",  # R62 fix #7: 送信前の旧応答 (同一なら未生成扱い)
) -> str:
    """R62 fix #7 (3者合意 2026-06-10 22:09):
    旧応答誤取得バグの根絶 — 送信前の baseline と同一テキストは
    「まだ新応答が生成されていない」 とみなし stable判定しない。
    (Gemini 2330chars×3回ループの真因: 安定テキスト=旧応答 を即回収していた)
    """
    import hashlib
    baseline_hash = hashlib.sha1(
        (baseline_text or "").strip().encode("utf-8")
    ).hexdigest() if baseline_text else None

    sel = SELECTORS[actor]
    loc = page.locator(sel["last_response"]).last
    prev = ""
    stable_since: Optional[float] = None
    elapsed = 0.0
    interval = 1.0
    reloaded = False
    while elapsed < max_wait_sec:
        await asyncio.sleep(interval)
        elapsed += interval
        try:
            cur = await loc.inner_text(timeout=5_000)
        except Exception:
            continue
        cur_strip = cur.strip()
        # R62 fix #7: baseline と同一 = 旧応答 → 未生成扱い (stable判定しない)
        if baseline_hash and cur_strip:
            cur_hash = hashlib.sha1(cur_strip.encode("utf-8")).hexdigest()
            if cur_hash == baseline_hash:
                prev = cur
                stable_since = None
                # 旧応答のまま90秒 → 新応答がDOMに来ない可能性 → reload
                if not reloaded and elapsed >= RELOAD_AFTER_SEC:
                    try:
                        await page.reload(wait_until="domcontentloaded", timeout=15_000)
                        await asyncio.sleep(3.0)
                        loc = page.locator(sel["last_response"]).last
                        reloaded = True
                    except Exception:
                        pass
                continue
        # R59.2: 短文 (Thinking / placeholder) は stable判定の対象にしない
        if cur == prev and cur_strip and len(cur_strip) >= MIN_RESPONSE_CHARS:
            if stable_since is None:
                stable_since = elapsed
            elif elapsed - stable_since >= stabilize_sec:
                return cur
        else:
            prev = cur
            stable_since = None
        # R59.2: 90秒経過しても短文のまま → reload (Thinking mode rendering bug対策)
        if (not reloaded and elapsed >= RELOAD_AFTER_SEC
                and len((prev or "").strip()) < MIN_RESPONSE_CHARS):
            try:
                await page.reload(wait_until="domcontentloaded", timeout=15_000)
                await asyncio.sleep(3.0)
                # reload後 locator再取得
                loc = page.locator(sel["last_response"]).last
                reloaded = True
                prev = ""
                stable_since = None
            except Exception:
                pass
    raise TimeoutError(f"{actor} 応答が {max_wait_sec}s 以内に安定せず (鮮度検知: baseline={'有' if baseline_hash else '無'})")


async def relay_turn(
    cdp_port: int, actor: str, prompt_text: str,
    enable_reload_retry: bool = True,
) -> str:
    """R60 ④: 失敗時 tab reload + 1回 retry (Shuji要請 2026-06-10)。

    各AIが「止まった」 (送信btn無し / 応答stale / locator timeout) に対し
    自動 reload試行で回復させる。
    """
    ctx = await attach_chrome(f"http://127.0.0.1:{cdp_port}")
    page = await find_tab(ctx, actor)
    # R62 fix #9: Geminiは送信前reload (複数session同期によるDOM stale対策、
    # Shuji報告「またgeminiで止まってる」 2026-06-10 23:14)
    if actor == "gemini":
        try:
            await page.reload(wait_until="domcontentloaded", timeout=15_000)
            await asyncio.sleep(3.0)
            page = await find_tab(ctx, actor)
        except Exception:
            pass
    # R62 fix #7: 送信前の旧応答を baseline として記録 (鮮度検知)
    baseline = await get_last_response_text(page, actor)
    try:
        await send_prompt(page, actor, prompt_text)
        # R62 fix #8: 送信後20秒以内に生成開始を確認 (Shuji報告: Geminiターンで進まない)
        # 生成開始の証拠: stop btn可視 or 応答テキストがbaselineから変化
        started = await _verify_generation_started(page, actor, baseline)
        if not started:
            # 送信click空振りの可能性 → 1回だけ即再送
            await send_prompt(page, actor, prompt_text)
        return await wait_and_extract(page, actor, baseline_text=baseline)
    except Exception as e:
        if not enable_reload_retry:
            raise
        # 失敗 → reload + 1回 retry
        last_err = e
        try:
            # 「停止ボタン」 押しを最初に試す (Gemini hang対策)
            for stop_sel in (
                'button[aria-label="回答を停止"]',
                'button[aria-label="Stop"]',
                'button[data-testid="stop-button"]',
            ):
                try:
                    btn = page.locator(stop_sel).first
                    await btn.wait_for(state="visible", timeout=2_000)
                    await btn.click()
                    await asyncio.sleep(2.0)
                    break
                except Exception:
                    continue
            # tab reload
            await page.reload(wait_until="domcontentloaded", timeout=20_000)
            await asyncio.sleep(4.0)
            # find_tab再取得 (reloadでpageオブジェクト同じだがlocator再構築のため)
            page = await find_tab(ctx, actor)
            # R62 fix #7: retry時も baseline再取得 (reload後の最新旧応答)
            baseline2 = await get_last_response_text(page, actor)
            await send_prompt(page, actor, prompt_text)
            return await wait_and_extract(page, actor, baseline_text=baseline2)
        except Exception as e2:
            raise type(last_err)(
                f"{actor} 1st_fail={last_err} | reload_retry_fail={e2}"
            ) from e2


# ===== 画像自動転送 (2026-06-13 Shuji指示「自動で画像がルームに表示されるようにして」) =====
# リレーはテキストのみ転送のため、AIがタブ内で生成した画像は部屋に届かなかった。
# src URLとピクセルhashの二重管理で新出画像のみをノードスクショ回収する。
# (Geminiは毎ターンreloadでblob: srcが変わるため、src不一致でもピクセルhashで再添付を防ぐ)
_seen_image_srcs: dict[str, set] = {}
_seen_image_pixhash: dict[str, set] = {}

IMG_MIN_DIM = 200          # これ未満はアイコン類として無視
IMG_SCAN_LAST_N = 6        # 走査対象 = 直近の大型画像N個
IMG_MAX_PER_TURN = 4


async def capture_new_images(
    cdp_port: int, actor: str, out_dir, prime_only: bool = False,
) -> list:
    """タブ内の新出大型画像をPNG保存して Path リストを返す。

    prime_only=True は既存画像を既知化するだけ (worker起動時の再添付防止)。
    """
    import hashlib
    from datetime import datetime as _dt
    from pathlib import Path as _P

    ctx = await attach_chrome(f"http://127.0.0.1:{cdp_port}")
    page = await find_tab(ctx, actor)
    metas = await page.evaluate(
        """(minDim) => [...document.querySelectorAll('img')]
            .map((im, i) => ({i: i, src: im.currentSrc || im.src || '',
                              w: im.width, h: im.height}))
            .filter(m => m.w >= minDim && m.h >= minDim && m.src)""",
        IMG_MIN_DIM)
    seen_src = _seen_image_srcs.setdefault(actor, set())
    seen_pix = _seen_image_pixhash.setdefault(actor, set())
    saved: list = []
    loc = page.locator("img")
    targets = metas[-IMG_SCAN_LAST_N:]
    for m in targets:
        if m["src"] in seen_src:
            continue
        if len(saved) >= IMG_MAX_PER_TURN:
            break
        try:
            el = loc.nth(m["i"])
            await el.scroll_into_view_if_needed(timeout=5000)
            await asyncio.sleep(0.3)
            data = await el.screenshot(timeout=10000)
        except Exception:
            continue
        seen_src.add(m["src"])
        if not data or len(data) < 5000:
            continue
        ph = hashlib.md5(data).hexdigest()
        if ph in seen_pix:
            continue  # reload等でsrcが変わっただけの既知画像
        seen_pix.add(ph)
        if prime_only or out_dir is None:
            continue
        ts = _dt.now().strftime("%Y%m%d_%H%M%S_%f")
        p = _P(out_dir) / f"{ts}_{actor}_auto.png"
        p.write_bytes(data)
        saved.append(p)
    return saved


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
