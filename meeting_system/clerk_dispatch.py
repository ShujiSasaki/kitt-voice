"""
clerk_dispatch — 会議の依頼を事務Claudeへ自動ディスパッチ (2026-06-12 Shuji指示)

「btcルームから作業依頼あります。自動的に依頼が飛ぶか、事務claudeに依頼する
ボタンを作成してください」への実装。

仕組み (月額0円・外部公開なし・ローカルファイルキューのみ):
1. 自動: relay_workerが部屋の収束 (consensus_reached / external_wait) を検知した
   とき、直近発言から「事務Claudeへの依頼」ブロックを抽出して
   data/clerk_requests/pending/ に書き出し + Mac通知。
2. 手動: PWAの「事務Claudeへ依頼」ボタン → POST /api/rooms/{id}/clerk_dispatch
   → 同じ抽出を実行 (見つからなければ直近発言全文をフォールバック添付)。
3. 受領: 事務Claude (Claude Codeセッション) が pending/ を巡回し、
   実行後 done/ へ移動して部屋へ成果を再inject。

重複防止: 依頼本文のsha1先頭12桁をファイル名に含め、pending/done両方に
同hashがあればスキップ。
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import time
from datetime import datetime
from pathlib import Path

from .state_schema import DEFAULT_BASE, JST

ENC = "utf-8"

REQUEST_MARKERS = (
    "【事務Claudeへの依頼文】",
    "事務Claudeへの依頼:",
    "事務Claudeへの依頼：",
    "■ 事務Claudeへの依頼",
    "事務Claudeへの最終確定発注書",
    "事務Claudeへ発注",
    "事務Claudeへの発注",
    "事務Claudeへの修正指示",
    "事務Claudeに依頼",
)
SECTION_STOPS = ("2. 前走者", "3. consensus", "4. ", "5. ", "■ ")
MAX_REQUEST_CHARS = 2400
LOOKBACK_MSGS = 12


def _hash(text: str) -> str:
    return hashlib.sha1(text.encode(ENC)).hexdigest()[:12]


import re

PWA_SUMMARY_RE = re.compile(r"<pwa_summary>.*?</pwa_summary>", re.DOTALL)


def extract_clerk_request(bodies: list[str]) -> str:
    """発言本文のリストから依頼ブロックを抽出 (最長候補を採用)

    pwa_summary内は除外 (2026-06-12: 「事務Claudeに依頼を貼るか決めて」という
    Shuji向け質問の断片を依頼として誤発射した事故への対処)。
    1行だけの候補も依頼文として成立しないため捨てる。
    """
    best = ""
    for b in bodies:
        if not b:
            continue
        b = PWA_SUMMARY_RE.sub("", b)
        idx = -1
        for marker in REQUEST_MARKERS:
            idx = b.find(marker)
            if idx >= 0:
                break
        if idx < 0:
            continue
        block_lines = [b[idx:].splitlines()[0]]  # マーカー行も含める (何の依頼か明示)
        blank_streak = 0
        for ln in b[idx:].splitlines()[1:]:
            s = ln.strip()
            if s.startswith(SECTION_STOPS):
                break
            if not s:
                blank_streak += 1
                if blank_streak >= 3:
                    break
            else:
                blank_streak = 0
            block_lines.append(ln)
        candidate = "\n".join(block_lines).strip()[:MAX_REQUEST_CHARS]
        # 1行だけ (マーカー行のみ) は依頼として成立しない断片 → 捨てる
        if len([ln for ln in candidate.splitlines() if ln.strip()]) < 2:
            continue
        if len(candidate) > len(best):
            best = candidate
    return best


def _recent_actor_bodies(base: Path, room_id: str,
                         lookback: int = LOOKBACK_MSGS,
                         loop: int | None = None) -> list[str]:
    """現ラウンド (最後のShuji送信より後) の発言のみ走査。

    2026-06-13 fix: loop番号はラウンド毎に1から振り直されるため、loop一致だけ
    では過去ラウンドの同loop発言を拾い、処理済み依頼が再発射されていた。
    「最後のshuji発言より後」を境界とし、その中でloop一致を適用する。
    """
    path = base / "data" / "timeline.jsonl"
    if not path.exists():
        return []
    room_msgs = []
    for line in path.read_text(encoding=ENC).splitlines():
        if not line.strip():
            continue
        try:
            m = json.loads(line)
        except json.JSONDecodeError:
            continue
        if m.get("room_id") == room_id:
            room_msgs.append(m)
    last_shuji = max((i for i, m in enumerate(room_msgs)
                      if m.get("actor") == "shuji"), default=-1)
    bodies = []
    for m in room_msgs[last_shuji + 1:]:
        if m.get("actor") not in ("gpt", "gemini", "claude"):
            continue
        if loop is not None and m.get("loop") != loop:
            continue
        bodies.append(m.get("body") or "")
    return bodies[-lookback:]


def pending_dir(base: Path = DEFAULT_BASE) -> Path:
    return base / "data" / "clerk_requests" / "pending"


def done_dir(base: Path = DEFAULT_BASE) -> Path:
    return base / "data" / "clerk_requests" / "done"


def _already_dispatched(base: Path, room_id: str, h: str) -> bool:
    for d in (pending_dir(base), done_dir(base)):
        if d.exists() and list(d.glob(f"*_{room_id}_{h}.md")):
            return True
    return False


def write_pending(room_id: str, text: str, base: Path = DEFAULT_BASE,
                  source: str = "auto") -> Path | None:
    """依頼をpendingキューへ書き出し。重複ならNone"""
    text = (text or "").strip()
    if not text:
        return None
    h = _hash(text)
    if _already_dispatched(base, room_id, h):
        return None
    d = pending_dir(base)
    d.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(JST).strftime("%Y%m%d_%H%M%S")
    path = d / f"{ts}_{room_id}_{h}.md"
    header = (f"---\nroom: {room_id}\nsource: {source}\n"
              f"created: {datetime.now(JST).isoformat()}\nhash: {h}\n---\n\n")
    path.write_text(header + text + "\n", encoding=ENC)
    return path


def notify_mac(title: str, body: str) -> None:
    """Mac通知 (失敗しても本処理は止めない)"""
    try:
        subprocess.run(
            ["osascript", "-e",
             f'display notification "{body[:120]}" with title "{title}" '
             f'sound name "Glass"'],
            timeout=5, capture_output=True)
    except Exception:
        pass


def dispatch_for_room(room_id: str, base: Path = DEFAULT_BASE,
                      source: str = "auto",
                      fallback_full_text: bool = False,
                      loop: int | None = None) -> dict:
    """部屋の直近発言から依頼を抽出してキューへ。

    loop: 収束した巡の番号 (autoディスパッチ時はこの巡のみ走査)
    Returns: {"dispatched": bool, "path": str|None, "preview": str,
              "reason": str}
    """
    bodies = _recent_actor_bodies(base, room_id, loop=loop)
    req = extract_clerk_request(bodies)
    reason = "marker"
    if not req and fallback_full_text and bodies:
        # ボタン押下時: マーカー無しでも直近発言全文を依頼として運ぶ
        req = bodies[-1].strip()[:MAX_REQUEST_CHARS]
        reason = "fallback_last_msg"
    if not req:
        return {"dispatched": False, "path": None, "preview": "",
                "reason": "no_request_found"}
    path = write_pending(room_id, req, base, source=source)
    if path is None:
        return {"dispatched": False, "path": None,
                "preview": req[:100], "reason": "duplicate"}
    notify_mac("事務Claudeへの依頼",
               f"[{room_id}] {req.splitlines()[0][:80]}")
    return {"dispatched": True, "path": str(path),
            "preview": req[:200], "reason": reason}


def self_test() -> bool:
    import shutil
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="clerk_dispatch_test_"))
    try:
        # 1. 抽出: マーカー行含む、セクション境界で停止
        body = ("1. 意見\n■ 事務Claudeへ発注済みの修正仕様（AI3者完全合意）\n"
                "行動・解釈のAI抽出化\nFRの補完\n\n2. 前走者発言への監査\n含めない")
        req = extract_clerk_request([body])
        assert "修正仕様" in req and "FRの補完" in req, f"抽出失敗: {req}"
        assert "含めない" not in req
        # pwa_summary内のマーカーは無視 (Shuji向け質問の誤発射防止)
        noise = ("考察\n<pwa_summary>(A)事務Claudeに依頼を貼るか(B)私がやるか"
                 "決めてください</pwa_summary>\n続き")
        assert extract_clerk_request([noise]) == "", "pwa_summary除外失敗"
        # マーカー行のみの断片も依頼にしない
        assert extract_clerk_request(["事務Claudeに依頼します。"]) == ""
        # 2. timeline からの抽出 + 書き出し
        tl = tmp / "data" / "timeline.jsonl"
        tl.parent.mkdir(parents=True)
        recs = [
            {"room_id": "r1", "actor": "shuji", "body": "依頼して"},
            {"room_id": "r1", "actor": "gemini", "body": body},
            {"room_id": "r2", "actor": "gpt", "body": "別部屋のマーカーなし発言"},
        ]
        tl.write_text("\n".join(json.dumps(r, ensure_ascii=False)
                                for r in recs), encoding=ENC)
        r = dispatch_for_room("r1", base=tmp)
        assert r["dispatched"] and r["reason"] == "marker", r
        p = Path(r["path"])
        assert p.exists() and "room: r1" in p.read_text(encoding=ENC)
        # 3. 重複防止
        r2 = dispatch_for_room("r1", base=tmp)
        assert not r2["dispatched"] and r2["reason"] == "duplicate", r2
        # 4. マーカー無し部屋: autoは見送り、ボタンはfallback
        r3 = dispatch_for_room("r2", base=tmp)
        assert not r3["dispatched"] and r3["reason"] == "no_request_found"
        r4 = dispatch_for_room("r2", base=tmp, source="button",
                               fallback_full_text=True)
        assert r4["dispatched"] and r4["reason"] == "fallback_last_msg", r4
        # 5. done移動後も重複防止が効く
        done = done_dir(tmp)
        done.mkdir(parents=True, exist_ok=True)
        p.rename(done / p.name)
        r5 = dispatch_for_room("r1", base=tmp)
        assert not r5["dispatched"] and r5["reason"] == "duplicate", r5
        # 6. 現ラウンド境界: 新しいshuji発言より前の旧依頼は拾わない
        with open(tl, "a", encoding=ENC) as fp:
            for rec in [
                {"room_id": "r3", "actor": "gpt",
                 "body": "■ 事務Claudeへの依頼\n旧ラウンドの依頼です\n2行目"},
                {"room_id": "r3", "actor": "shuji", "body": "新しい議題"},
                {"room_id": "r3", "actor": "gpt", "body": "マーカーのない新発言"},
            ]:
                fp.write("\n" + json.dumps(rec, ensure_ascii=False))
        r6 = dispatch_for_room("r3", base=tmp)
        assert not r6["dispatched"] and r6["reason"] == "no_request_found", \
            f"旧ラウンド依頼の再発射: {r6}"
        print("PASS: clerk_dispatch self_test (抽出/書出/重複防止/fallback/done/ラウンド境界)")
        return True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    import sys
    if "--self-test" in sys.argv:
        raise SystemExit(0 if self_test() else 1)
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print("usage: python3 -m meeting_system.clerk_dispatch <room_id> [--button]")
        raise SystemExit(1)
    result = dispatch_for_room(
        args[0], source="button" if "--button" in sys.argv else "auto",
        fallback_full_text="--button" in sys.argv)
    print(json.dumps(result, ensure_ascii=False))
