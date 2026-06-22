#!/usr/bin/env python3
"""
Playwright プロフィールスクロール取得
検索除外アカウント(ronpochi等)用 - UserTweets GraphQLレスポンスを捕捉
"""
import json, time, sqlite3, sys, os
from datetime import datetime
from playwright.sync_api import sync_playwright

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'x_tweets.db')
STORAGE_STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'x-storage.json')

conn = sqlite3.connect(DB_PATH)
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA busy_timeout=5000")

handle = sys.argv[1] if len(sys.argv) > 1 else '4HpO4Q9Dz3CWkhV'

def extract_tweets(data, target_handle):
    """GraphQLレスポンスからツイートを抽出"""
    tweets = []
    def walk(obj):
        if not obj or not isinstance(obj, (dict, list)):
            return
        if isinstance(obj, list):
            for item in obj:
                walk(item)
            return
        legacy = obj.get('legacy')
        if legacy and legacy.get('id_str') and legacy.get('full_text'):
            author = ''
            core = obj.get('core', {})
            if isinstance(core, dict):
                ur = core.get('user_results', core.get('user_result', {}))
                if isinstance(ur, dict):
                    result = ur.get('result', {})
                    if isinstance(result, dict):
                        leg = result.get('legacy', {})
                        if isinstance(leg, dict):
                            author = leg.get('screen_name', '')

            # Skip RTs
            if 'retweeted_status_result' in obj:
                return

            media = legacy.get('extended_entities', {}).get('media', []) or legacy.get('entities', {}).get('media', [])
            tweets.append({
                'id': legacy['id_str'],
                'text': legacy['full_text'],
                'date': legacy.get('created_at', ''),
                'screen_name': author or target_handle,
                'in_reply_to': legacy.get('in_reply_to_status_id_str'),
                'is_quote': 1 if 'quoted_status_result' in obj else 0,
                'rt_count': legacy.get('retweet_count', 0),
                'fav_count': legacy.get('favorite_count', 0),
                'media': json.dumps([{'type': m.get('type'), 'url': m.get('media_url_https')} for m in media]) if media else None,
            })
            return
        for v in obj.values():
            walk(v)
    walk(data)
    seen = set()
    return [t for t in tweets if not (t['id'] in seen or seen.add(t['id']))]

def run():
    total_new = 0
    total_responses = 0
    rate_limited = False
    rate_reset_at = 0  # unix timestamp when rate limit resets

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=STORAGE_STATE, viewport={'width': 1280, 'height': 900})
        page = context.new_page()

        def on_response(response):
            nonlocal total_new, total_responses, rate_limited, rate_reset_at
            url = response.url
            # UserTweets or UserTweetsAndReplies
            if 'UserTweets' not in url and 'UserMedia' not in url:
                return

            status = response.status
            remaining = response.headers.get('x-rate-limit-remaining', '?')
            reset = response.headers.get('x-rate-limit-reset', '0')

            if status == 429:
                rate_limited = True
                rate_reset_at = int(reset) + 5 if reset and reset != '0' else int(time.time()) + 900
                print(f'    429. Reset at {time.strftime("%H:%M", time.localtime(rate_reset_at))}')
                # sleepはメインループ側で管理（on_responseではsleepしない）
                return

            if status != 200:
                return

            try:
                data = response.json()
                tweets = extract_tweets(data, handle)
                total_responses += 1

                new = 0
                for t in tweets:
                    # Skip replies to others
                    if t['text'].startswith('@') and t.get('in_reply_to'):
                        sn = t['text'].split()[0].lstrip('@')
                        if sn.lower() != handle.lower():
                            continue

                    # Parse epoch
                    epoch = None
                    if t['date']:
                        try:
                            dt = datetime.strptime(t['date'], '%a %b %d %H:%M:%S %z %Y')
                            epoch = int(dt.timestamp() * 1000)
                        except:
                            pass

                    try:
                        cur = conn.execute(
                            'INSERT OR IGNORE INTO tweets (tweet_id, screen_name, created_at, created_at_epoch, full_text, in_reply_to_status_id, is_retweet, is_quote, retweet_count, favorite_count, media_json, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                            (t['id'], t['screen_name'] or handle, t['date'], epoch, t['text'], t['in_reply_to'], 0, t['is_quote'], t['rt_count'], t['fav_count'], t['media'], datetime.utcnow().isoformat()))
                        if cur.rowcount > 0:
                            new += 1
                    except:
                        pass
                conn.commit()
                total_new += new
                if total_responses % 5 == 0:
                    db_total = conn.execute("SELECT COUNT(*) FROM tweets WHERE screen_name=?", (handle,)).fetchone()[0]
                    print(f'    Resp #{total_responses}: +{new} new (total new: {total_new}, DB: {db_total})')
            except:
                pass

        page.on('response', on_response)

        print(f'=== {handle} profile scroll ===')
        db_before = conn.execute("SELECT COUNT(*) FROM tweets WHERE screen_name=?", (handle,)).fetchone()[0]
        print(f'DB before: {db_before}')

        # Navigate to profile
        page.goto(f'https://x.com/{handle}', wait_until='domcontentloaded', timeout=30000)
        page.wait_for_timeout(5000)

        # Scroll loop - total_responsesベースで判定
        no_response = 0
        last_resp_count = 0
        rate_limit_retries = 0

        for scroll in range(50000):  # 大量スクロール対応
            # 429待機→スクロール位置保持したまま待つ→再開
            if rate_limited:
                rate_limit_retries += 1
                if rate_limit_retries > 20:
                    print(f'    Too many 429s ({rate_limit_retries}), stopping.')
                    break
                wait = max(rate_reset_at - int(time.time()), 60)
                print(f'    Rate limit #{rate_limit_retries}, sleeping {wait}s (keeping scroll position)...')
                page.wait_for_timeout(wait * 1000)  # ブラウザ内で待機（スクロール位置保持）
                rate_limited = False
                no_response = 0
                last_resp_count = total_responses
                # スクロール再開（continueでループに戻る）
                continue

            page.mouse.wheel(0, 3000)
            page.wait_for_timeout(2000)

            # レスポンスが来ていればスクロール続行
            if total_responses > last_resp_count:
                no_response = 0
                last_resp_count = total_responses
            else:
                no_response += 1
                if no_response >= 30:  # 60秒レスポンスなし→ページ末尾到達
                    print(f'    No new responses for {no_response * 2}s, stopping.')
                    break

            if scroll % 100 == 0 and scroll > 0:
                elapsed_min = scroll * 2 / 60
                db_current = conn.execute("SELECT COUNT(*) FROM tweets WHERE screen_name=?", (handle,)).fetchone()[0]
                print(f'    Scroll #{scroll} ({elapsed_min:.0f}min): DB={db_current}, +{db_current - db_before} new, resp={total_responses}')

        page.close()
        browser.close()

    db_after = conn.execute("SELECT COUNT(*) FROM tweets WHERE screen_name=?", (handle,)).fetchone()[0]
    print(f'\n{handle} done: {db_before} → {db_after} (+{db_after - db_before})')
    conn.close()

if __name__ == '__main__':
    run()
