#!/usr/bin/env python3
"""
Binance APIからBTC/USDT 4H足・1H足データを取得してSQLiteに保存
+ tweet_marketにマルチタイムフレームリターンを紐付け
"""
import json, sqlite3, os, time, subprocess
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'x_tweets.db')
conn = sqlite3.connect(DB_PATH)
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA busy_timeout=30000")

# Create 4H table
conn.execute("""CREATE TABLE IF NOT EXISTS market_btc_4h (
    ts_epoch INTEGER PRIMARY KEY,
    datetime TEXT NOT NULL,
    open REAL, high REAL, low REAL, close REAL,
    volume REAL
)""")

# Create 1H table
conn.execute("""CREATE TABLE IF NOT EXISTS market_btc_1h (
    ts_epoch INTEGER PRIMARY KEY,
    datetime TEXT NOT NULL,
    open REAL, high REAL, low REAL, close REAL,
    volume REAL
)""")
conn.commit()

def fetch_klines(interval, table_name):
    """Fetch klines from Binance API"""
    start_ms = int(datetime(2017, 8, 17).timestamp() * 1000)
    end_ms = int(datetime(2026, 5, 20).timestamp() * 1000)

    # Check existing data to resume
    row = conn.execute(f"SELECT MAX(ts_epoch) FROM {table_name}").fetchone()
    if row[0]:
        start_ms = (row[0] + 1) * 1000  # resume from last + 1 sec
        print(f"[{table_name}] Resuming from {datetime.utcfromtimestamp(row[0])}", flush=True)

    total = 0
    current = start_ms

    while current < end_ms:
        url = f"https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval={interval}&startTime={current}&limit=1000"
        result = subprocess.run(['curl', '-s', url], capture_output=True, text=True, timeout=30)

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            print(f"JSON parse error, retrying in 5s...", flush=True)
            time.sleep(5)
            continue

        if not data or not isinstance(data, list):
            if isinstance(data, dict) and data.get('code') == -1003:
                print("Rate limited, waiting 60s...", flush=True)
                time.sleep(60)
                continue
            break

        for candle in data:
            ts = candle[0] // 1000
            dt_str = datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d %H:%M')
            conn.execute(
                f"INSERT OR IGNORE INTO {table_name} (ts_epoch, datetime, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (ts, dt_str, float(candle[1]), float(candle[2]), float(candle[3]), float(candle[4]), float(candle[5]))
            )

        total += len(data)
        # Advance: use close time of last candle + 1ms
        current = data[-1][6] + 1  # closeTime + 1
        conn.commit()

        if total % 5000 == 0:
            print(f"[{table_name}] {total} candles fetched...", flush=True)

        if len(data) < 1000:
            break
        time.sleep(0.3)

    count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
    date_range = conn.execute(f"SELECT MIN(datetime), MAX(datetime) FROM {table_name}").fetchone()
    print(f"[{table_name}] Total: {count} candles, Range: {date_range[0]} ~ {date_range[1]}", flush=True)
    return count

# --- Step 1: Fetch 4H candles ---
print("=== Fetching 4H candles ===", flush=True)
count_4h = fetch_klines('4h', 'market_btc_4h')

# --- Step 2: Fetch 1H candles ---
print("\n=== Fetching 1H candles ===", flush=True)
count_1h = fetch_klines('1h', 'market_btc_1h')

# --- Step 3: Update tweet_market with multi-timeframe returns ---
print("\n=== Updating tweet_market with multi-TF returns ===", flush=True)

# Add new columns if not exist
for col in ['btc_price_4h', 'ret_4h', 'ret_12h', 'ret_2d', 'ret_3d']:
    try:
        conn.execute(f"ALTER TABLE tweet_market ADD COLUMN {col} REAL")
        print(f"  Added column: {col}", flush=True)
    except sqlite3.OperationalError:
        pass  # already exists
conn.commit()

# Build 4H close price lookup (ts_epoch -> close)
print("  Building 4H price index...", flush=True)
prices_4h = {}
for row in conn.execute("SELECT ts_epoch, close FROM market_btc_4h ORDER BY ts_epoch"):
    prices_4h[row[0]] = row[1]
ts_4h_list = sorted(prices_4h.keys())

# Build 1H close price lookup
print("  Building 1H price index...", flush=True)
prices_1h = {}
for row in conn.execute("SELECT ts_epoch, close FROM market_btc_1h ORDER BY ts_epoch"):
    prices_1h[row[0]] = row[1]
