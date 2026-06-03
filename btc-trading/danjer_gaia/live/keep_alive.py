"""
Project danjer-GAIA — Cache Keep-Alive
=========================================
🚨 Gemini Round 22 致命的指摘 (R42):
"Context Cache のデフォルトTTLは 5分 (300秒)。 Cloud Run 15分間隔のステートレス呼び出しでは
Cache再利用率 = 0% (毎回コールドスタート・フル課金・推論 10-15秒遅延)"

対策:
- Cloud Run Min Instances = 1 (常時1インスタンス維持)
- このスクリプトで 4分間隔の軽量 keep-alive クエリを Gemini に投げ続ける
- Cache life を常に 5分以内に再延長 → 再利用率 99%+ 維持

実行モード:
  - local: ローカルで5分毎に投げる (Cron or in-process loop)
  - cloud_run: Cloud Run 内部の同一プロセスで非同期 task として動かす
"""
from __future__ import annotations
import os
import time
import threading
from datetime import datetime, timezone
from typing import Optional, Callable
import logging


logger = logging.getLogger(__name__)


def load_env():
    env_path = '/Users/shuji/Desktop/kitt-voice/.env'
    if not os.path.exists(env_path):
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip().strip("'\""))


def keep_alive_ping(
    model: str = "models/gemini-2.0-flash-exp",
    cache_name: Optional[str] = None,
    ping_text: str = "ping",
) -> bool:
    """
    Gemini API に軽量クエリを投げて Context Cache の life を延長。

    Args:
        model: モデル名
        cache_name: 既存 Context Cache 名 (cachedContents/xxx)
        ping_text: 投げる短文 ("ping" 等、 10トークン以下を推奨)

    Returns: 成功なら True
    """
    load_env()
    try:
        import google.generativeai as genai
        api_key = os.environ.get('GEMINI_API_KEY')
        if not api_key:
            logger.warning("GEMINI_API_KEY not set, skip ping")
            return False
        genai.configure(api_key=api_key)

        if cache_name:
            # Context Cache が存在する場合: cache を使った generateContent でlife延長
            cached_model = genai.GenerativeModel.from_cached_content(cached_content=cache_name)
            resp = cached_model.generate_content(ping_text)
        else:
            # cache無しの場合 (Phase 2.5 初期): 単純に Gemini にping
            m = genai.GenerativeModel(model)
            resp = m.generate_content(ping_text)
        return bool(resp)
    except Exception as e:
        logger.warning(f"keep_alive_ping failed: {e}")
        return False


def run_keep_alive_loop(
    interval_seconds: int = 240,  # 4分 (Cache TTL 5分 = 300秒より短く)
    cache_name: Optional[str] = None,
    stop_event: Optional[threading.Event] = None,
    on_ping: Optional[Callable[[bool, datetime], None]] = None,
):
    """
    バックグラウンドで keep-alive を回し続ける。

    Args:
        interval_seconds: ping間隔 (デフォルト4分、 Cache TTL 5分より短く)
        cache_name: 維持したい Context Cache 名
        stop_event: 停止トリガー
        on_ping: ping毎のコールバック (成功/失敗, 時刻)
    """
    stop_event = stop_event or threading.Event()
    while not stop_event.is_set():
        ok = keep_alive_ping(cache_name=cache_name)
        now = datetime.now(timezone.utc)
        if on_ping:
            try:
                on_ping(ok, now)
            except Exception:
                pass
        logger.info(f"keep_alive ping ok={ok} at {now.isoformat()}")
        # interval 待機 (stop_event で早期解除可能)
        stop_event.wait(timeout=interval_seconds)


class KeepAliveThread:
    """バックグラウンドスレッドで keep-alive を回す管理クラス"""

    def __init__(self, interval_seconds: int = 240, cache_name: Optional[str] = None):
        self.interval = interval_seconds
        self.cache_name = cache_name
        self.stop_event = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self.ping_count = 0
        self.success_count = 0
        self.last_ping_at: Optional[datetime] = None
        self.last_success_at: Optional[datetime] = None

    def _on_ping(self, ok: bool, when: datetime):
        self.ping_count += 1
        self.last_ping_at = when
        if ok:
            self.success_count += 1
            self.last_success_at = when

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(
            target=run_keep_alive_loop,
            kwargs=dict(
                interval_seconds=self.interval,
                cache_name=self.cache_name,
                stop_event=self.stop_event,
                on_ping=self._on_ping,
            ),
            daemon=True,
        )
        self.thread.start()

    def stop(self, timeout: float = 5.0):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=timeout)

    def stats(self) -> dict:
        return {
            "ping_count": self.ping_count,
            "success_count": self.success_count,
            "success_rate": self.success_count / self.ping_count if self.ping_count else None,
            "last_ping_at": self.last_ping_at.isoformat() if self.last_ping_at else None,
            "last_success_at": self.last_success_at.isoformat() if self.last_success_at else None,
        }
