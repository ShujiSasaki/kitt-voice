#!/usr/bin/env python3
"""
Binance APIからBTC/USDT日足データを取得してSQLiteに保存
"""
import json, sqlite3, os, time, subprocess
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'x_tweets.db')
conn = sqlite3.connect(DB_PATH)
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA busy_timeout=30000")

conn.execute("""CREATE TABLE IF NOT EXISTS market_btc_1d (
    ts_epoch INTEGER PRIMARY KEY,
    date TEXT NOT NULL,
    open REAL, high REAL, low REAL, close REAL,
    volume REAL
)""")
conn.commit()

# Fetch from Binance API (1000 candles per request, daily)
# 2017-08-17 is BTCUSDT listing date on Binance
start_ms = int(datetime(2017, 8, 17).timestamp() * 1000)
end_ms = int(datetime(2026, 5, 19).timestamp() * 1000)

total = 0
current = start_ms

while current < end_ms:
    url = f"https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1d&startTime={current}&limit=1000"
    result = subprocess.run(['curl', '-s', url], capture_output=True, text=True, timeout=30)
    data = json.loads(result.stdout)

    if not data or not isinstance(data, list):
        break

    for candle in data:
        ts = candle[0] // 1000  # ms to sec
        date_str = datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d')
        conn.execute(
            "INSERT OR IGNORE INTO market_btc_1d (ts_epoch, date, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ts, date_str, float(candle[1]), float(candle[2]), float(candle[3]), float(candle[4]), float(candle[5]))
        )

    total += len(data)
    current = data[-1][0] + 86400000  # next day in ms
    conn.commit()

    if len(data) < 1000:
        break
    time.sleep(0.5)

print(f"BTC daily candles saved: {total}", flush=True)
print(f"Date range: {conn.execute('SELECT MIN(date), MAX(date) FROM market_btc_1d').fetchone()}", flush=True)
conn.close()
