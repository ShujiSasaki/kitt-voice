"""
R50 Round 1合意済 異常通知6条件 (Max Round撤回後の終了/通知条件)
- Shuji 15発目: 3者合意のみ終了 (Max Round制限なし)
- 通知6条件: 合意/決裂/Validator異常/HUMAN_REQUIRED/3回失敗/コスト時間停滞
"""
import json
import time
from pathlib import Path
from dataclasses import dataclass, asdict


REPO_ROOT = Path(__file__).resolve().parents[2]
LOGS_DIR = REPO_ROOT / "logs"
NOTIFICATION_LOG = LOGS_DIR / "abnormal_notifications.jsonl"


CONDITION_CONSENSUS_REACHED = 1
CONDITION_DEADLOCK = 2
CONDITION_VALIDATOR_ERROR = 3
CONDITION_HUMAN_REQUIRED = 4
CONDITION_TECHNICAL_3X = 5
CONDITION_COST_TIME_STALL = 6

CONDITION_LABELS = {
    1: "consensus_reached",
    2: "discussion_deadlock",
    3: "validator_error",
    4: "watchdog_human_required",
    5: "technical_error_3x",
    6: "cost_time_stall_limit",
}


@dataclass
class NotificationEvent:
    timestamp_jst: str
    condition_code: int
    condition_label: str
    detail: str
    severity: str
    requires_shuji_action: bool


COST_LIMIT_USD = 50.0
TIME_LIMIT_HOURS = 12.0
STALL_LIMIT_MINUTES = 30


def emit_notification(event: NotificationEvent) -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    with open(NOTIFICATION_LOG, 'a', encoding='utf-8') as f:
        f.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")


def check_consensus_reached(consensus_state: dict) -> NotificationEvent | None:
    if consensus_state.get("all_three_consent") is True:
        return NotificationEvent(
            timestamp_jst=_now_jst(),
            condition_code=CONDITION_CONSENSUS_REACHED,
            condition_label=CONDITION_LABELS[CONDITION_CONSENSUS_REACHED],
            detail="3者合意成立 - 終了条件達成",
            severity="info",
            requires_shuji_action=True,
        )
    return None


def check_deadlock(round_history: list, stall_rounds: int = 5) -> NotificationEvent | None:
    """同一論点で stall_rounds回 進展なしなら決裂判定"""
    if len(round_history) < stall_rounds:
        return None
    recent = round_history[-stall_rounds:]
    if len({r.get("unresolved_critical_issues_count", 0) for r in recent}) == 1:
        return NotificationEvent(
            timestamp_jst=_now_jst(),
            condition_code=CONDITION_DEADLOCK,
            condition_label=CONDITION_LABELS[CONDITION_DEADLOCK],
            detail=f"直近{stall_rounds}Round で unresolved issue count 変化なし",
            severity="warn",
            requires_shuji_action=True,
        )
    return None


def check_validator_error(validator_failures_count: int) -> NotificationEvent | None:
    if validator_failures_count > 0:
        return NotificationEvent(
            timestamp_jst=_now_jst(),
            condition_code=CONDITION_VALIDATOR_ERROR,
            condition_label=CONDITION_LABELS[CONDITION_VALIDATOR_ERROR],
            detail=f"Validator検証失敗 {validator_failures_count}件",
            severity="warn",
            requires_shuji_action=True,
        )
    return None


def check_human_required(watchdog_status: str) -> NotificationEvent | None:
    if watchdog_status == "HUMAN_REQUIRED":
        return NotificationEvent(
            timestamp_jst=_now_jst(),
            condition_code=CONDITION_HUMAN_REQUIRED,
            condition_label=CONDITION_LABELS[CONDITION_HUMAN_REQUIRED],
            detail="Watchdog HUMAN_REQUIRED発動 (400s+ stall)",
            severity="critical",
            requires_shuji_action=True,
        )
    return None


def check_technical_3x(error_log: list) -> NotificationEvent | None:
    """同じ technical error が 3回連続発生したら通知"""
    if len(error_log) < 3:
        return None
    recent_3 = error_log[-3:]
    if len({e.get("error_type", "") for e in recent_3}) == 1:
        return NotificationEvent(
            timestamp_jst=_now_jst(),
            condition_code=CONDITION_TECHNICAL_3X,
            condition_label=CONDITION_LABELS[CONDITION_TECHNICAL_3X],
            detail=f"同一エラー3回連続: {recent_3[-1].get('error_type', '?')}",
            severity="warn",
            requires_shuji_action=True,
        )
    return None


