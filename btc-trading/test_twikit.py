#!/usr/bin/env python3
"""
twikit テスト - UserTweetsの速度とレート制限を確認
"""
import asyncio
import json
import os
import sqlite3
import time
from datetime import datetime

# twikit uses httpx internally - no browser needed
from twikit import Client

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'x_tweets.db')

env = {}
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env')) as f:
    for line in f:
        if '=' in line and not line.startswith('#'):
            k, v = line.strip().split('=', 1)
            env[k] = v

async def main():
    client = Client('ja')

    # Login with cookies
    ct0 = env.get('X_CT0', '')
    auth_token = env.get('X_AUTH_TOKEN', '')

    # Set cookies directly
    client.set_cookies({
        'ct0': ct0,
        'auth_token': auth_token,
    })

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")

    # Test: Get BobLoukas's tweets
    handle = 'BobLoukas'
    user_id = '82172203'

    print(f'=== twikit test: {handle} ===')
    db_before = conn.execute("SELECT COUNT(*) FROM tweets WHERE screen_name=?", (handle,)).fetchone()[0]
    print(f'DB before: {db_before}')

    start_time = time.time()
    total_new = 0
    total_fetched = 0
    page = 0

    try:
        # Get user
        user = await client.get_user_by_screen_name(handle)
        print(f'User: {user.name} (id: {user.id}, tweets: {user.statuses_count})')

        # Get tweets
        tweets = await user.get_tweets('Tweets', count=20)
        cursor = None

        while tweets:
            page += 1
            fetched = len(tweets)
            total_fetched += fetched
            new = 0

            for t in tweets:
                tweet_id = t.id
                text = t.text or ''
                created_at = str(t.created_at) if t.created_at else ''

                # Skip RTs
                if hasattr(t, 'retweeted_tweet') and t.retweeted_tweet:
                    continue

                # Parse epoch
                epoch = None
                if t.created_at:
                    try:
                        epoch = int(t.created_at.timestamp() * 1000)
                    except:
                        pass

                # Media
                media_json = None
                if hasattr(t, 'media') and t.media:
                    media_list = []
                    for m in t.media:
                        media_list.append({
                            'type': getattr(m, 'type', 'photo'),
                            'url': getattr(m, 'media_url_https', '') or getattr(m, 'url', ''),
                        })
                    if media_list:
                        media_json = json.dumps(media_list)

                is_quote = 1 if hasattr(t, 'quoted_tweet') and t.quoted_tweet else 0
                in_reply = getattr(t, 'in_reply_to_status_id', None)
                rt_count = getattr(t, 'retweet_count', 0) or 0
                fav_count = getattr(t, 'favorite_count', 0) or 0

                try:
                    cur = conn.execute(
                        'INSERT OR IGNORE INTO tweets (tweet_id, screen_name, created_at, created_at_epoch, full_text, in_reply_to_status_id, is_retweet, is_quote, retweet_count, favorite_count, media_json, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                        (str(tweet_id), handle, created_at, epoch, text, str(in_reply) if in_reply else None, 0, is_quote, rt_count, fav_count, media_json, datetime.now().isoformat()))
                    if cur.rowcount > 0:
                        new += 1
                except Exception as e:
                    print(f'  DB error: {e}')

            conn.commit()
            total_new += new

            elapsed = time.time() - start_time
            oldest = str(tweets[-1].created_at)[:10] if tweets else '?'
            print(f'  P{page}: {fetched}件 +{new}new oldest={oldest} total={total_fetched} ({elapsed:.0f}s)')

            if page >= 100:  # Max 100 pages for test
                print('  Reached 100 page limit')
                break

            # Get next page
            try:
                tweets = await tweets.next()
            except Exception as e:
                print(f'  Next page error: {e}')
                break

            time.sleep(1)

    except Exception as e:
        print(f'Error: {e}')
        import traceback
        traceback.print_exc()

    elapsed = time.time() - start_time
    db_after = conn.execute("SELECT COUNT(*) FROM tweets WHERE screen_name=?", (handle,)).fetchone()[0]
    print(f'\n{handle}: fetched={total_fetched}, new={total_new}, DB: {db_before}→{db_after} ({elapsed:.0f}s)')
    conn.close()

asyncio.run(main())
