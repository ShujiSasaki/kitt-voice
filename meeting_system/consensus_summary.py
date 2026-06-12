"""
consensus_summary — R64: 合意成立時の自動「合意まとめ」提示

3者合意 (2026-06-11 13:55 R64):
- トリガー: 合意成立 (is_consensus_established false→true) で summary_pending=true
- 重複防止: summary_sent=false のときだけ1回実行、出力後フラグ反転
- 生成: 直近true巡の3者発言から固定フォーマット (機械抽出、月額0円)
- 提示: validator actorで timeline inject + PWA表示 + 議事録保存
- 固定フォーマット: 結論 / 決まったこと / 残っていること / 次にやること / Shujiさんの判断要否

CLI (手動再生成・E2E用):
    python3 -m meeting_system.consensus_summary <room_id> [--force]
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

from . import queue_io
from .state_schema import (
    DEFAULT_BASE, JST, SEQUENCE,
    read_state, write_state_atomic,
)

ENC = "utf-8"

REMAINING_KEYWORDS = (
    "実装待ち", "実測待ち", "外部確認", "保留", "残:", "残）", "残って",
    "未実装", "未取得", "提出待ち",
)
NEXT_KEYWORDS = (
    "次にやること", "次アクション", "実装依頼", "事務Claudeが実装",
    "事務Claudeの実装", "次の議題", "4点セット",
)
JUDGMENT_KEYWORDS = ("Shujiさんの判断", "判断が必要", "判断待ち")


def _read_timeline_for_room(base: Path, room_id: str) -> list[dict]:
    path = base / "data" / "timeline.jsonl"
    if not path.exists():
        return []
    msgs = []
    for line in path.read_text(encoding=ENC).splitlines():
        if not line.strip():
            continue
        try:
            m = json.loads(line)
        except json.JSONDecodeError:
            continue
        if m.get("room_id") == room_id:
            msgs.append(m)
    return msgs


# P1-③ (2026-06-12 包括指示): 抽出ノイズ除去 — 見出し行/タグ/フォーマット定義行を除外
NOISE_SUBSTRINGS = (
    "<pwa_summary", "</pwa_summary", "フォーマット", "ヘッダー",
    "consensus_candidate", "Verify token", "[Room:", "[Validator-Verify",
    "セクションで応答", "末尾token",
)
SECTION_HEADINGS = (
    "結論", "決まったこと", "残っていること", "次にやること",
    "Shujiさんの判断要否", "Shujiさんの判断が必要か", "次アクション", "【次アクション】",
)


def _extract_lines(bodies: list[str], keywords: tuple, limit: int = 5) -> list[str]:
    out: list[str] = []
    for b in bodies:
        for ln in b.splitlines():
            s = ln.strip().lstrip("-・*>").strip()
            if not s or len(s) > 140:
                continue
            # 見出しそのもの・メタ行はノイズ
            if s in SECTION_HEADINGS or s.strip("【】■ ") in SECTION_HEADINGS:
                continue
            if any(n in s for n in NOISE_SUBSTRINGS):
                continue
            # キーワードの羅列だけの行 (例: 「結論 / 決まったこと / ...」) もノイズ
            if s.count("/") >= 3 and len(s) < 80:
                continue
            if any(k in s for k in keywords) and s not in out:
                out.append(s)
    return out[:limit]


def build_summary_body(state: dict, loop_msgs: dict[str, dict]) -> str:
    """loop_msgs: {actor: timeline record} (直近true巡の3者発言)"""
    topic = state.get("current_topic") or state.get("topic_title") or state.get("room_id", "")
    loop_n = state.get("consensus_established_loop") or state.get("total_loops", 0)
    est_at = (state.get("consensus_established_at") or "")[:16].replace("T", " ")
    bodies = [(loop_msgs.get(a) or {}).get("body") or "" for a in SEQUENCE]

    # 結論 = 最終発言者 (claude優先) の pwa_summary
    conclusion = ""
    for a in reversed(SEQUENCE):
        s = (loop_msgs.get(a) or {}).get("summary")
        if s:
            conclusion = s
            break
    if not conclusion:
        conclusion = f"{topic} — 3者合意成立"

    decided = []
    label = {"gpt": "GPT", "gemini": "Gemini", "claude": "発言Claude"}
    for a in SEQUENCE:
        s = (loop_msgs.get(a) or {}).get("summary")
        if s:
            decided.append(f"- {label[a]}: {s}")
    if not decided:
        decided = ["- (各AIの要約なし — 証跡▼を参照)"]

    remaining = _extract_lines(bodies, REMAINING_KEYWORDS)
    next_actions = _extract_lines(bodies, NEXT_KEYWORDS)
    judgment_lines = _extract_lines(bodies, JUDGMENT_KEYWORDS, limit=3)
    all_text = "\n".join(bodies)
    if "判断不要" in all_text and not judgment_lines:
        judgment = "今の判断不要"
    elif judgment_lines:
        judgment = "\n".join(f"- {ln}" for ln in judgment_lines)
    else:
        judgment = "今の判断不要 (自動判定: 判断要求の記載なし)"

    lines = [
        f"📋 [合意まとめ] {topic}",
        f"(3者true×{loop_n}巡で合意成立 {est_at})",
        "",
        "■ 結論",
        conclusion,
        "",
        "■ 決まったこと",
        *decided,
        "",
        "■ 残っていること",
        *([f"- {ln}" for ln in remaining] or ["- なし (自動抽出: 該当なし)"]),
        "",
        "■ 次にやること",
        *([f"- {ln}" for ln in next_actions] or ["- 特になし"]),
        "",
        "■ Shujiさんの判断要否",
        judgment,
        "",
        "[Validator-Verify: R64-CONSENSUS-SUMMARY]",
    ]
    return "\n".join(lines)


def generate_and_inject(
    room_id: str, base: Path = DEFAULT_BASE, force: bool = False,
) -> dict | None:
    """summary_pending かつ 未送信なら 合意まとめを生成して timeline + 議事録に出力"""
    state = read_state(room_id, base)
    if not force:
        if not state.get("summary_pending"):
            return None
        if state.get("summary_sent"):
            return None

    loop_n = state.get("consensus_established_loop") or state.get("total_loops", 0)
    history = state.get("loops_history") or []
    entry = {}
    if 0 < loop_n <= len(history):
        entry = history[loop_n - 1]
    elif history:
        entry = history[-1]
    wanted_ids = {entry.get(f"{a}_msg_id"): a for a in SEQUENCE if entry.get(f"{a}_msg_id")}

    msgs = _read_timeline_for_room(base, room_id)
    loop_msgs: dict[str, dict] = {}
    for m in msgs:
        a = wanted_ids.get(m.get("msg_id"))
        if a:
            loop_msgs[a] = m
    # fallback: msg_idで見つからなければ 各actorの最後の発言
    for a in SEQUENCE:
        if a not in loop_msgs:
            last = next((m for m in reversed(msgs) if m.get("actor") == a), None)
            if last:
                loop_msgs[a] = last

    body = build_summary_body(state, loop_msgs)
    msg_id = f"summary_{room_id}_{int(time.time())}"
    topic = state.get("current_topic") or state.get("topic_title") or room_id
    record = {
        "room_id": room_id,
        "msg_id": msg_id,
        "actor": "validator",
        "body": body,
        "raw": body,
        "tags": {"system": "consensus_summary"},
        "validator": {"pass": True, "items": ["consensus_summary"]},
        "loop": loop_n,
        "summary": f"📋 合意まとめ: {topic}",
        "consensus_value": "true",
    }
    queue_io.append_timeline(record, base=base)

    # 議事録保存
    out_path = (base / "data" / "projects" / room_id / "minutes"
                / f"consensus_summary_loop{loop_n}.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(body + "\n", encoding=ENC)

    # フラグ反転 + unread+1 (PWA新着)
    st = read_state(room_id, base)
    st["summary_pending"] = False
    st["summary_sent"] = True
    st["summary_sent_at"] = datetime.now(JST).isoformat()
    st["unread_count"] = int(st.get("unread_count", 0)) + 1
    write_state_atomic(room_id, st, base)

    return {"msg_id": msg_id, "minutes_path": str(out_path), "loop": loop_n}


def self_test() -> bool:
    import shutil
    import tempfile
    from . import state_schema as _ss
    tmp = Path(tempfile.mkdtemp(prefix="consensus_summary_test_"))
    try:
        room = "r1"
        st = _ss.default_state(room)
        st["current_topic"] = "テスト議題X"
        st["total_loops"] = 2
        st["consensus_established_loop"] = 2
        st["consensus_established_at"] = "2026-06-11T13:55:29+09:00"
        st["is_consensus_established"] = True
        st["summary_pending"] = True
        st["summary_sent"] = False
        st["loops_history"] = [
            {"loop": 1},
            {"loop": 2, "gpt_msg_id": "m_g", "gemini_msg_id": "m_m", "claude_msg_id": "m_c"},
        ]
        _ss.write_state_atomic(room, st, tmp)
        for mid, actor, summ, body in [
            ("m_g", "gpt", "GPT要約です",
             "本文\n実装待ちはAです\nconsensus_candidate: true\n"
             "固定フォーマット: 結論 / 決まったこと / 残っていること / 次にやること\n"
             "■ 残っていること\n<pwa_summary>実装待ちのZ</pwa_summary>"),
            ("m_m", "gemini", "Gemini要約です", "本文\n判断不要です"),
            ("m_c", "claude", "Claude要約です", "本文\n次にやること: 事務Claudeが実装する"),
        ]:
            queue_io.append_timeline({
                "room_id": room, "msg_id": mid, "actor": actor,
                "body": body, "summary": summ, "loop": 2,
                "validator": {"pass": True, "items": ["t"]},
            }, base=tmp)

        r = generate_and_inject(room, base=tmp)
        assert r and r["msg_id"].startswith("summary_r1_"), f"inject失敗: {r}"
        # timeline に validator record が追加されたか
        msgs = _read_timeline_for_room(tmp, room)
        last = msgs[-1]
        assert last["actor"] == "validator"
        assert "📋 [合意まとめ] テスト議題X" in last["body"]
        assert "■ 結論" in last["body"] and "Claude要約です" in last["body"]
        assert "GPT要約です" in last["body"]
        assert "実装待ちはAです" in last["body"]  # 残っていること抽出
        assert "事務Claudeが実装する" in last["body"]  # 次にやること抽出
        # P1-③: ノイズ除外 — 見出し行/タグ/フォーマット定義行は出力されない
        assert "固定フォーマット" not in last["body"], "フォーマット定義行が混入"
        assert "<pwa_summary>実装待ちのZ" not in last["body"], "pwa_summaryタグ行が混入"
        body_lines = last["body"].splitlines()
        assert "- 残っていること" not in body_lines, "見出しそのものが混入"
        # 議事録ファイル
        assert Path(r["minutes_path"]).exists()
        # フラグ反転
        st2 = _ss.read_state(room, tmp)
        assert st2["summary_sent"] is True and st2["summary_pending"] is False
        assert st2["summary_sent_at"]
        # 重複防止: 2回目は None
        assert generate_and_inject(room, base=tmp) is None
        print("PASS: consensus_summary self_test (生成/抽出/フラグ/重複防止)")
        return True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    import sys
    if "--self-test" in sys.argv:
        raise SystemExit(0 if self_test() else 1)
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print("usage: python3 -m meeting_system.consensus_summary <room_id> [--force]")
        raise SystemExit(1)
    result = generate_and_inject(args[0], force="--force" in sys.argv)
    print(json.dumps(result, ensure_ascii=False))
