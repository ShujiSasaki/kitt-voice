#!/usr/bin/env python3
"""
twitterapi.io で全アカウントの投稿を取得
- UserTimeline API (includeReplies=false)
- cursor pagination で全件取得
- INSERT OR IGNORE で既存はスキップ
- 5秒間隔 (free tier制限)
- 中断再開: cursor_stateテーブルに保存
"""
import json, time, sqlite3, sys, os
from datetime import datetime
import subprocess

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'x_tweets.db')
API_KEY = "new1_feed115c46dc4fa0b618229cfb721068"

ACCOUNTS = {
    'CryptoHayes': '983993370048630785',
    'smile_danjer': '3382360819',
    'BobLoukas': '82172203',
    '_Checkmatey_': '951920334831173632',
    'LynAldenContact': '823766058909761536',
    'PeterLBrandt': '247857712',
    '4HpO4Q9Dz3CWkhV': '1177549072997027842',
}

conn = sqlite3.connect(DB_PATH)
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA busy_timeout=5000")

# cursor_state for twitterapi.io
conn.execute("""CREATE TABLE IF NOT EXISTS cursor_state_twitterapi (
    screen_name TEXT PRIMARY KEY,
    user_id TEXT,
    cursor TEXT,
    total_pages INTEGER DEFAULT 0,
    total_fetched INTEGER DEFAULT 0,
    total_new INTEGER DEFAULT 0,
    status TEXT DEFAULT 'pending',
    updated_at TEXT
)""")
conn.commit()


def fetch_page(user_id, cursor=None):
    """1ページ取得 (curl経由でSSL問題回避)"""
    url = f"https://api.twitterapi.io/twitter/user/tweet_timeline?userId={user_id}&includeReplies=false"
    if cursor:
        url += f"&cursor={cursor}"

    result = subprocess.run(
        ['curl', '-s', url, '-H', f'X-API-Key: {API_KEY}'],
        capture_output=True, text=True, timeout=30
    )

    try:
        data = json.loads(result.stdout)
        if data.get('status') != 'success':
            error = data.get('error', data.get('msg', 'unknown'))
            return None, None, False, error
        tweets = data.get('data', {}).get('tweets', [])
        next_cursor = data.get('next_cursor')
        has_next = data.get('has_next_page', False)
        return tweets, next_cursor, has_next, None
    except Exception as e:
        return None, None, False, str(e)


def save_tweets(tweets, handle):
    """ツイートをDB保存。新規件数を返す"""
    new = 0
    for t in tweets:
        tweet_id = str(t.get('id', ''))
        if not tweet_id or len(tweet_id) < 10:
            continue

        # RTスキップ
        if t.get('type') == 'retweet':
            continue

        text = t.get('text', '')
        created_at = t.get('createdAt', '')
        author = t.get('author', {})
        screen_name = author.get('userName', handle) if isinstance(author, dict) else handle

        # epoch
        epoch = None
        if created_at:
            try:
                dt = datetime.strptime(created_at, '%a %b %d %H:%M:%S %z %Y')
                epoch = int(dt.timestamp() * 1000)
            except:
                pass

        # media
        media = t.get('media', t.get('extendedEntities', {}).get('media', []))
        media_json = None
        if media and isinstance(media, list):
            media_list = []
            for m in media:
                if isinstance(m, dict):
                    media_list.append({
                        'type': m.get('type', 'photo'),
                        'url': m.get('media_url_https', m.get('url', '')),
                    })
            if media_list:
                media_json = json.dumps(media_list)

        is_reply = 1 if t.get('isReply') else 0
        is_quote = 1 if t.get('quoted_tweet') or t.get('isQuote') else 0
        in_reply_to = t.get('inReplyToId') or t.get('in_reply_to_status_id_str')

        try:
            cur = conn.execute(
                'INSERT OR IGNORE INTO tweets (tweet_id, screen_name, created_at, created_at_epoch, full_text, in_reply_to_status_id, is_retweet, is_quote, retweet_count, favorite_count, media_json, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (tweet_id, screen_name, created_at, epoch, text,
                 str(in_reply_to) if in_reply_to else None,
                 0, is_quote,
                 t.get('retweetCount', 0),
                 t.get('likeCount', 0),
                 media_json,
                 datetime.now().isoformat()))
            if cur.rowcount > 0:
                new += 1
        except:
            pass

    conn.commit()
    return new


