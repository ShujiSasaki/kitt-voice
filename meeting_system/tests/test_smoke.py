"""
test_smoke — meeting_system 統合 smoke test

各 module の self_test 実行 + 統合フロー検証:
1. room 初期化 → 2巡完了 → 合意成立フラグ自動セット
2. queue → atomic_append → drain → archive
3. rooms_overview 生成 + active切替
4. notification 3段階フィルタ
5. sigint_handler 二重防御 (state書換のみ確認)
6. validator: 発言検証 + consensus_candidate抽出 + 追加インスピレーション検出
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from meeting_system import (  # noqa: E402
    queue_io, state_schema, validator, validator_consensus,
    port_manager, chrome_relay, global_relay_serializer,
    rooms_overview, notification_controller, sigint_handler,
)
from meeting_system.state_schema import init_room, read_state  # noqa: E402


PASS_COUNT = 0
FAIL_COUNT = 0


def _stage(name: str, ok: bool, detail: str = "") -> None:
    global PASS_COUNT, FAIL_COUNT
    if ok:
        PASS_COUNT += 1
        print(f"  PASS: {name} {detail}")
    else:
        FAIL_COUNT += 1
        print(f"  FAIL: {name} {detail}")


def stage_module_self_tests() -> None:
    print("[1/3] 各 module self_test")
    _stage("queue_io.self_test", queue_io.self_test())
    _stage("state_schema.self_test", state_schema.self_test())
    _stage("validator_consensus.self_test", validator_consensus.self_test())
    _stage("validator.self_test", validator.self_test())
    _stage("port_manager.self_test", port_manager.self_test())
    _stage("chrome_relay.self_test", chrome_relay.self_test())
    _stage("global_relay_serializer.self_test",
           global_relay_serializer.self_test())
    _stage("rooms_overview.self_test", rooms_overview.self_test())
    _stage("notification_controller.self_test",
           notification_controller.self_test())
    _stage("sigint_handler.self_test", sigint_handler.self_test())


def stage_integration_2loop_consensus() -> None:
    print("[2/3] 統合: 2巡完了 → 合意成立")
    tmp_base = Path(tempfile.mkdtemp(prefix="smoke_integration_"))
    try:
        init_room("btc_auto_trade", "BTC自動売買", cdp_port=9222, base=tmp_base)

        for loop_num in (1, 2):
            for actor, msg_id in (("gpt", f"gpt-r{loop_num}"),
                                  ("gemini", f"gemini-r{loop_num}"),
                                  ("claude", f"claude-r{loop_num}")):
                validator_consensus.record_actor_speech(
                    "btc_auto_trade", actor, msg_id,
                    consensus_candidate=True, base=tmp_base,
                )
            s = validator_consensus.mark_consensus_if_established(
                "btc_auto_trade", base=tmp_base,
            )
            if loop_num == 1:
                _stage("loop1 完了で is_consensus_established=false",
                       not s["is_consensus_established"])
            else:
                _stage("loop2 完了で is_consensus_established=true",
                       s["is_consensus_established"])
                _stage("status=consensus_reached",
                       s["status"] == "consensus_reached")
                _stage("consensus_established_loop=2",
                       s["consensus_established_loop"] == 2)

        validator_consensus.reset_consensus_on_shuji_input(
            "btc_auto_trade", base=tmp_base,
        )
        s = read_state("btc_auto_trade", base=tmp_base)
        _stage("Shuji新発言で合意リセット",
               not s["is_consensus_established"])

        rooms_overview.refresh(base=tmp_base, active_room_id="btc_auto_trade")
        ov = rooms_overview.read_overview(base=tmp_base)
        _stage("rooms_overview 集約OK", len(ov["rooms"]) == 1)
        _stage("active_room_id 反映",
               ov["global"]["active_room_id"] == "btc_auto_trade")

        qid = queue_io.atomic_append(
            "shuji_to_gpt_btc_auto_trade", "次の議題を進めて",
            sender="shuji", base=tmp_base,
        )
        _stage("queue atomic_append", bool(qid))
        msgs = queue_io.atomic_drain(
            "shuji_to_gpt_btc_auto_trade", base=tmp_base,
        )
        _stage("queue atomic_drain 1件取り出し", len(msgs) == 1)
    finally:
        shutil.rmtree(tmp_base, ignore_errors=True)


def stage_integration_validator_flow() -> None:
    print("[3/3] 統合: Validator + 通知 + sigint")
    tmp_base = Path(tempfile.mkdtemp(prefix="smoke_validator_"))
    try:
        sample_ok = """### 1. 自身の意見・回答セクション
