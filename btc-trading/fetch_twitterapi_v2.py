#!/usr/bin/env python3
"""
twitterapi.io v2 - Search API + 日付ウィンドウ分割で全件取得
- advanced_search エンドポイント
- since_time/until_time でUnixタイムスタンプ分割
- 月単位ウィンドウ + cursor pagination
- INSERT OR IGNORE
- 中断再開対応
"""
import json, time, sqlite3, sys, os, functools
from datetime import datetime, timedelta
import subprocess

# Force flush on all prints
print = functools.partial(print, flush=True)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'x_tweets.db')
API_KEY = "new1_feed115c46dc4fa0b618229cfb721068"

ACCOUNTS = {
    'CryptoHayes': ('983993370048630785', '2018-03-01', '2026-05-18'),
    'smile_danjer': ('3382360819', '2015-08-01', '2026-05-18'),
    'BobLoukas': ('82172203', '2009-10-01', '2026-05-18'),
    '_Checkmatey_': ('951920334831173632', '2018-01-01', '2026-05-18'),
    'LynAldenContact': ('823766058909761536', '2017-01-01', '2026-05-18'),
    'PeterLBrandt': ('247857712', '2014-01-01', '2026-05-18'),
    '4HpO4Q9Dz3CWkhV': ('1177549072997027842', '2019-09-01', '2026-05-18'),
}

conn = sqlite3.connect(DB_PATH)
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA busy_timeout=5000")

conn.execute("""CREATE TABLE IF NOT EXISTS search_windows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    screen_name TEXT NOT NULL,
    since_ts INTEGER NOT NULL,
    until_ts INTEGER NOT NULL,
    cursor TEXT,
    status TEXT DEFAULT 'pending',
    fetched_count INTEGER DEFAULT 0,
    new_count INTEGER DEFAULT 0,
    updated_at TEXT,
    UNIQUE(screen_name, since_ts, until_ts)
)""")
conn.commit()


def generate_windows(handle, start_str, end_str, days=30):
    """月単位のウィンドウを生成してDBに保存"""
    d = datetime.strptime(start_str, '%Y-%m-%d')
    e = datetime.strptime(end_str, '%Y-%m-%d')
    windows = []
    while d < e:
        since = d
        d += timedelta(days=days)
        if d > e:
            d = e
        until = d
        since_ts = int(since.timestamp())
        until_ts = int(until.timestamp())

        # 既にdoneならスキップ
        existing = conn.execute(
            "SELECT status FROM search_windows WHERE screen_name=? AND since_ts=? AND until_ts=?",
            (handle, since_ts, until_ts)
        ).fetchone()
        if existing and existing[0] == 'done':
            continue

        conn.execute(
            "INSERT OR IGNORE INTO search_windows (screen_name, since_ts, until_ts, status) VALUES (?, ?, ?, 'pending')",
            (handle, since_ts, until_ts)
        )
        windows.append((since_ts, until_ts))
    conn.commit()
    return windows


def fetch_search_page(query, cursor=None):
    """1ページ検索"""
    import urllib.parse
    params = f"query={query}&queryType=Latest"
    if cursor:
        params += f"&cursor={urllib.parse.quote(cursor, safe='')}"
    url = f"https://api.twitterapi.io/twitter/tweet/advanced_search?{params}"

    result = subprocess.run(
        ['curl', '-s', '--max-time', '30', url, '-H', f'X-API-Key: {API_KEY}'],
        capture_output=True, text=True, timeout=45
    )

    try:
        data = json.loads(result.stdout)
        if data.get('error') == 'Too Many Requests':
            return None, None, False, 'rate_limit'
        if data.get('error'):
            return None, None, False, data.get('error')
        # Two response formats: {tweets:[...]} or {status:"success", data:{tweets:[...]}}
        tweets = data.get('tweets', [])
        if not tweets and 'data' in data:
            tweets = data.get('data', {}).get('tweets', [])
        next_cursor = data.get('next_cursor')
        has_next = data.get('has_next_page', False)
        return tweets, next_cursor, has_next, None
    except Exception as e:
        return None, None, False, str(e)


