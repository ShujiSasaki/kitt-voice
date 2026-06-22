#!/usr/bin/env python3
"""
gallery-dl --dump-json の出力をパイプでSQLiteに投入
全ツイート(テキストのみ含む)を日単位で取得
"""
import json, subprocess, sqlite3, sys, os, re
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'x_tweets.db')
PROFILE = sys.argv[1] if len(sys.argv) > 1 else 'Profile 4'

conn = sqlite3.connect(DB_PATH)
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA synchronous=NORMAL")
conn.execute("PRAGMA busy_timeout=5000")
conn.execute("""CREATE TABLE IF NOT EXISTS fetch_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    screen_name TEXT NOT NULL,
    since_date TEXT NOT NULL,
    until_date TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    tweet_count INTEGER DEFAULT 0,
    started_at TEXT,
    finished_at TEXT,
    UNIQUE(screen_name, since_date, until_date)
)""")
conn.commit()

GAPS = {
    'smile_danjer': ('2023-07-01', '2024-05-01'),
    'BobLoukas': ('2021-05-01', '2025-03-01'),
    '_Checkmatey_': ('2020-12-01', '2025-08-01'),
    'LynAldenContact': ('2021-04-01', '2025-06-01'),
    'PeterLBrandt': ('2021-03-01', '2025-10-01'),
}

def save_tweet(data):
    tid = str(data.get('tweet_id', ''))
    if not tid or len(tid) < 10:
        return False

    screen_name = ''
    author = data.get('author', {})
    if isinstance(author, dict):
        screen_name = author.get('name', '')

    created_at = data.get('date', '')
    epoch = None
    if created_at:
        try:
            if isinstance(created_at, str):
                dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            else:
                dt = created_at
            epoch = int(dt.timestamp() * 1000)
            created_at = dt.isoformat()
        except:
            pass

    full_text = data.get('content', '') or ''
    in_reply = str(data.get('reply_to', '')) if data.get('reply_to') else None
    is_rt = 1 if data.get('retweet_id') else 0
    is_quote = 1 if data.get('quote_id') else 0

    media = None
    if data.get('media'):
        media = json.dumps(data['media'])

    try:
        cur = conn.execute(
            "INSERT OR IGNORE INTO tweets (tweet_id, screen_name, created_at, created_at_epoch, full_text, in_reply_to_status_id, is_retweet, is_quote, retweet_count, favorite_count, media_json, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (tid, screen_name, created_at, epoch, full_text, in_reply, is_rt, is_quote, data.get('retweet_count', 0), data.get('favorite_count', 0) or data.get('like_count', 0), media, datetime.utcnow().isoformat())
        )
        return cur.rowcount > 0
    except:
        return False

def fetch_day(handle, since, until):
    """gallery-dl --dump-json で取得してSQLiteに保存"""
    query = f"from:{handle} since:{since} until:{until}"
    url = f"https://x.com/search?q={query}&f=live"

    try:
        result = subprocess.run(
            ['gallery-dl', '--cookies-from-browser', f'chrome:{PROFILE}', '--dump-json', '-o', 'sleep-request=19', url],
            capture_output=True, text=True, timeout=21600  # 6時間タイムアウト
        )

        if not result.stdout.strip():
            return 0

        count = 0
        try:
            items = json.loads(result.stdout)
            # 形式: [[msg_type, tweet_data], ...]
            for item in items:
                if isinstance(item, list) and len(item) >= 2 and isinstance(item[1], dict):
                    d = item[1]
                    tid = str(d.get('tweet_id', ''))
                    if not tid or len(tid) < 10:
                        continue
                    screen_name = d.get('author', {}).get('name', '') if isinstance(d.get('author'), dict) else ''
                    created_at = str(d.get('date', ''))
                    full_text = d.get('content', '') or ''
                    in_reply = str(d.get('reply_to', '')) if d.get('reply_to') else None
                    is_rt = 1 if d.get('retweet_id') else 0
                    is_quote = 1 if d.get('quote_id') else 0
                    media = json.dumps(d['media']) if d.get('media') else None

                    try:
                        cur = conn.execute(
                            "INSERT OR IGNORE INTO tweets (tweet_id, screen_name, created_at, full_text, in_reply_to_status_id, is_retweet, is_quote, retweet_count, favorite_count, media_json, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (tid, screen_name, created_at, full_text, in_reply, is_rt, is_quote, d.get('retweet_count', 0), d.get('favorite_count', 0) or d.get('like_count', 0), media, datetime.utcnow().isoformat())
                        )
                        if cur.rowcount > 0:
                            count += 1
                    except:
                        pass
        except json.JSONDecodeError:
            pass

        conn.commit()
        return count
    except subprocess.TimeoutExpired:
        return -1
    except Exception as e:
        print(f"  Error: {e}")
        return -1

def main():
    target = sys.argv[2] if len(sys.argv) > 2 else None

    for account, (start, end) in GAPS.items():
        if target and account != target:
            continue

        print(f"\n=== {account}: {start} → {end} ===")

        d = datetime.strptime(start, '%Y-%m-%d')
        e = datetime.strptime(end, '%Y-%m-%d')
        total_days = (e - d).days
        total_new = 0
        day_num = 0

        while d < e:
            since = d.strftime('%Y-%m-%d')
            d += timedelta(days=7)  # 週単位
            if d > e: d = e
            until = d.strftime('%Y-%m-%d')
            day_num += 1

            # 既に完了済みならスキップ
            row = conn.execute("SELECT status FROM fetch_jobs WHERE screen_name=? AND since_date=? AND until_date=?", (account, since, until)).fetchone()
            if row and row[0] == 'done':
                continue

            conn.execute("INSERT OR REPLACE INTO fetch_jobs (screen_name, since_date, until_date, status, started_at) VALUES (?, ?, ?, 'running', ?)", (account, since, until, datetime.utcnow().isoformat()))
            conn.commit()

            count = fetch_day(account, since, until)

            if count >= 0:
                conn.execute("UPDATE fetch_jobs SET status='done', tweet_count=?, finished_at=? WHERE screen_name=? AND since_date=? AND until_date=?", (count, datetime.utcnow().isoformat(), account, since, until))
                total_new += count
            else:
                conn.execute("UPDATE fetch_jobs SET status='failed', finished_at=? WHERE screen_name=? AND since_date=? AND until_date=?", (datetime.utcnow().isoformat(), account, since, until))
            conn.commit()

            if day_num % 10 == 0:
                db_total = conn.execute("SELECT COUNT(*) FROM tweets WHERE screen_name=?", (account,)).fetchone()[0]
                print(f"  [{day_num}/{total_days}] {since}: DB={db_total} (+{total_new} new)")

        db_total = conn.execute("SELECT COUNT(*) FROM tweets WHERE screen_name=?", (account,)).fetchone()[0]
        print(f"\n{account} done: DB={db_total} (+{total_new} new)")

    conn.close()
    print("\n=== Complete ===")

if __name__ == '__main__':
    main()
