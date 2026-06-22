#!/usr/bin/env python3
"""BTC 1h/4h 足を Binance公開API(無料・キー不要)から全期間取得 → btc_market.db

danjer予測の採点を日中精度で行うための価格パスデータ。
data-api.binance.vision は地域制限なしの公開市場データ専用エンドポイント。

usage: python3 fetch_btc_intraday.py 1h
       python3 fetch_btc_intraday.py 4h
"""
import json
import sqlite3
import ssl
import sys
import time
import urllib.request
from datetime import datetime, timezone

import certifi

DB = "/Users/shuji/Desktop/kitt-voice/btc-trading/btc_market.db"
BASE = "https://data-api.binance.vision/api/v3/klines"
SYMBOL = "BTCUSDT"
START_MS = int(datetime(2018, 12, 1, tzinfo=timezone.utc).timestamp() * 1000)
CTX = ssl.create_default_context(cafile=certifi.where())


def fetch(interval):
    table = f"market_btc_{interval}"
    con = sqlite3.connect(DB)
    con.execute(f"""CREATE TABLE IF NOT EXISTS {table} (
        ts_ms INTEGER PRIMARY KEY, ts_utc TEXT,
        open REAL, high REAL, low REAL, close REAL, volume REAL)""")
    con.commit()
    start = START_MS
    total = 0
    reqs = 0
    while True:
        url = (f"{BASE}?symbol={SYMBOL}&interval={interval}"
               f"&startTime={start}&limit=1000")
        for attempt in range(4):
            try:
                with urllib.request.urlopen(url, timeout=30, context=CTX) as r:
                    rows = json.loads(r.read())
                break
            except Exception as e:
                if attempt == 3:
                    raise
                time.sleep(2 * (attempt + 1))
        if not rows:
            break
        recs = []
        for k in rows:
            ts = k[0]
            iso = datetime.fromtimestamp(ts / 1000, timezone.utc).isoformat()
            recs.append((ts, iso, float(k[1]), float(k[2]), float(k[3]),
                         float(k[4]), float(k[5])))
        con.executemany(
            f"INSERT OR REPLACE INTO {table} "
            "(ts_ms,ts_utc,open,high,low,close,volume) VALUES (?,?,?,?,?,?,?)",
            recs)
        con.commit()
        total += len(recs)
        reqs += 1
        last = rows[-1][0]
        if reqs % 10 == 0:
            print(f"  {interval}: {total}本 "
                  f"(〜{datetime.fromtimestamp(last/1000,timezone.utc).date()})",
                  flush=True)
        if last <= start:
            break
        start = last + 1
        if len(rows) < 1000:
            break
        time.sleep(0.25)
    n = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    rng = con.execute(
        f"SELECT MIN(ts_utc),MAX(ts_utc) FROM {table}").fetchone()
    con.close()
    print(f"=== {table} 完了: {n}本 / {rng[0][:10]}〜{rng[1][:10]} ===")


if __name__ == "__main__":
    iv = sys.argv[1] if len(sys.argv) > 1 else "4h"
    fetch(iv)
