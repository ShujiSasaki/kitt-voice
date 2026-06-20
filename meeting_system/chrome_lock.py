"""
chrome_lock — Claude in Chrome 同時1件ロック (TTL自動解放付き)

システム保守ルーム 3者合意 (2026-06-21 00:47):
  「Claude in Chromeを同時に動かさず受付順に1件ずつ」処理する直列キュー。
  - 同時1件ロック: 共有Chrome(CDP)を駆動できるのは常に1プロセスのみ。
    複数プロジェクト/手動操作の同時併用でエラー率が上がる事故を防ぐ。
  - TTL自動解放: ロック保持プロセスがハング/異常終了しても、heartbeatが
    TTL超過で失効 → 次の待機者が奪取できる。1件のハングが行列全体を
    止める事故を防ぐ (全員 "絶対やる" で合意)。
  月額0円・外部公開なし・新DB不要 (data/chrome.lock の1ファイルのみ)。

排他: fcntl.flock(サイドカー .guard) で read-modify-write を直列化。
ロック本体は JSON: {holder, acquired_at, heartbeat, ttl, note, pid, stolen}.
保持者は処理中 heartbeat() でTTLを延ばし、終了時 release() で明示解放する。
"""
from __future__ import annotations

import contextlib
import json
import os
import time
from pathlib import Path

try:
    import fcntl  # POSIX (macOS/Linux)
    _HAS_FCNTL = True
except ImportError:  # pragma: no cover
    _HAS_FCNTL = False

from .state_schema import DEFAULT_BASE

ENC = "utf-8"
DEFAULT_TTL = 900.0  # 15分 — 1ターンの最長想定を超えたら失効とみなす


def _lock_path(base: Path) -> Path:
    return base / "data" / "chrome.lock"


def _guard_path(base: Path) -> Path:
    return base / "data" / "chrome.lock.guard"


@contextlib.contextmanager
def _guard(base: Path):
    """read-modify-write をプロセス間で直列化する排他区間。"""
    p = _guard_path(base)
    p.parent.mkdir(parents=True, exist_ok=True)
    f = open(p, "w")
    try:
        if _HAS_FCNTL:
            fcntl.flock(f, fcntl.LOCK_EX)
        yield
    finally:
        if _HAS_FCNTL:
            with contextlib.suppress(Exception):
                fcntl.flock(f, fcntl.LOCK_UN)
        f.close()


def _read(base: Path) -> dict | None:
    p = _lock_path(base)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding=ENC))
    except Exception:
        return None


def _write(base: Path, data: dict) -> None:
    p = _lock_path(base)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding=ENC)
    tmp.replace(p)


def _expired(rec: dict, now: float) -> bool:
    ttl = rec.get("ttl", DEFAULT_TTL)
    last = rec.get("heartbeat", rec.get("acquired_at", 0))
    return (now - last) > ttl


def acquire(holder: str, base: Path = DEFAULT_BASE,
            ttl: float = DEFAULT_TTL, note: str = "") -> bool:
    """ロック取得。空き/失効/自分が保持中なら True、他者が保持中(未失効)なら False。

    失効ロックは奪取する (stolen=True を記録)。同じholderの再取得は
    acquired_at を維持しつつ heartbeat を更新する (継続保持)。
    """
    now = time.time()
    with _guard(base):
        rec = _read(base)
        held_by_other = bool(rec and rec.get("holder") not in (None, holder))
        if held_by_other and not _expired(rec, now):
            return False
        if rec and rec.get("holder") == holder:
            acquired_at = rec.get("acquired_at", now)
        else:
            acquired_at = now
        _write(base, {
            "holder": holder,
            "acquired_at": acquired_at,
            "heartbeat": now,
            "ttl": ttl,
            "note": note,
            "pid": os.getpid(),
            "stolen": held_by_other,
        })
        return True


def heartbeat(holder: str, base: Path = DEFAULT_BASE) -> bool:
    """保持中ロックの heartbeat を更新 (TTL延長)。保持者でなければ False。"""
    now = time.time()
    with _guard(base):
        rec = _read(base)
        if not rec or rec.get("holder") != holder:
            return False
        rec["heartbeat"] = now
        _write(base, rec)
        return True


def release(holder: str, base: Path = DEFAULT_BASE) -> bool:
    """自分が保持しているロックを解放。保持者でなければ False (他者のは消さない)。"""
    with _guard(base):
        rec = _read(base)
        if rec and rec.get("holder") == holder:
            with contextlib.suppress(Exception):
                _lock_path(base).unlink()
            return True
        return False


def status(base: Path = DEFAULT_BASE) -> dict:
    """現在のロック状態。UI/監視用 (待ち順表示の実データ)。"""
    now = time.time()
    rec = _read(base)
    if not rec or not rec.get("holder"):
        return {"held": False, "holder": None, "ttl_remaining": 0.0,
                "expired": False, "note": "", "pid": None}
    exp = _expired(rec, now)
    ttl = rec.get("ttl", DEFAULT_TTL)
    remaining = max(0.0, ttl - (now - rec.get("heartbeat", now)))
    return {
        "held": not exp,
        "holder": rec.get("holder"),
        "acquired_at": rec.get("acquired_at"),
        "heartbeat": rec.get("heartbeat"),
        "ttl": ttl,
        "ttl_remaining": round(remaining, 1),
        "expired": exp,
        "note": rec.get("note", ""),
        "pid": rec.get("pid"),
        "stolen": rec.get("stolen", False),
    }


def self_test() -> bool:
    import shutil
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="chrome_lock_test_"))
    try:
        A, B = "workerA", "workerB"
        # 1. 取得 → 他者は失敗
        assert acquire(A, base=tmp) is True
        assert acquire(B, base=tmp) is False, "未失効ロックを奪取してしまった"
        # 2. heartbeat: 保持者OK / 非保持者NG
        assert heartbeat(A, base=tmp) is True
        assert heartbeat(B, base=tmp) is False
        # 3. status: 保持中
        s = status(base=tmp)
        assert s["held"] and s["holder"] == A, s
        assert s["ttl_remaining"] > 0
        # 4. 同一holder再取得 = 継続 (acquired_at維持)
        a0 = status(base=tmp)["acquired_at"]
        assert acquire(A, base=tmp) is True
        assert status(base=tmp)["acquired_at"] == a0, "再取得でacquired_atが変わった"
        # 5. TTL失効 → 他者が奪取
        assert acquire(A, base=tmp, ttl=0.01) is True
        time.sleep(0.05)
        s2 = status(base=tmp)
        assert s2["expired"] is True, f"失効判定されず: {s2}"
        assert acquire(B, base=tmp) is True, "失効ロックを奪取できない"
        assert status(base=tmp)["holder"] == B
        assert status(base=tmp)["stolen"] is True
        # 6. 解放: 非保持者は消せない / 保持者は消せる
        assert release(A, base=tmp) is False, "他者のロックを解放してしまった"
        assert release(B, base=tmp) is True
        assert status(base=tmp)["held"] is False
        # 7. 解放後は再取得できる
        assert acquire(A, base=tmp) is True
        release(A, base=tmp)
        print("PASS: chrome_lock self_test (取得/排他/heartbeat/継続/TTL奪取/解放)")
        return True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    import sys
    if "--self-test" in sys.argv:
        raise SystemExit(0 if self_test() else 1)
    print(json.dumps(status(), ensure_ascii=False, indent=2))
