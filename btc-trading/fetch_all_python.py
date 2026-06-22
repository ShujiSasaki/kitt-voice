#!/usr/bin/env python3
"""
X全投稿取得 - gallery-dlと同じ認証でSearchTimeline全件(テキストのみ含む)をSQLite保存
日単位分割、cursor保存、中断再開対応
"""
import json, time, sqlite3, sys, os, re
from datetime import datetime, timedelta

# gallery-dlの認証とHTTPクライアントを再利用
from gallery_dl.extractor import twitter as tw
from gallery_dl import config

# SQLite
DB_PATH = os.path.join(os.path.dirname(__file__), 'x_tweets.db')
conn = sqlite3.connect(DB_PATH)
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA synchronous=NORMAL")
conn.execute("PRAGMA busy_timeout=5000")
conn.execute("""CREATE TABLE IF NOT EXISTS tweets (
    tweet_id TEXT PRIMARY KEY,
    screen_name TEXT,
    created_at TEXT,
    created_at_epoch INTEGER,
    full_text TEXT,
    in_reply_to_status_id TEXT,
    is_retweet INTEGER DEFAULT 0,
    is_quote INTEGER DEFAULT 0,
    retweet_count INTEGER,
    favorite_count INTEGER,
    media_json TEXT,
    raw_json TEXT,
    fetched_at TEXT
)""")
conn.execute("""CREATE TABLE IF NOT EXISTS fetch_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    screen_name TEXT NOT NULL,
    since_date TEXT NOT NULL,
    until_date TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    tweet_count INTEGER DEFAULT 0,
    started_at TEXT,
    finished_at TEXT,
    error TEXT,
    UNIQUE(screen_name, since_date, until_date)
)""")
conn.commit()

# 欠落期間
GAPS = {
    'smile_danjer': ('2023-07-01', '2024-05-01'),
    'BobLoukas': ('2021-05-01', '2025-03-01'),
    '_Checkmatey_': ('2020-12-01', '2025-08-01'),
    'LynAldenContact': ('2021-04-01', '2025-06-01'),
    'PeterLBrandt': ('2021-03-01', '2025-10-01'),
}

def save_tweet(tweet_data):
    """gallery-dlのtweet dictをSQLiteに保存"""
    tid = str(tweet_data.get('tweet_id', ''))
    if not tid or len(tid) < 10:
        return False

    screen_name = tweet_data.get('author', {}).get('name', '') or tweet_data.get('user', {}).get('name', '')
    created_at = tweet_data.get('date', '')
    if isinstance(created_at, datetime):
        epoch = int(created_at.timestamp() * 1000)
        created_at = created_at.isoformat()
    else:
        epoch = None

    full_text = tweet_data.get('content', '') or tweet_data.get('text', '')
    in_reply = tweet_data.get('reply_to', None)
    is_rt = 1 if tweet_data.get('retweet_id') else 0
    is_quote = 1 if tweet_data.get('quote_id') else 0
    rt_count = tweet_data.get('retweet_count', 0)
    fav_count = tweet_data.get('favorite_count', 0) or tweet_data.get('like_count', 0)

    media = None
    if tweet_data.get('media'):
        media = json.dumps(tweet_data['media'])

    try:
        conn.execute(
            "INSERT OR IGNORE INTO tweets (tweet_id, screen_name, created_at, created_at_epoch, full_text, in_reply_to_status_id, is_retweet, is_quote, retweet_count, favorite_count, media_json, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (tid, screen_name, created_at, epoch, full_text, in_reply, is_rt, is_quote, rt_count, fav_count, media, datetime.utcnow().isoformat())
        )
        return conn.total_changes > 0
    except:
        return False

def fetch_search(handle, since, until):
    """gallery-dlのAPIを使ってSearchTimeline取得"""
    url = f"https://x.com/search?q=from%3A{handle}%20since%3A{since}%20until%3A{until}&f=live"

    # gallery-dlのextractorを使用
    config.clear()
    config.set(("extractor", "twitter"), "cookies-from-browser", ["chrome", None, None, "Profile 4"])

    try:
        extr = tw.TwitterSearchExtractor.from_url(url)
        extr.initialize()

        count = 0
        for msg in extr:
            if msg[0] == tw.Message.Url:
                # 画像付きツイートのデータ
                tweet_data = msg[2] if len(msg) > 2 else {}
                if save_tweet(tweet_data):
                    count += 1
            elif msg[0] == tw.Message.Directory:
                # ディレクトリ情報(ツイートメタデータ含む場合)
                pass

        conn.commit()
        return count
    except Exception as e:
        return -1

def main():
    handle = sys.argv[1] if len(sys.argv) > 1 else None

    for account, (start, end) in GAPS.items():
        if handle and account != handle:
            continue

        print(f"\n=== {account}: {start} → {end} ===")

        # 日単位ジョブ生成
        d = datetime.strptime(start, '%Y-%m-%d')
        e = datetime.strptime(end, '%Y-%m-%d')

        total_new = 0
        day_num = 0

        while d < e:
            since = d.strftime('%Y-%m-%d')
            d += timedelta(days=1)
            until = d.strftime('%Y-%m-%d')
            day_num += 1

            # 既に完了済みならスキップ
            row = conn.execute("SELECT status FROM fetch_jobs WHERE screen_name=? AND since_date=? AND until_date=?", (account, since, until)).fetchone()
            if row and row[0] == 'done':
                continue

            # ジョブ記録
            conn.execute("INSERT OR REPLACE INTO fetch_jobs (screen_name, since_date, until_date, status, started_at) VALUES (?, ?, ?, 'running', ?)", (account, since, until, datetime.utcnow().isoformat()))
            conn.commit()

            count = fetch_search(account, since, until)

            if count >= 0:
                conn.execute("UPDATE fetch_jobs SET status='done', tweet_count=?, finished_at=? WHERE screen_name=? AND since_date=? AND until_date=?", (count, datetime.utcnow().isoformat(), account, since, until))
                total_new += count
            else:
                conn.execute("UPDATE fetch_jobs SET status='failed', error='fetch_error', finished_at=? WHERE screen_name=? AND since_date=? AND until_date=?", (datetime.utcnow().isoformat(), account, since, until))
            conn.commit()

            if day_num % 30 == 0:
                db_total = conn.execute("SELECT COUNT(*) FROM tweets WHERE screen_name=?", (account,)).fetchone()[0]
                print(f"  [{day_num}] {since}: DB={db_total} (+{total_new})")

        db_total = conn.execute("SELECT COUNT(*) FROM tweets WHERE screen_name=?", (account,)).fetchone()[0]
        print(f"{account} done: DB={db_total} (+{total_new})")

    conn.close()
    print("\n=== Complete ===")

if __name__ == '__main__':
    main()