def save_tweets(tweets, handle):
    """ツイートをDB保存"""
    new = 0
    for t in tweets:
        tweet_id = str(t.get('id', ''))
        if not tweet_id or len(tweet_id) < 10:
            continue
        if t.get('type') == 'retweet':
            continue

        text = t.get('text', '')
        created_at = t.get('createdAt', '')
        author = t.get('author', {})
        screen_name = author.get('userName', handle) if isinstance(author, dict) else handle

        epoch = None
        if created_at:
            try:
                dt = datetime.strptime(created_at, '%a %b %d %H:%M:%S %z %Y')
                epoch = int(dt.timestamp() * 1000)
            except:
                pass

        media = t.get('media', t.get('extendedEntities', {}).get('media', []))
        media_json = None
        if media and isinstance(media, list):
            media_list = [{'type': m.get('type', 'photo'), 'url': m.get('media_url_https', m.get('url', ''))} for m in media if isinstance(m, dict)]
            if media_list:
                media_json = json.dumps(media_list)

        is_quote = 1 if t.get('quoted_tweet') or t.get('isQuote') else 0
        in_reply_to = t.get('inReplyToId') or t.get('in_reply_to_status_id_str')

        try:
            cur = conn.execute(
                'INSERT OR IGNORE INTO tweets (tweet_id, screen_name, created_at, created_at_epoch, full_text, in_reply_to_status_id, is_retweet, is_quote, retweet_count, favorite_count, media_json, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (tweet_id, screen_name, created_at, epoch, text,
                 str(in_reply_to) if in_reply_to else None,
                 0, is_quote, t.get('retweetCount', 0), t.get('likeCount', 0),
                 media_json, datetime.now().isoformat()))
            if cur.rowcount > 0:
                new += 1
        except:
            pass
    conn.commit()
    return new


