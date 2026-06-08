"""
sigint_handler — Shujiさん割込 二重防御

3者合意 (前々議題 R50-PLAN-B-SYSTEM-DETAIL):
- state.json アトミック書換 (status=paused_by_shuji, next_actor=shuji)
- SIGINT送信 (orchestratorプロセスへ)
- どちらか片方が失敗してもShujiさん介入が反映される
"""
from __future__ import annotations

import os
import signal
import sys
from datetime import datetime
from pathlib import Path

from . import state_schema
from .state_schema import DEFAULT_BASE, JST, read_state, write_state_atomic

PID_FILE_NAME = "orchestrator.pid"


class ShujiInterrupt(KeyboardInterrupt):
    """Shujiさん割込専用例外、 通常Ctrl+Cと区別"""


def _pid_path(base: Path) -> Path:
    return base / "data" / PID_FILE_NAME


def write_orchestrator_pid(base: Path = DEFAULT_BASE) -> None:
    path = _pid_path(base)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(os.getpid()), encoding="utf-8")


def read_orchestrator_pid(base: Path = DEFAULT_BASE) -> int | None:
    path = _pid_path(base)
    if not path.exists():
        return None
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return None


def request_interrupt(room_id: str, base: Path = DEFAULT_BASE) -> dict:
    state = read_state(room_id, base)
    state["status"] = "paused_by_shuji"
    state["next_actor"] = "shuji"
    state["interrupt_ts"] = datetime.now(JST).isoformat()
    write_state_atomic(room_id, state, base)

    pid = read_orchestrator_pid(base)
    result = {"state_written": True, "sigint_sent": False, "pid": pid}
    if pid:
        try:
            os.kill(pid, signal.SIGINT)
            result["sigint_sent"] = True
        except ProcessLookupError:
            result["sigint_error"] = "process_not_found"
        except PermissionError as e:
            result["sigint_error"] = f"permission: {e}"
    return result


def install_handlers(base: Path = DEFAULT_BASE) -> None:
    write_orchestrator_pid(base)

    def _handler(signum, frame):
        try:
            paused_rooms = []
            projects = base / "projects"
            if projects.exists():
                for proj_dir in projects.iterdir():
                    if not (proj_dir / "state.json").exists():
                        continue
                    s = read_state(proj_dir.name, base)
                    if s.get("status") == "paused_by_shuji":
                        paused_rooms.append(proj_dir.name)
            if paused_rooms:
                raise ShujiInterrupt(f"shuji_interrupt: {paused_rooms}")
        except ShujiInterrupt:
            raise
        except Exception:
            pass
        sys.exit(130)

    signal.signal(signal.SIGINT, _handler)
    signal.signal(signal.SIGTERM, _handler)


def self_test() -> bool:
    import shutil
    import tempfile as _tempfile
    tmp_base = Path(_tempfile.mkdtemp(prefix="sigint_test_"))
    try:
        state_schema.init_room("r1", base=tmp_base)

        write_orchestrator_pid(base=tmp_base)
        pid = read_orchestrator_pid(base=tmp_base)
        assert pid == os.getpid(), f"pid mismatch: {pid} vs {os.getpid()}"
        _pid_path(tmp_base).unlink()

        result = request_interrupt("r1", base=tmp_base)
        assert result["state_written"]
        assert result["pid"] is None, "no pid → no SIGINT (state書換のみ)"
        assert not result["sigint_sent"]
        s = read_state("r1", base=tmp_base)
        assert s["status"] == "paused_by_shuji"
        assert s["next_actor"] == "shuji"
        assert s["interrupt_ts"]

        print("PASS: sigint_handler self_test")
        return True
    finally:
        shutil.rmtree(tmp_base, ignore_errors=True)


if __name__ == "__main__":
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).parent.parent))
    ok = self_test()
    raise SystemExit(0 if ok else 1)
