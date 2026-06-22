#!/usr/bin/env python3
"""
Playwright GraphQL直接ページング
1. 検索ページを開いてSearchTimeline requestを捕捉
2. 捕捉したheaders+URLで直接cursor paginationをpage.evaluate(fetch)で実行
3. UIスクロール不要 → 高速
"""
import json, time, sqlite3, sys, os, re
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'x_tweets.db')
STORAGE_STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'x-storage.json')

conn = sqlite3.connect(DB_PATH)
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA busy_timeout=5000")

def save_tweets(data, handle):
    """GraphQLレスポンスJSONからツイートを抽出して保存"""
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
            # Skip RTs
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

            media = legacy.get('extended_entities', {}).get('media', []) or legacy.get('entities', {}).get('media', [])

            # Parse epoch
            epoch = None
            date_str = legacy.get('created_at', '')
            if date_str:
                try:
                    dt = datetime.strptime(date_str, '%a %b %d %H:%M:%S %z %Y')
                    epoch = int(dt.timestamp() * 1000)
                except:
                    pass

            tweets.append({
                'id': legacy['id_str'],
                'text': legacy['full_text'],
                'date': date_str,
                'epoch': epoch,
                'screen_name': author or handle,
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
        try:
            cur = conn.execute(
                'INSERT OR IGNORE INTO tweets (tweet_id, screen_name, created_at, created_at_epoch, full_text, in_reply_to_status_id, is_retweet, is_quote, retweet_count, favorite_count, media_json, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (t['id'], t['screen_name'], t['date'], t['epoch'], t['text'], t['in_reply_to'], 0, t['is_quote'], t['rt_count'], t['fav_count'], t['media'], datetime.utcnow().isoformat()))
            if cur.rowcount > 0:
                new += 1
        except:
            pass
    conn.commit()
    return new, len(unique)


def fetch_window(page, handle, since, until, captured_url, captured_headers):
    """1つの日付windowをGraphQL直接ページングで取得"""
    # Build search URL for this window
    query = f'from:{handle} since:{since} until:{until} -filter:replies'

    total_new = 0
    total_tweets = 0
    cursor = None

    for pg in range(200):
        # Use page.evaluate to call fetch from browser context
        result = page.evaluate("""async ({ baseUrl, cursor, headers, query }) => {
            try {
                const url = new URL(baseUrl);
                // Update variables with new query and cursor
                const v = JSON.parse(url.searchParams.get('variables'));
                v.rawQuery = query;
                if (cursor) v.cursor = cursor;
                else delete v.cursor;
                url.searchParams.set('variables', JSON.stringify(v));

                const resp = await fetch(url.toString(), {
                    credentials: 'include',
                    headers: {
                        'authorization': headers.authorization,
                        'x-csrf-token': headers['x-csrf-token'],
                        'x-twitter-active-user': 'yes',
                        'x-twitter-auth-type': 'OAuth2Session',
                        'content-type': 'application/json',
                    }
                });

                const status = resp.status;
                const remaining = resp.headers.get('x-rate-limit-remaining');
                const reset = resp.headers.get('x-rate-limit-reset');

                if (status !== 200) {
                    return { status, remaining, reset, data: null };
                }

                const data = await resp.json();
                return { status, remaining, reset, data };
            } catch (e) {
                return { status: -1, error: e.message, data: null };
            }
        }""", {
            'baseUrl': captured_url,
            'cursor': cursor,
            'headers': captured_headers,
            'query': query,
        })

        status = result.get('status')
        remaining = result.get('remaining', '?')
        reset = result.get('reset', '0')

        if status == 429:
            if reset and reset != '0':
                wait = max(int(reset) - int(time.time()) + 5, 60)
                print(f'      429. Waiting {wait}s')
                time.sleep(wait)
                continue
            else:
                print(f'      429. Waiting 900s')
                time.sleep(900)
                continue

        if status == 404:
            print(f'      404 - transaction-id issue. Aborting window.')
            return total_new, total_tweets, 'error_404'

        if status != 200:
            print(f'      HTTP {status}: {result.get("error", "")}')
            return total_new, total_tweets, f'error_{status}'

        data = result.get('data')
        if not data:
            return total_new, total_tweets, 'no_data'

        new, count = save_tweets(data, handle)
        total_new += new
        total_tweets += count

        # Extract bottom cursor
        raw = json.dumps(data)
        cm = re.search(r'"cursor-bottom-[^"]*"[^}]*"value":"([^"]+)"', raw)
        next_cursor = cm.group(1) if cm else None

        if not next_cursor or next_cursor == cursor or count == 0:
            return total_new, total_tweets, 'done'

        cursor = next_cursor
        time.sleep(0.5)  # 0.5秒間隔

    return total_new, total_tweets, 'max_pages'


def run():
    handle = sys.argv[1] if len(sys.argv) > 1 else 'smile_danjer'
    window_days = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    start_date = sys.argv[3] if len(sys.argv) > 3 else '2018-01-01'
    end_date = sys.argv[4] if len(sys.argv) > 4 else '2026-05-08'

    db_before = conn.execute("SELECT COUNT(*) FROM tweets WHERE screen_name=?", (handle,)).fetchone()[0]
    print(f'=== GraphQL Direct: {handle} ({start_date} → {end_date}, {window_days}d windows) ===')
    print(f'DB before: {db_before}')

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=STORAGE_STATE, viewport={'width': 1280, 'height': 900})
        page = context.new_page()

        # Step 1: Capture SearchTimeline request headers
        captured_url = None
        captured_headers = None

        def on_request(req):
            nonlocal captured_url, captured_headers
            if 'SearchTimeline' in req.url and not captured_headers:
                captured_headers = req.headers
                captured_url = req.url

        page.on('request', on_request)

        # Open a search page to trigger SearchTimeline
        init_query = f'from:{handle} since:2025-01-01 until:2025-02-01'
        init_url = f'https://x.com/search?q={init_query}&src=typed_query&f=live'
        print(f'Opening search to capture headers...')
        page.goto(init_url, wait_until='domcontentloaded', timeout=30000)
        page.wait_for_timeout(5000)

        # Scroll once to trigger if needed
        if not captured_url:
            page.mouse.wheel(0, 3000)
            page.wait_for_timeout(3000)

        if not captured_url:
            print('ERROR: Could not capture SearchTimeline request')
            browser.close()
            return

        print(f'Captured SearchTimeline URL and headers.')

        # Step 2: Generate date windows
        d = datetime.strptime(start_date, '%Y-%m-%d')
        e = datetime.strptime(end_date, '%Y-%m-%d')
        windows = []
        while d < e:
            since = d.strftime('%Y-%m-%d')
            d += timedelta(days=window_days)
            if d > e: d = e
            until = d.strftime('%Y-%m-%d')
            windows.append((since, until))

        print(f'{len(windows)} windows to process')

        # Step 3: Fetch each window
        total_new = 0
        for wi, (since, until) in enumerate(windows):
            new, count, status = fetch_window(page, handle, since, until, captured_url, captured_headers)
            total_new += new

            if status == 'error_404':
                print(f'  [{wi+1}/{len(windows)}] {since}→{until}: 404 ERROR - stopping')
                break

            db_now = conn.execute("SELECT COUNT(*) FROM tweets WHERE screen_name=?", (handle,)).fetchone()[0]
            print(f'  [{wi+1}/{len(windows)}] {since}→{until}: +{new}new/{count}total status={status} DB={db_now}')

        browser.close()

    db_after = conn.execute("SELECT COUNT(*) FROM tweets WHERE screen_name=?", (handle,)).fetchone()[0]
    print(f'\n{handle} done: {db_before} → {db_after} (+{db_after - db_before})')
    conn.close()

if __name__ == '__main__':
    run()
