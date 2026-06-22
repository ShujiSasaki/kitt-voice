#!/usr/bin/env python3
"""
X API v2 公式API - ユーザータイムライン取得
$0.005/read (他人のツイート), exclude=replies,retweets で投稿のみ
pagination_token で全件取得、SQLite保存
"""
import json, time, sqlite3, sys, os, re
from datetime import datetime
import requests

# === Config ===
env = {}
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env')) as f:
    for line in f:
        if '=' in line and not line.startswith('#'):
            k, v = line.strip().split('=', 1)
            env[k] = v

BEARER_TOKEN = env.get('X_BEARER_TOKEN', '')
if not BEARER_TOKEN:
    print('ERROR: X_BEARER_TOKEN not found in .env')
    sys.exit(1)

# === SQLite ===
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'x_tweets.db')
conn = sqlite3.connect(DB_PATH)
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA busy_timeout=5000")

# === Accounts ===
ACCOUNTS = {
    'CryptoHayes': '983993370048630785',
    'smile_danjer': '3382360819',
    'BobLoukas': '82172203',
    '_Checkmatey_': '951920334831173632',
    'LynAldenContact': '823766058909761536',
    'PeterLBrandt': '247857712',
    '4HpO4Q9Dz3CWkhV': '1177549072997027842',
}

# === Session ===
session = requests.Session()
session.headers.update({
    'Authorization': f'Bearer {BEARER_TOKEN}',
    'User-Agent': 'btc-research/1.0',
})

# === Tweet fields ===
TWEET_FIELDS = 'created_at,public_metrics,referenced_tweets,attachments,entities,conversation_id,in_reply_to_user_id'
USER_FIELDS = 'username'
MEDIA_FIELDS = 'type,url,preview_image_url'
EXPANSIONS = 'attachments.media_keys,author_id'

def fetch_user_tweets(user_id, handle, max_results=100, start_time=None, end_time=None):
    """ユーザーの全ツイート取得 → クライアント側でRT/リプライ除外してDB保存"""
    url = f'https://api.x.com/2/users/{user_id}/tweets'
    params = {
        'max_results': max_results,
        # exclude なし: 全件取得してクライアントでフィルタ
        'tweet.fields': TWEET_FIELDS,
        'user.fields': USER_FIELDS,
        'media.fields': MEDIA_FIELDS,
        'expansions': EXPANSIONS,
    }
    if start_time:
        params['start_time'] = start_time  # ISO 8601 format
    if end_time:
        params['end_time'] = end_time

    total_new = 0
    total_fetched = 0
    page = 0
    pagination_token = None

    while True:
        if pagination_token:
            params['pagination_token'] = pagination_token
        elif 'pagination_token' in params:
            del params['pagination_token']

        resp = session.get(url, params=params, timeout=30)
        page += 1

        # Rate limit headers
        remaining = resp.headers.get('x-rate-limit-remaining', '?')
        reset = resp.headers.get('x-rate-limit-reset', '0')

        if resp.status_code == 429:
            if reset and reset != '0':
                wait = int(reset) - int(time.time()) + 5
                if wait > 0:
                    print(f'    429 rate limited. Waiting {wait}s (reset: {datetime.fromtimestamp(int(reset)).strftime("%H:%M")})')
                    time.sleep(wait)
                    continue
            else:
                print('    429 rate limited. Waiting 900s')
                time.sleep(900)
                continue

        if resp.status_code != 200:
            print(f'    HTTP {resp.status_code}: {resp.text[:200]}')
            break

        data = resp.json()
        tweets = data.get('data', [])
        meta = data.get('meta', {})
        includes = data.get('includes', {})

        # Build media lookup
        media_lookup = {}
        for m in includes.get('media', []):
            media_lookup[m['media_key']] = {
                'type': m.get('type'),
                'url': m.get('url') or m.get('preview_image_url'),
            }

        if not tweets:
            print(f'    Page {page}: no tweets returned')
            break

        total_fetched += len(tweets)
        new = 0
        skipped_rt = 0
        skipped_reply = 0
        for t in tweets:
            tweet_id = t['id']
            created_at = t.get('created_at', '')
            full_text = t.get('text', '')

            # Referenced tweets (quote, reply, RT)
            refs = t.get('referenced_tweets', [])
            is_rt = 1 if any(r['type'] == 'retweeted' for r in refs) else 0
            is_quote = 1 if any(r['type'] == 'quoted' for r in refs) else 0
            in_reply = None
            is_reply = False
            for r in refs:
                if r['type'] == 'replied_to':
                    in_reply = r['id']
                    is_reply = True

            # Skip RTs (don't store)
            if is_rt:
                skipped_rt += 1
                continue

            # Skip replies to others (store self-replies as threads)
            reply_to_user = t.get('in_reply_to_user_id')
            if is_reply and reply_to_user and reply_to_user != user_id:
                skipped_reply += 1
                continue

            # Parse epoch
            epoch = None
            if created_at:
                try:
                    dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    epoch = int(dt.timestamp() * 1000)
                except:
                    pass

            # Public metrics
            pm = t.get('public_metrics', {})
            rt_count = pm.get('retweet_count', 0)
            fav_count = pm.get('like_count', 0)

            # Media
            media_keys = t.get('attachments', {}).get('media_keys', [])
            media_list = [media_lookup[mk] for mk in media_keys if mk in media_lookup]
            media_json = json.dumps(media_list) if media_list else None

            try:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO tweets (tweet_id, screen_name, created_at, created_at_epoch, full_text, in_reply_to_status_id, is_retweet, is_quote, retweet_count, favorite_count, media_json, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (tweet_id, handle, created_at, epoch, full_text, in_reply, is_rt, is_quote, rt_count, fav_count, media_json, datetime.utcnow().isoformat())
                )
                if cur.rowcount > 0:
                    new += 1
            except Exception as e:
                print(f'    DB error: {e}')

        conn.commit()
        total_new += new

        result_count = meta.get('result_count', len(tweets))
        next_token = meta.get('next_token')

        # Progress
        oldest = tweets[-1].get('created_at', '')[:10] if tweets else '?'
        print(f'    P{page}: {result_count}件 (+{new}new, skip:RT={skipped_rt}/reply={skipped_reply}) r={remaining} oldest={oldest}')

        if not next_token:
            print(f'    Pagination complete.')
            break

        pagination_token = next_token
        time.sleep(1)  # 1秒間隔

    return total_fetched, total_new


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else None

    print(f'=== X API v2 Tweet Fetcher ===')
    print(f'Bearer Token: ...{BEARER_TOKEN[-10:]}')

    for handle, user_id in ACCOUNTS.items():
        if target and handle != target:
            continue

        db_before = conn.execute("SELECT COUNT(*) FROM tweets WHERE screen_name=?", (handle,)).fetchone()[0]
        print(f'\n=== {handle} (id:{user_id}) DB:{db_before} ===')

        fetched, new = fetch_user_tweets(user_id, handle)

        db_after = conn.execute("SELECT COUNT(*) FROM tweets WHERE screen_name=?", (handle,)).fetchone()[0]
        print(f'\n{handle}: fetched={fetched}, new={new}, DB: {db_before} → {db_after}')

    conn.close()
    print('\n=== Complete ===')


if __name__ == '__main__':
    main()
