#!/usr/bin/env python3
"""Binance先物 資金調達率(FR) 全履歴取得 → btc_market.db funding_rate_8h

₿部屋3者合意 (must-fix③): FRはBinance等から無料取得して補完する。
- エンドポイント: GET https://fapi.binance.com/fapi/v1/fundingRate (公開・キー不要・無料)
- BTCUSDT perp の8h FR。履歴は2019-09-10開始。limit=1000/req → 約8リクエストで全件
- 再実行安全: 既存最終ts以降のみ追記 (INSERT OR REPLACE)
"""
import json
import sqlite3
import ssl
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# homebrew python3.14はシステムCAを見ないため certifi のCA束を明示
import certifi
SSL_CTX = ssl.create_default_context(cafile=certifi.where())

BASE = Path(__file__).resolve().parent.parent
MKT_DB = BASE / "btc_market.db"
API = "https://fapi.binance.com/fapi/v1/fundingRate"
SYMBOL = "BTCUSDT"
FIRST_FUNDING_MS = 1568102400000  # 2019-09-10 08:00 UTC ごろ開始


def fetch_page(start_ms, limit=1000):
    q = urllib.parse.urlencode(
        {"symbol": SYMBOL, "startTime": start_ms, "limit": limit})
    req = urllib.request.Request(f"{API}?{q}",
                                 headers={"User-Agent": "kitt-fr-fetch/1.0"})
    with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as r:
        return json.loads(r.read().decode())


def main():
    con = sqlite3.connect(MKT_DB)
    con.execute("""
      CREATE TABLE IF NOT EXISTS funding_rate_8h (
        ts_ms INTEGER PRIMARY KEY,
        ts_utc TEXT,
        symbol TEXT,
        funding_rate REAL,
        mark_price REAL
      )""")
    last = con.execute(
        "SELECT MAX(ts_ms) FROM funding_rate_8h").fetchone()[0]
    start = (last + 1) if last else FIRST_FUNDING_MS
    total = 0
    while True:
        rows = fetch_page(start)
        if not rows:
            break
        for r in rows:
            ts = int(r["fundingTime"])
            con.execute(
                "INSERT OR REPLACE INTO funding_rate_8h VALUES (?,?,?,?,?)",
                (ts,
                 datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
                 .strftime("%Y-%m-%d %H:%M:%S"),
                 r["symbol"], float(r["fundingRate"]),
                 float(r.get("markPrice") or 0) or None))
        con.commit()
        total += len(rows)
        newest = int(rows[-1]["fundingTime"])
        print(f"  +{len(rows)}件 (累計{total}) .. "
              f"{datetime.fromtimestamp(newest/1000, tz=timezone.utc):%Y-%m-%d}",
              flush=True)
        if len(rows) < 1000:
            break
        start = newest + 1
        time.sleep(0.3)  # 公開APIへの礼儀 (rate limit余裕だが念のため)
    n, lo, hi = con.execute(
        "SELECT COUNT(*), MIN(ts_utc), MAX(ts_utc) FROM funding_rate_8h"
    ).fetchone()
    con.close()
    print(f"DONE funding_rate_8h: {n}行  {lo} .. {hi}  (+{total}追加)")


if __name__ == "__main__":
    main()