def fetch_account(handle, user_id):
    """1アカウントの全投稿を取得"""
    # 中断再開チェック
    saved = conn.execute(
        "SELECT cursor, total_pages, total_fetched, total_new, status FROM cursor_state_twitterapi WHERE screen_name=?",
        (handle,)
    ).fetchone()

    if saved and saved[4] == 'done':
        print(f'  Already done. Skipping.')
        return

    cursor = saved[0] if saved else None
    total_pages = saved[1] if saved else 0
    total_fetched = saved[2] if saved else 0
    total_new = saved[3] if saved else 0

    if cursor:
        print(f'  Resuming from page {total_pages} (cursor saved)')

    db_before = conn.execute("SELECT COUNT(*) FROM tweets WHERE screen_name=?", (handle,)).fetchone()[0]
    rate_errors = 0

    while True:
        tweets, next_cursor, has_next, error = fetch_page(user_id, cursor)

        if error:
            if 'Too Many Requests' in str(error):
                rate_errors += 1
                if rate_errors > 10:
                    print(f'  Too many rate errors. Saving state and stopping.')
                    break
                print(f'  Rate limit. Waiting 10s...')
                time.sleep(10)
                continue
            else:
                print(f'  Error: {error}')
                break

        rate_errors = 0

        if not tweets:
            print(f'  No tweets returned. End of timeline.')
            conn.execute(
                "INSERT OR REPLACE INTO cursor_state_twitterapi (screen_name, user_id, cursor, total_pages, total_fetched, total_new, status, updated_at) VALUES (?, ?, ?, ?, ?, ?, 'done', ?)",
                (handle, user_id, cursor, total_pages, total_fetched, total_new, datetime.now().isoformat()))
            conn.commit()
            break

        new = save_tweets(tweets, handle)
        total_pages += 1
        total_fetched += len(tweets)
        total_new += new

        # cursor保存
        conn.execute(
            "INSERT OR REPLACE INTO cursor_state_twitterapi (screen_name, user_id, cursor, total_pages, total_fetched, total_new, status, updated_at) VALUES (?, ?, ?, ?, ?, ?, 'running', ?)",
            (handle, user_id, next_cursor, total_pages, total_fetched, total_new, datetime.now().isoformat()))
        conn.commit()

        # 進捗表示
        if total_pages % 10 == 0:
            db_now = conn.execute("SELECT COUNT(*) FROM tweets WHERE screen_name=?", (handle,)).fetchone()[0]
            oldest = tweets[-1].get('createdAt', '')[:19] if tweets else '?'
            print(f'  P{total_pages}: +{new}new/{len(tweets)}fetched (cumul: {total_new}new/{total_fetched}fetched) oldest={oldest} DB={db_now}')

        if not has_next or not next_cursor:
            print(f'  Pagination complete.')
            conn.execute(
                "INSERT OR REPLACE INTO cursor_state_twitterapi (screen_name, user_id, cursor, total_pages, total_fetched, total_new, status, updated_at) VALUES (?, ?, ?, ?, ?, ?, 'done', ?)",
                (handle, user_id, next_cursor, total_pages, total_fetched, total_new, datetime.now().isoformat()))
            conn.commit()
            break

        cursor = next_cursor
        time.sleep(6)  # 5秒制限 + 1秒余裕

    db_after = conn.execute("SELECT COUNT(*) FROM tweets WHERE screen_name=?", (handle,)).fetchone()[0]
    print(f'  {handle}: pages={total_pages}, fetched={total_fetched}, new={total_new}, DB: {db_before}→{db_after}')


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else None

    print(f'=== twitterapi.io Full Fetch ===')
    print(f'API Key: ...{API_KEY[-8:]}')

    for handle, user_id in ACCOUNTS.items():
        if target and handle != target:
            continue

        db_count = conn.execute("SELECT COUNT(*) FROM tweets WHERE screen_name=?", (handle,)).fetchone()[0]
        print(f'\n=== {handle} (id:{user_id}) DB:{db_count} ===')

        fetch_account(handle, user_id)

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
