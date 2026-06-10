"""
health_check_tabs — R57 Phase D: Chrome 3者tab健全性チェック

依存 (Phase 1既存12モジュール流用):
- meeting_system.chrome_relay (CDP接続 + tab探索)

実行:
    python3 scripts/health_check_tabs.py --cdp-port 9222
    python3 scripts/health_check_tabs.py --cdp-port 9222 --json

CDP接続不可なら exit 2、 tab足りないなら exit 1、 全 OK で exit 0。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from meeting_system import chrome_relay  # noqa: E402

REQUIRED_ACTORS = ["gpt", "gemini", "claude"]


async def check(cdp_port: int) -> dict:
    endpoint = f"http://127.0.0.1:{cdp_port}"
    result: dict = {
        "cdp_endpoint": endpoint,
        "cdp_attached": False,
        "tabs": {},
        "all_present": False,
    }
    try:
        ctx = await chrome_relay.attach_chrome(endpoint)
    except Exception as e:
        result["error"] = f"cdp_attach_failed: {e}"
        return result
    result["cdp_attached"] = True
    for actor in REQUIRED_ACTORS:
        try:
            page = await chrome_relay.find_tab(ctx, actor)
            url = page.url
            try:
                title = await page.title()
            except Exception:
                title = ""
            result["tabs"][actor] = {
                "found": True, "url": url, "title": title[:80],
            }
        except Exception as e:
            result["tabs"][actor] = {"found": False, "error": str(e)}
    result["all_present"] = all(
        v.get("found") for v in result["tabs"].values()
    )
    return result


def main() -> int:
    p = argparse.ArgumentParser(description="R57 health_check_tabs (Phase D)")
    p.add_argument("--cdp-port", type=int, default=9222)
    p.add_argument("--json", action="store_true",
                   help="JSON出力 (人間向けpretty出力をskip)")
    args = p.parse_args()
    try:
        result = asyncio.run(check(args.cdp_port))
    except KeyboardInterrupt:
        return 130
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if not result.get("cdp_attached"):
            print(f"❌ CDP接続失敗: {result.get('error')}")
            print(f"   起動例: chrome --remote-debugging-port={args.cdp_port}")
            return 2
        print(f"✅ CDP attached: {result['cdp_endpoint']}")
        for actor, info in result["tabs"].items():
            if info.get("found"):
                print(f"  ✅ {actor:8s} {info['url'][:100]}")
            else:
                print(f"  ❌ {actor:8s} not found ({info.get('error', '')[:80]})")
        if result["all_present"]:
            print("✅ all 3 actors present")
            return 0
        print("⚠️  not all actors present")
        return 1
    if not result.get("cdp_attached"):
        return 2
    return 0 if result["all_present"] else 1


def self_test() -> bool:
    """構造のみ検証 (CDP接続なし)"""
    assert REQUIRED_ACTORS == ["gpt", "gemini", "claude"]
    # check() は async + CDP necessary、 ここでは構造確認のみ
    print("PASS: health_check_tabs self_test (structure)")
    return True


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        raise SystemExit(0 if self_test() else 1)
    raise SystemExit(main())
