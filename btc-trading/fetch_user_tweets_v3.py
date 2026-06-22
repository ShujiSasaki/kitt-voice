#!/usr/bin/env python3
"""
UserTweets v3 - cursor保存 + route()でcursor差し替え + 高速再開
1. プロフィールを開いてUserTweetsレスポンスを捕捉
2. bottom cursorをDB保存
3. 再開時: page.route()でUserTweetsリクエストのcursorを保存済みcursorに差し替え
4. ブラウザが正しいtransaction-idを生成するので404にならない
"""
import json, time, sqlite3, sys, os, re, urllib.parse
from datetime import datetime
from playwright.sync_api import sync_playwright

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'x_tweets.db')
STORAGE_STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'x-storage.json')

conn = sqlite3.connect(DB_PATH)
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA busy_timeout=5000")

# cursor state table
conn.execute("""CREATE TABLE IF NOT EXISTS cursor_state (
    screen_name TEXT PRIMARY KEY,
    endpoint TEXT NOT NULL,
    bottom_cursor TEXT,
    oldest_tweet_id TEXT,
    oldest_created_at TEXT,
    total_pages INTEGER DEFAULT 0,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
)""")
conn.commit()

handle = sys.argv[1] if len(sys.argv) > 1 else 'BobLoukas'

