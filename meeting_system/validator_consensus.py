"""
validator_consensus — 合意成立判定の機械検証

3者合意 (loop2 R50-CONSENSUS-LOGIC-AND-UI-FEEDBACK):
- 最低 consensus_required_min_loops=2 巡を満たす場合のみ合意成立
- 直近完了巡で 3者全員 consensus_candidate=true
- loops_history に msg_id が揃っている
- Shuji新発言/Must Fix/最終案変更時は自動 is_consensus_established=false に戻す
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Tuple

from . import state_schema
from .state_schema import (
    DEFAULT_BASE, JST, SEQUENCE,
    read_state, write_state_atomic,
)


def record_actor_speech(
    room_id: str,
    actor: str,
    msg_id: str,
    consensus_candidate: bool,
    base: Path = DEFAULT_BASE,
    consensus_value: str | None = None,
) -> dict:
    """R59 Q3: consensus_value で 3値 (true/false/blocked/external_wait) を受け取れる。
    consensus_value未指定なら legacy bool consensus_candidate から true/false に変換。
    """
    state = read_state(room_id, base)

    # P1-① (2026-06-12 包括指示): validator等の非SEQUENCE actorは
    # 巡回カウンタ・判定記録に一切影響させない。
    # 旧実装は validator inject が total_loops を進め、空のcandsで
    # mark_consensus_if_established が合意成立を誤リセットする副作用があった
    # (完了報告injectのたびに合意済み部屋が再開される実害が複数回発生)。
    if actor not in SEQUENCE:
        state["current_actor"] = actor
        state["last_msg_id"] = msg_id
        state["last_msg_ts"] = datetime.now(JST).isoformat()
        write_state_atomic(room_id, state, base)
        return state

    if state["current_turn_in_loop"] == 0:
        state["total_loops"] += 1
        state["loops_history"].append({"loop": state["total_loops"]})

    cur_loop = state["total_loops"]
    loop_key = str(cur_loop)
    state["consensus_candidates_per_loop"].setdefault(loop_key, {})
    # R59 Q3: 3値保存 (legacy bool→strに正規化)
    if consensus_value is None:
        consensus_value = "true" if consensus_candidate else "false"
    state["consensus_candidates_per_loop"][loop_key][actor] = consensus_value

    if state["loops_history"]:
        state["loops_history"][-1][f"{actor}_msg_id"] = msg_id

    idx = SEQUENCE.index(actor)
    if idx == len(SEQUENCE) - 1:
        state["current_turn_in_loop"] = 0
        state["next_actor"] = "gpt"
    else:
        state["current_turn_in_loop"] = idx + 1
        state["next_actor"] = SEQUENCE[idx + 1]

    state["current_actor"] = actor
    state["last_msg_id"] = msg_id
    state["last_msg_ts"] = datetime.now(JST).isoformat()

    write_state_atomic(room_id, state, base)
    return state


def check_consensus_established(state: dict) -> Tuple[bool, str]:
    min_loops = state.get("consensus_required_min_loops", 2)
    total = state.get("total_loops", 0)
    in_turn = state.get("current_turn_in_loop", 0)
    completed = total if in_turn == 0 else total - 1

    if completed < min_loops:
        return (False, f"completed_loops={completed} < min_loops={min_loops}")

    last_key = str(completed)
    cands = state.get("consensus_candidates_per_loop", {}).get(last_key, {})
    for a in SEQUENCE:
        v = cands.get(a)
        # R59 Q3: 3値対応 (true/False/blocked/external_wait)
        if v is True or v == "true":
            continue
        # blocked / external_wait は「人間介入待ち」 で 合意未成立扱い
        if v in ("blocked", "external_wait"):
            return (False, f"loop {completed}: {a}={v} (人間介入待ち)")
        return (False, f"loop {completed}: {a}.consensus_candidate != true (got {v!r})")

    history = state.get("loops_history", [])
    if len(history) < completed:
        return (False, "loops_history insufficient")
    last_entry = history[completed - 1]
    for a in SEQUENCE:
        if not last_entry.get(f"{a}_msg_id"):
            return (False, f"loop {completed}: {a}_msg_id missing")

    return (True, f"loop {completed} 3者全員 consensus_candidate=true、 msg_id揃")


def mark_consensus_if_established(
    room_id: str, base: Path = DEFAULT_BASE,
) -> dict:
    state = read_state(room_id, base)
    established, reason = check_consensus_established(state)
    changed = False

    # R61 fix #6 (3者合意 4巡連続一致 2026-06-10 21:16):
    # 最新loopの3者判定が 全員 blocked / external_wait なら
    # state["status"] に該当値を書込み → relay_worker が auto-pause できる。
    # (パースは validator.py で済み、 status への永続化だけが欠落していた)
    cur_loop_key = str(state.get("total_loops", 0))
    cur_cands = state.get("consensus_candidates_per_loop", {}).get(cur_loop_key, {})
    wait_values = [
        v for a, v in cur_cands.items()
        if a in SEQUENCE and v in ("blocked", "external_wait")
    ]
    actors_voted = [a for a in cur_cands if a in SEQUENCE]
    if (len(actors_voted) == len(SEQUENCE)
            and len(wait_values) == len(SEQUENCE)
            and state.get("status") not in ("blocked", "external_wait")):
        # 多数値 (同数なら blocked優先 = より強い停止)
        new_status = ("blocked" if wait_values.count("blocked")
                      >= wait_values.count("external_wait") else "external_wait")
        state["status"] = new_status
        changed = True

    if established and not state.get("is_consensus_established"):
        state["is_consensus_established"] = True
        state["consensus_established_at"] = datetime.now(JST).isoformat()
        state["consensus_established_reason"] = reason
        state["consensus_established_loop"] = state.get("total_loops")
        state["status"] = "consensus_reached"
        # R64: 合意成立ごとに 合意まとめ を1回提示 (consensus_summary.py が消費)
        state["summary_pending"] = True
        state["summary_sent"] = False
        state["summary_sent_at"] = None
        changed = True
    elif not established and state.get("is_consensus_established"):
        state["is_consensus_established"] = False
        state["consensus_established_reason"] = f"reset: {reason}"
        if state.get("status") == "consensus_reached":
            state["status"] = "idle"
        changed = True
    if changed:
        write_state_atomic(room_id, state, base)
    return state


def reset_consensus_on_shuji_input(
    room_id: str, base: Path = DEFAULT_BASE,
) -> dict:
    """R59 bug fix: Shuji submit時に loop状態も完全reset (新議題扱い)。
    過去 timeline.jsonl は touch しない (改ざん禁止仕様)、
    state.json の loop/cands のみリセット。
    """
    state = read_state(room_id, base)
    changed = False
    if state.get("is_consensus_established"):
        state["is_consensus_established"] = False
        state["consensus_established_at"] = None
        state["consensus_established_loop"] = None
        state["consensus_established_reason"] = "reset: shuji_new_input"
        changed = True
    # R64: 新議題 → まとめフラグもリセット (次の合意で再発火)
    if state.get("summary_pending") or state.get("summary_sent"):
        state["summary_pending"] = False
        state["summary_sent"] = False
        state["summary_sent_at"] = None
        changed = True
    # R66: max_loops_reached も新submitで解除 (上限到達後の新指示で再開)
    if state.get("status") in ("consensus_reached", "blocked", "external_wait",
                               "max_loops_reached"):
        state["status"] = "idle"
        changed = True
    # 新議題として 巡回カウンタもリセット (R59 bug fix、 17:48 Shuji報告)
    if state.get("total_loops", 0) > 0:
        state["total_loops"] = 0
        state["current_turn_in_loop"] = 0
        state["next_actor"] = "gpt"
        state["consensus_candidates_per_loop"] = {}
        state["loops_history"] = []
        changed = True
    if changed:
        write_state_atomic(room_id, state, base)
    return state


def self_test() -> bool:
    import shutil
    import tempfile as _tempfile
    tmp_base = Path(_tempfile.mkdtemp(prefix="validator_consensus_test_"))
    try:
        state_schema.init_room("r1", base=tmp_base)

        record_actor_speech("r1", "gpt", "m1", True, base=tmp_base)
        record_actor_speech("r1", "gemini", "m2", True, base=tmp_base)
        record_actor_speech("r1", "claude", "m3", True, base=tmp_base)

        s = mark_consensus_if_established("r1", base=tmp_base)
        assert not s["is_consensus_established"], "1巡目でtrueになってはいけない"
        assert s["total_loops"] == 1

        record_actor_speech("r1", "gpt", "m4", True, base=tmp_base)
        record_actor_speech("r1", "gemini", "m5", True, base=tmp_base)
        record_actor_speech("r1", "claude", "m6", True, base=tmp_base)

        s2 = mark_consensus_if_established("r1", base=tmp_base)
        assert s2["is_consensus_established"], f"2巡目でtrueになるべき: {s2}"
        assert s2["consensus_established_loop"] == 2
        assert s2["status"] == "consensus_reached"

        reset_consensus_on_shuji_input("r1", base=tmp_base)
        s3 = state_schema.read_state("r1", base=tmp_base)
        assert not s3["is_consensus_established"], "Shuji発言でリセットされるべき"

        # P1-①: validator inject は loop/cands/合意状態に影響しない
        state_schema.init_room("r2", base=tmp_base)
        record_actor_speech("r2", "gpt", "n1", True, base=tmp_base)
        record_actor_speech("r2", "gemini", "n2", True, base=tmp_base)
        record_actor_speech("r2", "claude", "n3", True, base=tmp_base)
        record_actor_speech("r2", "gpt", "n4", True, base=tmp_base)
        record_actor_speech("r2", "gemini", "n5", True, base=tmp_base)
        record_actor_speech("r2", "claude", "n6", True, base=tmp_base)
        s4 = mark_consensus_if_established("r2", base=tmp_base)
        assert s4["is_consensus_established"], "前提: 2巡trueで成立"
        loops_before = s4["total_loops"]
        record_actor_speech("r2", "validator", "v1", False, base=tmp_base,
                            consensus_value="false")
        s5 = state_schema.read_state("r2", base=tmp_base)
        assert s5["total_loops"] == loops_before, "validatorでloopが進んではいけない"
        assert "validator" not in s5["consensus_candidates_per_loop"].get(
            str(loops_before), {}), "validatorがcandsに混入してはいけない"
        s6 = mark_consensus_if_established("r2", base=tmp_base)
        assert s6["is_consensus_established"], \
            "validator inject後も合意成立が維持されるべき (旧bugでは誤リセット)"
        assert s5["last_msg_ts"], "last_msg_tsは更新される (R67b Watchdog用)"

        print("PASS: validator_consensus self_test (P1-① validator非干渉含む)")
        return True
    finally:
        shutil.rmtree(tmp_base, ignore_errors=True)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    ok = self_test()
    raise SystemExit(0 if ok else 1)
