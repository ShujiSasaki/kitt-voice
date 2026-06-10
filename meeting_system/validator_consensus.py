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

    if actor in SEQUENCE:
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
    if established and not state.get("is_consensus_established"):
        state["is_consensus_established"] = True
        state["consensus_established_at"] = datetime.now(JST).isoformat()
        state["consensus_established_reason"] = reason
        state["consensus_established_loop"] = state.get("total_loops")
        state["status"] = "consensus_reached"
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
    state = read_state(room_id, base)
    if state.get("is_consensus_established"):
        state["is_consensus_established"] = False
        state["consensus_established_reason"] = "reset: shuji_new_input"
        state["status"] = "idle"
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

        print("PASS: validator_consensus self_test")
        return True
    finally:
        shutil.rmtree(tmp_base, ignore_errors=True)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    ok = self_test()
    raise SystemExit(0 if ok else 1)
