"""keep_alive 単体テスト (実 Gemini API は呼ばずスタブ)"""
from __future__ import annotations
import unittest
import threading
import time
from unittest.mock import patch
from datetime import datetime, timezone

from danjer_gaia.live.keep_alive import (
    KeepAliveThread, run_keep_alive_loop,
)


class TestKeepAliveThread(unittest.TestCase):
    def test_start_stop(self):
        kt = KeepAliveThread(interval_seconds=1)
        # ping を mock してすぐ True を返すように
        with patch('danjer_gaia.live.keep_alive.keep_alive_ping', return_value=True):
            kt.start()
            time.sleep(2.5)  # 2-3回 ping
            kt.stop(timeout=2.0)
        stats = kt.stats()
        # 少なくとも 1回は ping している
        self.assertGreaterEqual(stats["ping_count"], 1)
        self.assertGreaterEqual(stats["success_count"], 1)
        self.assertEqual(stats["success_rate"], 1.0)

    def test_stats_initial(self):
        kt = KeepAliveThread()
        s = kt.stats()
        self.assertEqual(s["ping_count"], 0)
        self.assertEqual(s["success_count"], 0)
        self.assertIsNone(s["success_rate"])
        self.assertIsNone(s["last_ping_at"])

    def test_failure_handling(self):
        kt = KeepAliveThread(interval_seconds=1)
        with patch('danjer_gaia.live.keep_alive.keep_alive_ping', return_value=False):
            kt.start()
            time.sleep(2.0)
            kt.stop(timeout=2.0)
        stats = kt.stats()
        self.assertGreaterEqual(stats["ping_count"], 1)
        # 成功は 0
        self.assertEqual(stats["success_count"], 0)
        self.assertEqual(stats["success_rate"], 0.0)


class TestKeepAliveLoop(unittest.TestCase):
    def test_stop_event_breaks_loop(self):
        stop = threading.Event()
        pings = []

        def callback(ok, when):
            pings.append((ok, when))
            if len(pings) >= 2:
                stop.set()

        with patch('danjer_gaia.live.keep_alive.keep_alive_ping', return_value=True):
            run_keep_alive_loop(interval_seconds=0.5, stop_event=stop, on_ping=callback)
        self.assertGreaterEqual(len(pings), 2)


if __name__ == "__main__":
    unittest.main()