def fetch_window(handle, since_ts, until_ts):
    """1つの日付ウィンドウを全ページ取得"""
    import urllib.parse
    query = urllib.parse.quote(f'from:{handle} since_time:{since_ts} until_time:{until_ts}')

    # 保存済みcursor確認
    saved = conn.execute(
        "SELECT cursor, fetched_count, new_count FROM search_windows WHERE screen_name=? AND since_ts=? AND until_ts=?",
        (handle, since_ts, until_ts)
    ).fetchone()
    cursor = saved[0] if saved and saved[0] else None
    total_fetched = saved[1] if saved else 0
    total_new = saved[2] if saved else 0

    page = 0
    rate_errors = 0
    consecutive_no_new = 0
    MAX_PAGES_PER_WINDOW = 100  # 1windowあたり最大100ページ

    while True:
        tweets, next_cursor, has_next, error = fetch_search_page(query, cursor)

        if error:
            if error == 'rate_limit':
                rate_errors += 1
                print(f'    Rate limit ({rate_errors}/5). Waiting 10s...')
                if rate_errors > 5:
                    conn.execute(
                        "UPDATE search_windows SET status='rate_limited', cursor=?, fetched_count=?, new_count=?, updated_at=? WHERE screen_name=? AND since_ts=? AND until_ts=?",
                        (cursor, total_fetched, total_new, datetime.now().isoformat(), handle, since_ts, until_ts))
                    conn.commit()
                    return total_fetched, total_new, 'rate_limited'
                time.sleep(10)
                continue
            else:
                print(f'    Error: {error}')
                return total_fetched, total_new, f'error:{error}'

        rate_errors = 0

        if not tweets:
            conn.execute(
                "UPDATE search_windows SET status='done', cursor=?, fetched_count=?, new_count=?, updated_at=? WHERE screen_name=? AND since_ts=? AND until_ts=?",
                (cursor, total_fetched, total_new, datetime.now().isoformat(), handle, since_ts, until_ts))
            conn.commit()
            return total_fetched, total_new, 'done'

        new = save_tweets(tweets, handle)
        total_fetched += len(tweets)
        total_new += new
        page += 1

        page += 1

        # 新規0が続く場合は早期終了（既取得エリアの無駄巡回を防止）
        if new == 0:
            consecutive_no_new += 1
        else:
            consecutive_no_new = 0

        if consecutive_no_new >= 10:
            print(f'      10 consecutive pages with 0 new. Skipping rest of window.')
            conn.execute(
                "UPDATE search_windows SET status='done', cursor=?, fetched_count=?, new_count=?, updated_at=? WHERE screen_name=? AND since_ts=? AND until_ts=?",
                (next_cursor, total_fetched, total_new, datetime.now().isoformat(), handle, since_ts, until_ts))
            conn.commit()
            return total_fetched, total_new, 'done'

        if page >= MAX_PAGES_PER_WINDOW:
            print(f'      Max pages ({MAX_PAGES_PER_WINDOW}) reached.')
            conn.execute(
                "UPDATE search_windows SET status='done', cursor=?, fetched_count=?, new_count=?, updated_at=? WHERE screen_name=? AND since_ts=? AND until_ts=?",
                (next_cursor, total_fetched, total_new, datetime.now().isoformat(), handle, since_ts, until_ts))
            conn.commit()
            return total_fetched, total_new, 'max_pages'

        if page % 10 == 0:
            print(f'      page {page}: +{new}new/{len(tweets)}t (cumul: {total_new}/{total_fetched})')

        # cursor保存
        conn.execute(
            "UPDATE search_windows SET status='running', cursor=?, fetched_count=?, new_count=?, updated_at=? WHERE screen_name=? AND since_ts=? AND until_ts=?",
            (next_cursor, total_fetched, total_new, datetime.now().isoformat(), handle, since_ts, until_ts))
        conn.commit()

        if not has_next or not next_cursor:
            conn.execute(
                "UPDATE search_windows SET status='done', cursor=?, fetched_count=?, new_count=?, updated_at=? WHERE screen_name=? AND since_ts=? AND until_ts=?",
                (next_cursor, total_fetched, total_new, datetime.now().isoformat(), handle, since_ts, until_ts))
            conn.commit()
            return total_fetched, total_new, 'done'

        cursor = next_cursor
        time.sleep(2)  # 有料プランは2秒間隔OK

    return total_fetched, total_new, 'done'


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else None
    window_days = int(sys.argv[2]) if len(sys.argv) > 2 else 30

    print(f'=== twitterapi.io v2 Search Fetch ===')

    for handle, (user_id, start, end) in ACCOUNTS.items():
        if target and handle != target:
            continue

        db_before = conn.execute("SELECT COUNT(*) FROM tweets WHERE screen_name=?", (handle,)).fetchone()[0]
        print(f'\n=== {handle}: {start} → {end} DB:{db_before} ===')

        # ウィンドウ生成
        windows = generate_windows(handle, start, end, days=window_days)
        total_windows = conn.execute(
            "SELECT COUNT(*) FROM search_windows WHERE screen_name=? AND status != 'done'",
            (handle,)
        ).fetchone()[0]
        done_windows = conn.execute(
            "SELECT COUNT(*) FROM search_windows WHERE screen_name=? AND status = 'done'",
            (handle,)
        ).fetchone()[0]
        print(f'  Windows: {total_windows} pending, {done_windows} done')

        # pending/running/rate_limitedのウィンドウを処理
        pending = conn.execute(
            "SELECT since_ts, until_ts FROM search_windows WHERE screen_name=? AND status != 'done' ORDER BY since_ts",
            (handle,)
        ).fetchall()

        for i, (since_ts, until_ts) in enumerate(pending):
            since_str = datetime.fromtimestamp(since_ts).strftime('%Y-%m-%d')
            until_str = datetime.fromtimestamp(until_ts).strftime('%Y-%m-%d')

            fetched, new, status = fetch_window(handle, since_ts, until_ts)

            db_now = conn.execute("SELECT COUNT(*) FROM tweets WHERE screen_name=?", (handle,)).fetchone()[0]
            print(f'  [{i+1}/{len(pending)}] {since_str}→{until_str}: +{new}new/{fetched}fetched status={status} DB={db_now}')

            if status == 'rate_limited':
                print(f'  Rate limited. Waiting 60s then continuing...')
                time.sleep(60)

        db_after = conn.execute("SELECT COUNT(*) FROM tweets WHERE screen_name=?", (handle,)).fetchone()[0]
        print(f'\n{handle} done: {db_before} → {db_after} (+{db_after - db_before})')

    print(f'\n=== Final DB Status ===')
    for handle in ACCOUNTS:
        cnt = conn.execute("SELECT COUNT(*) FROM tweets WHERE screen_name=?", (handle,)).fetchone()[0]
        print(f'  {handle}: {cnt}')
    total = conn.execute("SELECT COUNT(*) FROM tweets").fetchone()[0]
    print(f'  Total: {total}')
    conn.close()
    print('\n=== Complete ===')


if __name__ == '__main__':
    main()
