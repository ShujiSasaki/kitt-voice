"""
notification_controller — 通知 3段階 (OFF/NORMAL/STRICT)

3者合意 (前々議題 R50-PLAN-B-SYSTEM-DETAIL):
- Mac osascript デスクトップ通知 (0円)
- Slack/Discord Webhook (0円、 環境変数 SLACK_WEBHOOK_URL/DISCORD_WEBHOOK_URL)
- LINE Notify 不採用 (2025年3月終了済、 CLAUDE.md記載)
- notifications.json で通知レベルリアルタイム反映 (Watchdog or SSE経由 polling)
"""
from __future__ import annotations

import fcntl
import json
import os
import subprocess
import tempfile
import urllib.request
from pathlib import Path
from typing import Optional

DEFAULT_BASE = Path("/Users/shuji/Desktop/kitt-voice/meeting_system")
ENC = "utf-8"
NEWLINE = "\n"

LEVELS = {"off": 0, "normal": 1, "strict": 2}


def _notifications_path(base: Path) -> Path:
    return base / "data" / "notifications.json"


def read_config(base: Path = DEFAULT_BASE) -> dict:
    path = _notifications_path(base)
    if not path.exists():
        return {"level": "normal"}
    return json.loads(path.read_text(encoding=ENC))


def write_config(cfg: dict, base: Path = DEFAULT_BASE) -> None:
    path = _notifications_path(base)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(".lock")
    with open(lock_path, "w", encoding=ENC) as lock_fp:
        fcntl.flock(lock_fp.fileno(), fcntl.LOCK_EX)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding=ENC, newline=NEWLINE,
            dir=path.parent, delete=False,
        ) as tmp:
            json.dump(cfg, tmp, ensure_ascii=False, indent=2)
            tmp_path = Path(tmp.name)
        os.replace(tmp_path, path)


def _mac_notify(message: str, title: str = "ぐるぐる3者会議") -> bool:
    safe_msg = message.replace('"', "'").replace("\\", "")[:200]
    safe_title = title.replace('"', "'").replace("\\", "")[:50]
    try:
        subprocess.run(
            ["osascript", "-e",
             f'display notification "{safe_msg}" with title "{safe_title}"'],
            check=False, timeout=5,
        )
        return True
    except Exception:
        return False


def _webhook_notify(webhook_url: str, message: str) -> bool:
    try:
        if "discord.com" in webhook_url:
            payload = {"content": message[:1900]}
        else:
            payload = {"text": message[:1900]}
        req = urllib.request.Request(
            webhook_url, method="POST",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status < 400
    except Exception:
        return False


def notify(
    message: str,
    level: str = "normal",
    title: str = "ぐるぐる3者会議",
    base: Path = DEFAULT_BASE,
) -> dict:
    cfg = read_config(base)
    current = cfg.get("level", "normal")
    if LEVELS.get(current, 1) < LEVELS.get(level, 1):
        return {"sent": False, "reason": f"level {current} blocks {level}"}

    results = {"mac": False, "slack": False, "discord": False}
    results["mac"] = _mac_notify(message, title)

    slack_url = cfg.get("slack_webhook_url") or os.environ.get("SLACK_WEBHOOK_URL")
    if slack_url:
        results["slack"] = _webhook_notify(slack_url, message)

    discord_url = cfg.get("discord_webhook_url") or os.environ.get("DISCORD_WEBHOOK_URL")
    if discord_url:
        results["discord"] = _webhook_notify(discord_url, message)

    return {"sent": True, "channels": results}


def notify_consensus_reached(
    room_id: str,
    topic_title: Optional[str] = None,
    base: Path = DEFAULT_BASE,
) -> dict:
    msg = f"【3者合意成立】 room={room_id}"
    if topic_title:
        msg += f" / 議題: {topic_title}"
    return notify(msg, level="normal",
                  title="ぐるぐる3者会議 — 合意成立", base=base)


def self_test() -> bool:
    import shutil
    tmp_base = Path(tempfile.mkdtemp(prefix="notify_test_"))
    try:
        cfg = read_config(base=tmp_base)
        assert cfg["level"] == "normal"

        write_config({"level": "off"}, base=tmp_base)
        r = notify("test message", level="normal", base=tmp_base)
        assert not r["sent"], f"OFF should block normal: {r}"

        write_config({"level": "strict"}, base=tmp_base)
        r = notify("test", level="normal", base=tmp_base)
        assert r["sent"], "strict should allow normal"

        print("PASS: notification_controller self_test")
        return True
    finally:
        shutil.rmtree(tmp_base, ignore_errors=True)


if __name__ == "__main__":
    ok = self_test()
    raise SystemExit(0 if ok else 1)
