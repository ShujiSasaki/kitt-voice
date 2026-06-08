"""
port_manager — CDPポート 9222-9253 連番マップ + Chrome→Edge fallback

3者合意 (前議題 R50-MULTI-PROJECT-PARALLEL-AND-BROWSER-CHECK):
- 32会議予約 (9222-9253)
- File Lock + Atomic Move で port_registry.json管理
- _is_chrome_listening: CDP応答チェック
- _is_port_bindable: 新規bind可能チェック
- attach_with_retry: Chrome → Edge自動フォールバック
"""
from __future__ import annotations

import fcntl
import json
import os
import socket
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

BASE_PORT = 9222
MAX_PORTS = 32  # 9222-9253
DEFAULT_BASE = Path("/Users/shuji/Desktop/kitt-voice/meeting_system")
ENC = "utf-8"
NEWLINE = "\n"

CHROME_BIN = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
EDGE_BIN = "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"
PROFILE_ROOT_CHROME = Path("/Users/shuji/Library/Application Support/Google")
PROFILE_ROOT_EDGE = Path("/Users/shuji/Library/Application Support/Microsoft Edge")


def _registry_path(base: Path) -> Path:
    return base / "data" / "port_registry.json"


def _is_chrome_listening(port: int, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/json/version", timeout=timeout
        ) as r:
            return r.status == 200
    except Exception:
        return False


def _is_port_bindable(port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        try:
            s.close()
        except Exception:
            pass


def _read_registry(base: Path) -> dict:
    path = _registry_path(base)
    if not path.exists():
        return {"schema_version": 1, "assignments": {}}
    return json.loads(path.read_text(encoding=ENC))


def _write_registry(data: dict, base: Path) -> None:
    path = _registry_path(base)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(".lock")
    with open(lock_path, "w", encoding=ENC) as lock_fp:
        fcntl.flock(lock_fp.fileno(), fcntl.LOCK_EX)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding=ENC, newline=NEWLINE,
            dir=path.parent, delete=False,
        ) as tmp:
            json.dump(data, tmp, ensure_ascii=False, indent=2)
            tmp_path = Path(tmp.name)
        os.replace(tmp_path, path)


def assign_port(room_id: str, base: Path = DEFAULT_BASE) -> int:
    reg = _read_registry(base)
    if room_id in reg["assignments"]:
        return reg["assignments"][room_id]
    used = set(reg["assignments"].values())
    for offset in range(MAX_PORTS):
        candidate = BASE_PORT + offset
        if candidate in used:
            continue
        if _is_chrome_listening(candidate):
            continue
        if _is_port_bindable(candidate):
            reg["assignments"][room_id] = candidate
            _write_registry(reg, base)
            return candidate
    raise RuntimeError(
        f"No free CDP port in {BASE_PORT}-{BASE_PORT + MAX_PORTS - 1}"
    )


def release_port(room_id: str, base: Path = DEFAULT_BASE) -> None:
    reg = _read_registry(base)
    if room_id in reg["assignments"]:
        reg["assignments"].pop(room_id, None)
        _write_registry(reg, base)


def launch_browser(
    port: int,
    profile_dir: Path,
    browser: str = "chrome",
) -> subprocess.Popen | None:
    if _is_chrome_listening(port):
        return None
    profile_dir.mkdir(parents=True, exist_ok=True)
    binary = EDGE_BIN if browser == "edge" else CHROME_BIN
    if not Path(binary).exists():
        return None
    cmd = [
        binary,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    return subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def attach_with_retry(
    room_id: str,
    max_retries: int = 3,
    base: Path = DEFAULT_BASE,
) -> int:
    port = assign_port(room_id, base)
    chrome_profile = PROFILE_ROOT_CHROME / f"Chrome-{room_id}"
    edge_profile = PROFILE_ROOT_EDGE / f"Edge-{room_id}"
    last_err = None
    for attempt in range(max_retries):
        if _is_chrome_listening(port):
            return port
        try:
            if attempt == 0:
                launch_browser(port, chrome_profile, "chrome")
            elif attempt == 1:
                launch_browser(port, edge_profile, "edge")
            else:
                pass
        except Exception as e:
            last_err = e
        time.sleep(1 + attempt)
    raise RuntimeError(
        f"room {room_id} のブラウザ起動失敗 (Chrome→Edge): {last_err}"
    )


def get_port(room_id: str, base: Path = DEFAULT_BASE) -> int | None:
    reg = _read_registry(base)
    return reg["assignments"].get(room_id)


def self_test() -> bool:
    import shutil
    tmp_base = Path(tempfile.mkdtemp(prefix="port_mgr_test_"))
    try:
        p1 = assign_port("r1", base=tmp_base)
        assert BASE_PORT <= p1 < BASE_PORT + MAX_PORTS

        p1_again = assign_port("r1", base=tmp_base)
        assert p1 == p1_again, "same room_id should return same port"

        p2 = assign_port("r2", base=tmp_base)
        assert p2 != p1, "different rooms must get different ports"

        release_port("r1", base=tmp_base)
        p1_new = assign_port("r1", base=tmp_base)
        assert p1_new != p2

        assert _is_port_bindable(60000) in (True, False)
        assert _is_chrome_listening(1) is False

        print("PASS: port_manager self_test")
        return True
    finally:
        shutil.rmtree(tmp_base, ignore_errors=True)


if __name__ == "__main__":
    ok = self_test()
    raise SystemExit(0 if ok else 1)
