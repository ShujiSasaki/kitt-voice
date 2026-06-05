#!/usr/bin/env python3
"""
CLAUDE_AUTONOMOUS_WATCHDOG.py
============================
Shuji#13「Claude自動化」 解決D案 + Gemini第7応答指示+Gemini第8「Dual State主軸」 + Claude第4「過剰エンジニアリング取下げ」

物理制約 (Claude通常会話):
- 1ターン1呼び出し、 polling不可、 Bash sleep block
- ScheduleWakeup は /loop dynamic mode 専用、 通常会話 呼べない
- 本スクリプトは Shujiさんが `claude /loop --routine` で起動した時のみ有効

主軸 (Gemini第8指示 + Claude第4合意): Dual Button State シンプル判定
- Send Button = True (有効) かつ Stop/Regenerate Button = False (不在) → 完了
- 8項目化は 過剰エンジニアリング脆弱性として 取下げ済

使用法:
    python3 scripts/CLAUDE_AUTONOMOUS_WATCHDOG.py            # 1回チェック
    claude /loop --routine scripts/CLAUDE_AUTONOMOUS_WATCHDOG.py  # /loop連携 (将来)

依存: Python 3.11+ 標準ライブラリのみ
"""
import json
import ssl
import sys
import urllib.request
from typing import Optional

# macOS Python標準 SSL Cert問題回避 (production NG、 雛形のみ)
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

STATE_URL = "https://raw.githubusercontent.com/ShujiSasaki/kitt-voice/main/logs/state.json"
QUEUE_URL = "https://raw.githubusercontent.com/ShujiSasaki/kitt-voice/main/logs/queue.json"
ROUND_URL = "https://raw.githubusercontent.com/ShujiSasaki/kitt-voice/main/logs/rounds/round_50.md"


def fetch_json(url: str) -> dict:
    """GitHub Raw から JSON fetch。 失敗時 FETCH_ERROR ステータス返却 (Gemini第7指示)。"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "claude-watchdog/1.0"})
        with urllib.request.urlopen(req, timeout=5, context=_SSL_CTX) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"_fetch_error": str(e), "_status": "FETCH_ERROR"}


def fetch_text(url: str) -> Optional[str]:
    """GitHub Raw から テキスト fetch。 失敗時 None。"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "claude-watchdog/1.0"})
        with urllib.request.urlopen(req, timeout=5, context=_SSL_CTX) as r:
            return r.read().decode("utf-8")
    except Exception:
        return None


def extract_last_verify_token(round_md: str) -> Optional[str]:
    """議事録から最新Verify Token抽出 (3スロット形式 verbatim検証用)。"""
    import re
    patterns = [
        r"\[GPT-Verify:\s*([^\]]+)\]",
        r"\[Gemini-Verify:\s*([^\]]+)\]",
        r"\[Claude-Verify:\s*([^\]]+)\]",
        r"HMAC-SHA256\s+Verification\s+Token:\s*([0-9a-fA-F]{40,80})",
    ]
    last_match = None
    last_pos = -1
    for pat in patterns:
        for m in re.finditer(pat, round_md):
            if m.start() > last_pos:
                last_pos = m.start()
                last_match = m.group(1)
    return last_match


def main() -> int:
    state = fetch_json(STATE_URL)
    queue = fetch_json(QUEUE_URL)
    round_md = fetch_text(ROUND_URL)

    if state.get("_status") == "FETCH_ERROR":
        print(f"WATCHDOG: state.json FETCH_ERROR: {state['_fetch_error']}", file=sys.stderr)
        return 1
    if queue.get("_status") == "FETCH_ERROR":
        print(f"WATCHDOG: queue.json FETCH_ERROR: {queue['_fetch_error']}", file=sys.stderr)
        return 1

    print("=" * 60)
    print(f"Round: {state.get('current_round')}, "
          f"Subround: {state.get('current_subround')}, "
          f"Turn: {queue.get('current_turn', '?')}")
    print(f"Speaker order: {queue.get('fixed_order', 'GPT → Gemini → Claude')}")
    print(f"Next actor: {queue.get('next_actor', 'unknown')}")
    print(f"Termination: {queue.get('termination_status', 'in_progress')}")

    blocker = queue.get("blocker")
    if blocker:
        print(f"⚠️  BLOCKER: {blocker}")
    if queue.get("fetch_error"):
        print("⚠️  FETCH_ERROR: previous fetch failed, manual check required")

    pending = queue.get("pending_transmissions", [])
    if pending:
        print(f"\nPending transmissions ({len(pending)}):")
        for p in pending:
            print(f"  - {p.get('from', '?')} → {p.get('to', '?')}: {p.get('status', '?')}")

    if round_md:
        last_token = extract_last_verify_token(round_md)
        print(f"\nLast Verify Token: {last_token or 'NOT_FOUND'}")
        sections = round_md.count("\n## ")
        print(f"round_50.md sections: ~{sections}")

    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