def extract_and_save(data, target_handle):
    """GraphQLレスポンスからツイート抽出→DB保存、bottom cursor返す"""
    tweets = []
    bottom_cursor = None

    def walk(obj):
        nonlocal bottom_cursor
        if not obj or not isinstance(obj, (dict, list)):
            return
        if isinstance(obj, list):
            for item in obj:
                walk(item)
            return

        # Bottom cursor detection
        eid = obj.get('entryId', '')
        if eid.startswith('cursor-bottom') and obj.get('content', {}).get('value'):
            bottom_cursor = obj['content']['value']
        elif isinstance(obj.get('content'), dict):
            cc = obj['content']
            if cc.get('cursorType') == 'Bottom' and cc.get('value'):
                bottom_cursor = cc['value']

        legacy = obj.get('legacy')
        if legacy and legacy.get('id_str') and legacy.get('full_text'):
            if 'retweeted_status_result' in obj:
                return
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

            epoch = None
            date_str = legacy.get('created_at', '')
            if date_str:
                try:
                    dt = datetime.strptime(date_str, '%a %b %d %H:%M:%S %z %Y')
                    epoch = int(dt.timestamp() * 1000)
                except:
                    pass

            media = legacy.get('extended_entities', {}).get('media', []) or legacy.get('entities', {}).get('media', [])
            tweets.append({
                'id': legacy['id_str'],
                'text': legacy['full_text'],
                'date': date_str,
                'epoch': epoch,
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
    unique = [t for t in tweets if not (t['id'] in seen or seen.add(t['id']))]

    new = 0
    for t in unique:
        # Skip replies to others
        if t['text'].startswith('@') and t.get('in_reply_to'):
            pass  # Keep all for now, filter at analysis time

        try:
            cur = conn.execute(
                'INSERT OR IGNORE INTO tweets (tweet_id, screen_name, created_at, created_at_epoch, full_text, in_reply_to_status_id, is_retweet, is_quote, retweet_count, favorite_count, media_json, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (t['id'], t['screen_name'], t['date'], t['epoch'], t['text'], t['in_reply_to'], 0, t['is_quote'], t['rt_count'], t['fav_count'], t['media'], datetime.now().isoformat()))
            if cur.rowcount > 0:
                new += 1
        except:
            pass
    conn.commit()

    return new, len(unique), bottom_cursor


def run():
    total_new = 0
    total_responses = 0
    rate_limited = False
    rate_reset_at = 0
    last_bottom_cursor = None
    total_pages = 0

    # Check for saved cursor
    saved = conn.execute("SELECT bottom_cursor, total_pages FROM cursor_state WHERE screen_name=?", (handle,)).fetchone()
    saved_cursor = saved[0] if saved else None
    if saved:
        total_pages = saved[1] or 0
    cursor_injected = False  # True after first cursor injection

    db_before = conn.execute("SELECT COUNT(*) FROM tweets WHERE screen_name=?", (handle,)).fetchone()[0]
    print(f'=== UserTweets v3: {handle} ===')
    print(f'DB before: {db_before}')
    if saved_cursor:
        print(f'Resuming from saved cursor (page {total_pages})')
    else:
        print(f'Starting fresh')

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=STORAGE_STATE, viewport={'width': 1280, 'height': 900})
        page = context.new_page()

        def on_response(response):
            nonlocal total_new, total_responses, rate_limited, rate_reset_at, last_bottom_cursor, total_pages
            url = response.url
            if 'UserTweets' not in url:
                return

            status = response.status
            reset = response.headers.get('x-rate-limit-reset', '0')
            remaining = response.headers.get('x-rate-limit-remaining', '?')

            if status == 429:
                rate_limited = True
                rate_reset_at = int(reset) + 5 if reset and reset != '0' else int(time.time()) + 900
                print(f'    429. Reset at {time.strftime("%H:%M", time.localtime(rate_reset_at))} (r={remaining})')
                return

            if status != 200:
                return

            try:
                data = response.json()
                new, count, cursor = extract_and_save(data, handle)
                total_responses += 1
                total_new += new
                total_pages += 1

                if cursor:
                    last_bottom_cursor = cursor
                    # Save cursor to DB
                    conn.execute(
                        "INSERT OR REPLACE INTO cursor_state (screen_name, endpoint, bottom_cursor, total_pages, updated_at) VALUES (?, 'UserTweets', ?, ?, ?)",
                        (handle, cursor, total_pages, datetime.now().isoformat()))
                    conn.commit()

                if total_responses % 5 == 0:
                    db_total = conn.execute("SELECT COUNT(*) FROM tweets WHERE screen_name=?", (handle,)).fetchone()[0]
                    print(f'    Resp #{total_responses}: +{new}new/{count}total (cumul new={total_new}, DB={db_total}, page={total_pages}) r={remaining}')
            except:
                pass

        page.on('response', on_response)

        # Route handler: inject saved cursor into first UserTweets request
        if saved_cursor:
            def route_handler(route):
                nonlocal cursor_injected
                request = route.request
                url = request.url

                if 'UserTweets' in url and not cursor_injected:
                    # Parse URL and inject cursor
                    parsed = urllib.parse.urlparse(url)
                    params = urllib.parse.parse_qs(parsed.query)

                    if 'variables' in params:
                        variables = json.loads(params['variables'][0])
                        variables['cursor'] = saved_cursor
                        params['variables'] = [json.dumps(variables, separators=(',', ':'))]

                        new_query = urllib.parse.urlencode(params, doseq=True)
                        new_url = urllib.parse.urlunparse(parsed._replace(query=new_query))

                        cursor_injected = True
                        print(f'    Injected saved cursor into first UserTweets request')
                        route.continue_(url=new_url)
                        return

                route.continue_()

            page.route('**/UserTweets*', route_handler)

        # Navigate to profile
        print(f'Opening profile page...')
        page.goto(f'https://x.com/{handle}', wait_until='domcontentloaded', timeout=30000)
        page.wait_for_timeout(5000)

        # Scroll loop
        no_response = 0
        last_resp_count = 0
        rate_limit_retries = 0

        for scroll in range(50000):
            if rate_limited:
                rate_limit_retries += 1
                if rate_limit_retries > 50:
                    print(f'    Too many 429s ({rate_limit_retries}), stopping.')
                    break
                wait = max(rate_reset_at - int(time.time()), 60)
                print(f'    Rate limit #{rate_limit_retries}, sleeping {wait}s...')
                page.wait_for_timeout(wait * 1000)
                rate_limited = False
                no_response = 0
                last_resp_count = total_responses
                continue

            page.mouse.wheel(0, 3000)
            page.wait_for_timeout(2000)

            if total_responses > last_resp_count:
                no_response = 0
                last_resp_count = total_responses
            else:
                no_response += 1
                if no_response >= 30:
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
    print(f'Total pages: {total_pages}, Rate limit retries: {rate_limit_retries}')
    if last_bottom_cursor:
        print(f'Last cursor saved for resume')
    conn.close()

if __name__ == '__main__':
    run()