def check_cost_time_stall(metrics: dict) -> NotificationEvent | None:
    """コスト/時間/停滞上限超過チェック (Max Round撤回後の代替制限)"""
    violations = []
    if metrics.get("cumulative_cost_usd", 0) > COST_LIMIT_USD:
        violations.append(f"cost ${metrics['cumulative_cost_usd']:.2f} > ${COST_LIMIT_USD}")
    if metrics.get("elapsed_hours", 0) > TIME_LIMIT_HOURS:
        violations.append(f"time {metrics['elapsed_hours']:.1f}h > {TIME_LIMIT_HOURS}h")
    if metrics.get("stall_minutes", 0) > STALL_LIMIT_MINUTES:
        violations.append(f"stall {metrics['stall_minutes']}min > {STALL_LIMIT_MINUTES}min")
    if violations:
        return NotificationEvent(
            timestamp_jst=_now_jst(),
            condition_code=CONDITION_COST_TIME_STALL,
            condition_label=CONDITION_LABELS[CONDITION_COST_TIME_STALL],
            detail=f"コスト/時間/停滞 上限超過: {'; '.join(violations)}",
            severity="warn",
            requires_shuji_action=True,
        )
    return None


def evaluate_all_conditions(context: dict) -> list:
    """全6条件評価 - 発火した条件を返す"""
    events = []
    checkers = [
        (check_consensus_reached, context.get("consensus_state", {})),
        (check_deadlock, context.get("round_history", [])),
        (check_validator_error, context.get("validator_failures_count", 0)),
        (check_human_required, context.get("watchdog_status", "")),
        (check_technical_3x, context.get("error_log", [])),
        (check_cost_time_stall, context.get("metrics", {})),
    ]
    for fn, arg in checkers:
        ev = fn(arg)
        if ev:
            emit_notification(ev)
            events.append(ev)
    return events


def _now_jst() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S JST", time.localtime())


def self_test():
    passed = 0
    failed = 0

    ctx_consensus = {"consensus_state": {"all_three_consent": True}}
    events = evaluate_all_conditions(ctx_consensus)
    if any(e.condition_code == CONDITION_CONSENSUS_REACHED for e in events):
        passed += 1
        print("PASS: consensus_reached detected")
    else:
        failed += 1

    ctx_deadlock = {"round_history": [{"unresolved_critical_issues_count": 3}] * 6}
    events = evaluate_all_conditions(ctx_deadlock)
    if any(e.condition_code == CONDITION_DEADLOCK for e in events):
        passed += 1
        print("PASS: deadlock detected")
    else:
        failed += 1

    ctx_validator = {"validator_failures_count": 2}
    events = evaluate_all_conditions(ctx_validator)
    if any(e.condition_code == CONDITION_VALIDATOR_ERROR for e in events):
        passed += 1
        print("PASS: validator_error detected")
    else:
        failed += 1

    ctx_human = {"watchdog_status": "HUMAN_REQUIRED"}
    events = evaluate_all_conditions(ctx_human)
    if any(e.condition_code == CONDITION_HUMAN_REQUIRED for e in events):
        passed += 1
        print("PASS: human_required detected")
    else:
        failed += 1

    ctx_3x = {"error_log": [{"error_type": "RPCError"}] * 3}
    events = evaluate_all_conditions(ctx_3x)
    if any(e.condition_code == CONDITION_TECHNICAL_3X for e in events):
        passed += 1
        print("PASS: technical_3x detected")
    else:
        failed += 1

    ctx_cost = {"metrics": {"cumulative_cost_usd": 100.0, "elapsed_hours": 5, "stall_minutes": 10}}
    events = evaluate_all_conditions(ctx_cost)
    if any(e.condition_code == CONDITION_COST_TIME_STALL for e in events):
        passed += 1
        print("PASS: cost_limit detected")
    else:
        failed += 1

    print(f"\n=== SELF-TEST RESULT: {passed}/{passed+failed} PASSED ===")
    return failed == 0


if __name__ == "__main__":
    self_test()