ts_1h_list = sorted(prices_1h.keys())

import bisect

def find_price_at(ts_list, prices_dict, target_ts):
    """Find the closest candle close price at or before target_ts"""
    idx = bisect.bisect_right(ts_list, target_ts) - 1
    if idx < 0:
        return None
    return prices_dict[ts_list[idx]]

def find_price_after(ts_list, prices_dict, target_ts):
    """Find the closest candle close price at or after target_ts"""
    idx = bisect.bisect_left(ts_list, target_ts)
    if idx >= len(ts_list):
        return None
    return prices_dict[ts_list[idx]]

# Get all tweets with their epoch timestamps
print("  Loading tweets...", flush=True)
tweets = conn.execute("""
    SELECT tm.tweet_id, t.created_at_epoch
    FROM tweet_market tm
    JOIN tweets t ON tm.tweet_id = t.tweet_id
    WHERE t.created_at_epoch IS NOT NULL
""").fetchall()

print(f"  Processing {len(tweets)} tweets...", flush=True)

batch = []
updated = 0
for tweet_id, tweet_ts in tweets:
    if tweet_ts is None:
        continue

    # Current 4H candle price
    price_now_4h = find_price_at(ts_4h_list, prices_4h, tweet_ts)
    if price_now_4h is None:
        continue

    # Future prices at various horizons (using 1H for precision)
    price_4h_later = find_price_after(ts_1h_list, prices_1h, tweet_ts + 4*3600)
    price_12h_later = find_price_after(ts_1h_list, prices_1h, tweet_ts + 12*3600)
    price_2d_later = find_price_after(ts_1h_list, prices_1h, tweet_ts + 2*86400)
    price_3d_later = find_price_after(ts_1h_list, prices_1h, tweet_ts + 3*86400)

    ret_4h = ((price_4h_later / price_now_4h) - 1) * 100 if price_4h_later else None
    ret_12h = ((price_12h_later / price_now_4h) - 1) * 100 if price_12h_later else None
    ret_2d = ((price_2d_later / price_now_4h) - 1) * 100 if price_2d_later else None
    ret_3d = ((price_3d_later / price_now_4h) - 1) * 100 if price_3d_later else None

    batch.append((price_now_4h, ret_4h, ret_12h, ret_2d, ret_3d, tweet_id))

    if len(batch) >= 1000:
        conn.executemany(
            "UPDATE tweet_market SET btc_price_4h=?, ret_4h=?, ret_12h=?, ret_2d=?, ret_3d=? WHERE tweet_id=?",
            batch
        )
        conn.commit()
        updated += len(batch)
        batch = []
        if updated % 10000 == 0:
            print(f"  Updated {updated}/{len(tweets)} tweets...", flush=True)

if batch:
    conn.executemany(
        "UPDATE tweet_market SET btc_price_4h=?, ret_4h=?, ret_12h=?, ret_2d=?, ret_3d=? WHERE tweet_id=?",
        batch
    )
    conn.commit()
    updated += len(batch)

print(f"\n=== DONE ===", flush=True)
print(f"4H candles: {count_4h}", flush=True)
print(f"1H candles: {count_1h}", flush=True)
print(f"tweet_market updated: {updated} rows", flush=True)

# Verify
sample = conn.execute("""
    SELECT tm.tweet_id, t.screen_name, t.created_at,
           tm.btc_price, tm.btc_price_4h,
           tm.ret_4h, tm.ret_12h, tm.ret_1d, tm.ret_2d, tm.ret_3d, tm.ret_7d
    FROM tweet_market tm
    JOIN tweets t ON tm.tweet_id = t.tweet_id
    WHERE tm.ret_4h IS NOT NULL AND t.screen_name = 'smile_danjer'
    ORDER BY t.created_at_epoch DESC
    LIMIT 5
""").fetchall()
print("\nSample (danjer latest 5):", flush=True)
for r in sample:
    print(f"  {r[2]} | 1d${r[3]:.0f} 4h${r[4]:.0f} | ret: 4h={r[5]:+.2f}% 12h={r[6]:+.2f}% 1d={r[7]:+.2f}% 2d={r[8]:+.2f}% 3d={r[9]:+.2f}% 7d={r[10]:+.2f}%", flush=True)

conn.close()
