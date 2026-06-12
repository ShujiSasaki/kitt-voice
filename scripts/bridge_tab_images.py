#!/usr/bin/env python3
"""AIタブ内の生成画像を会議室へ転送する橋 (2026-06-13 Shuji要望)

背景: リレーはテキストのみスクレイプするため、ChatGPT/Geminiがタブ内で
生成した画像は部屋に届かない。本スクリプトはCDP経由で各タブの最新応答内の
画像をノードスクリーンショットとして回収し、data/attachments/{room}/ に保存
して timeline に添付メッセージを直接追記する (queue_io経由・サーバ無変更)。

usage: python3 scripts/bridge_tab_images.py <room_id> [gpt|gemini|both]
"""
import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from meeting_system import queue_io  # noqa: E402
from meeting_system.state_schema import (  # noqa: E402
    DEFAULT_BASE, JST, read_state, write_state_atomic,
)

from playwright.async_api import async_playwright  # noqa: E402

CDP = "http://127.0.0.1:9222"
MIN_DIM = 200  # これ未満の表示サイズの画像はアイコン類として無視
MAX_IMAGES_PER_TAB = 4

TAB_HINTS = {
    "gpt": "chatgpt.com",
    "gemini": "gemini.google.com",
}


async def grab_tab_images(actor: str, out_dir: Path) -> list[Path]:
    saved: list[Path] = []
    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(CDP)
        page = None
        for ctx in browser.contexts:
            for p in ctx.pages:
                if TAB_HINTS[actor] in (p.url or ""):
                    page = p
        if page is None:
            print(f"{actor}: タブが見つからない")
            return saved
        # 表示サイズが十分大きいimg要素のindexを後ろから収集
        idxs = await page.evaluate(
            """(minDim) => {
                const imgs = [...document.querySelectorAll('img')];
                const out = [];
                imgs.forEach((im, i) => {
                    const r = im.getBoundingClientRect ?
                        {w: im.width, h: im.height} : {w: 0, h: 0};
                    if (r.w >= minDim && r.h >= minDim) out.push(i);
                });
                return out;
            }""", MIN_DIM)
        if not idxs:
            print(f"{actor}: 対象サイズの画像なし")
            return saved
        targets = idxs[-MAX_IMAGES_PER_TAB:]
        loc = page.locator("img")
        seen_hashes = set()  # 同一画像がDOM上に複数ノードある場合の重複排除
        import hashlib
        for n, i in enumerate(targets, 1):
            try:
                el = loc.nth(i)
                await el.scroll_into_view_if_needed(timeout=5000)
                await asyncio.sleep(0.4)
                ts = datetime.now(JST).strftime("%Y%m%d_%H%M%S_%f")
                path = out_dir / f"{ts}_{actor}_{n}.png"
                await el.screenshot(path=str(path), timeout=10000)
                if path.exists() and path.stat().st_size > 5000:
                    h = hashlib.md5(path.read_bytes()).hexdigest()
                    if h in seen_hashes:
                        path.unlink(missing_ok=True)
                        print(f"  {actor} 画像{n}: 重複スキップ")
                        continue
                    seen_hashes.add(h)
                    saved.append(path)
                    print(f"  {actor} 画像{n}: {path.name} "
                          f"({path.stat().st_size//1024}KB)")
                else:
                    path.unlink(missing_ok=True)
            except Exception as e:
                print(f"  {actor} 画像{n}: 取得失敗 {e}")
        await browser.close()
    return saved


def inject_with_attachments(room_id: str, actor_label: str,
                            files: list[Path], base: Path) -> str:
    atts = []
    for p in files:
        atts.append({
            "url": f"/api/rooms/{room_id}/attachments/{p.name}",
            "filename": p.name,
            "content_type": "image/png",
            "size_bytes": p.stat().st_size,
        })
    body = (f"🖼 [事務Claude画像転送] {actor_label}タブ内の生成画像 "
            f"{len(files)}枚を回収して添付しました (リレーはテキストのみ"
            "転送のため、タブ内画像は事務Claudeが橋渡しします)")
    msg_id = f"imgbridge_{room_id}_{actor_label}_{int(time.time())}"
    queue_io.append_timeline({
        "room_id": room_id, "msg_id": msg_id, "actor": "validator",
        "body": body, "raw": body,
        "tags": {"system": "image_bridge"},
        "validator": {"pass": True, "items": ["image_bridge"]},
        "summary": f"{actor_label}の生成画像{len(files)}枚を添付",
        "attachments": atts,
    }, base=base)
    st = read_state(room_id, base)
    st["unread_count"] = int(st.get("unread_count", 0)) + 1
    st["last_msg_preview"] = f"validator: 🖼 {actor_label}の画像{len(files)}枚を添付"
    write_state_atomic(room_id, st, base)
    return msg_id


async def main():
    room = sys.argv[1] if len(sys.argv) > 1 else "btc_auto_trade"
    which = sys.argv[2] if len(sys.argv) > 2 else "both"
    actors = ["gpt", "gemini"] if which == "both" else [which]
    base = DEFAULT_BASE
    att_dir = base / "data" / "attachments" / room
    att_dir.mkdir(parents=True, exist_ok=True)
    for actor in actors:
        files = await grab_tab_images(actor, att_dir)
        if files:
            mid = inject_with_attachments(room, actor.upper(), files, base)
            print(f"{actor}: {len(files)}枚 inject済み ({mid})")
        else:
            print(f"{actor}: 転送対象なし")


if __name__ == "__main__":
    asyncio.run(main())