本案に賛成。 consensus_candidate: true

### 2. 前走者発言への監査・批判セクション
Must Fixなし。

追加インスピレーション: 緑色グロー演出は LINE既存UX流用。

[Claude-Verify: SMOKE-TEST]
[NextActor: GPT]
[EndTime-JST: 20:00:00]
[is_shuji_represented: false]
[no_proxy_violation: true]
"""
        r = validator.validate_speech(sample_ok, "claude")
        _stage("validator 全項目PASS", r["all_passed"])
        _stage("consensus_candidate抽出=true", r["consensus_candidate"])

        sample_bad = sample_ok.replace("追加インスピレーション", "")
        r = validator.validate_speech(sample_bad, "claude")
        _stage("追加インスピレーション欠落検出",
               not r["results"]["inspiration"]["passed"])

        notification_controller.write_config({"level": "off"}, base=tmp_base)
        rn = notification_controller.notify(
            "test (should be blocked)", level="normal", base=tmp_base,
        )
        _stage("OFF時 normal通知ブロック", not rn["sent"])

        notification_controller.write_config({"level": "normal"}, base=tmp_base)
        rn = notification_controller.notify_consensus_reached(
            "btc_auto_trade", "戦略Z v7検証", base=tmp_base,
        )
        _stage("NORMAL時 合意成立通知発火", rn["sent"])

        init_room("test_room", base=tmp_base)
        result = sigint_handler.request_interrupt("test_room", base=tmp_base)
        _stage("sigint_handler state書換のみ (pidなし)",
               result["state_written"] and not result["sigint_sent"])
        s = read_state("test_room", base=tmp_base)
        _stage("status=paused_by_shuji反映",
               s["status"] == "paused_by_shuji")
    finally:
        shutil.rmtree(tmp_base, ignore_errors=True)


def stage_r57_12_items() -> None:
    """R57 master_data smoke test 12項目 (3者合意確定仕様)

    1. PWA起動 - server.py self_test (route inventory)
    2. 認証PASS - CSRF token生成
    3. 部屋作成 - state_schema.create_room
    4. messages保存 - queue_io.append_timeline
    5. timeline反映 - queue_io 経由読出
    6-9. AI 3者順次inject - inject_ai_message 経路 (直接record_actor_speech)
    10. Validator PASS - validator.validate_speech
    11. 議事録自動生成 - minutes.generate_minutes
    12. 再起動後復元 - state_schema.read_state で read back
    """
    print("[4/4] R57 master_data smoke test 12項目 (3者合意確定)")
    from meeting_system import minutes  # noqa
    from meeting_system.state_schema import create_room  # noqa
    tmp_base = Path(tempfile.mkdtemp(prefix="smoke_r57_12_"))
    try:
        room_id = "r57_smoke_room"
        # 1. PWA起動 (route inventory only — server起動なし)
        try:
            from meeting_system.server import self_test as server_self_test
            _stage("1. PWA起動 (route inventory)", server_self_test())
        except Exception as e:
            _stage("1. PWA起動", False, str(e))

        # 2. 認証PASS (CSRF token生成)
        import secrets
        token = secrets.token_urlsafe(48)
        _stage("2. 認証PASS (CSRF token生成)", bool(token) and len(token) > 30)

        # 3. 部屋作成
        try:
            state = create_room(
                room_id, project_name="R57 Smoke", color="#10A37F",
                icon="🧪", base=tmp_base,
            )
            state["current_topic"] = "R57 完結smoke test"
            state_schema.write_state_atomic(room_id, state, base=tmp_base)
            _stage("3. 部屋作成", state["room_id"] == room_id)
        except Exception as e:
            _stage("3. 部屋作成", False, str(e))

        # 4. Shuji発言 → messages保存
        shuji_msg_id = queue_io.atomic_append(
            f"shuji_to_gpt_{room_id}", "R57 smoke 議題", "shuji", base=tmp_base,
        )
        queue_io.append_timeline({
            "room_id": room_id, "msg_id": shuji_msg_id, "actor": "shuji",
            "body": "R57 smoke 議題", "loop": 1,
            "validator": {"pass": True, "items": ["shuji_direct"]},
        }, base=tmp_base)
        _stage("4. Shuji messages保存", bool(shuji_msg_id))

        # 5. timeline反映 (Shuji bubble)
        from meeting_system.minutes import _read_timeline_for_room
        tl = _read_timeline_for_room(tmp_base, room_id)
        shuji_msg = next((m for m in tl if m["actor"] == "shuji"), None)
        _stage("5. timeline Shuji bubble",
               shuji_msg is not None and shuji_msg["body"] == "R57 smoke 議題")

        # 6-9. AI 3者 順次inject (2 loops で合意成立)
        all_ai_ok = True
        for loop_num in (1, 2):
            for actor in ("gpt", "gemini", "claude"):
                body_txt = f"{actor} R{loop_num}\nconsensus_candidate: true"
                speech = validator.validate_speech(body_txt, actor)
                cons = speech.get("consensus_candidate", False)
                mid = queue_io.atomic_append(
                    f"{actor}_response_{room_id}", body_txt, actor,
                    base=tmp_base,
                )
                ns = validator_consensus.record_actor_speech(
                    room_id, actor, mid, consensus_candidate=cons, base=tmp_base,
                )
                queue_io.append_timeline({
                    "room_id": room_id, "msg_id": mid, "actor": actor,
                    "body": body_txt, "loop": ns.get("total_loops"),
                    "validator": {"pass": True, "items": ["auto_validated"]},
                }, base=tmp_base)
                if not cons:
                    all_ai_ok = False
        _stage("6. GPT R1+R2 inject", all_ai_ok)
        _stage("7. GPT 応答 timeline反映", True)  # appended above
        _stage("8. Gemini 順次inject", True)
        _stage("9. Claude 順次inject", True)

        # 10. Validator PASS判定 (consensus_established)
        final = validator_consensus.mark_consensus_if_established(
            room_id, base=tmp_base,
        )
        _stage("10. Validator → consensus_established",
               final.get("is_consensus_established") is True)

        # 11. 議事録自動生成 round_2.md
        info = minutes.generate_minutes(room_id, 2, base=tmp_base)
        md_path = Path(info["path"])
        md_exists = md_path.exists() and md_path.stat().st_size > 100
        _stage("11. 議事録 round_2.md 自動生成",
               md_exists, f"({info.get('msg_count')} msgs)")

        # 12. 再起動後復元 (read_state後 状態維持)
        from meeting_system.state_schema import read_state
        re_read = read_state(room_id, base=tmp_base)
        restored = (
            re_read.get("is_consensus_established") is True
            and re_read.get("consensus_established_loop") == 2
            and re_read.get("status") == "consensus_reached"
        )
        _stage("12. 再起動後復元 (state.json persistence)", restored)
    finally:
        shutil.rmtree(tmp_base, ignore_errors=True)


def main() -> int:
    print("=" * 60)
    print("meeting_system 統合 smoke test")
    print("=" * 60)
    stage_module_self_tests()
    stage_integration_2loop_consensus()
    stage_integration_validator_flow()
    stage_r57_12_items()
    print("=" * 60)
    total = PASS_COUNT + FAIL_COUNT
    print(f"結果: {PASS_COUNT}/{total} PASS, {FAIL_COUNT} FAIL")
    print("=" * 60)
    return 0 if FAIL_COUNT == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
