#!/usr/bin/env python3
"""
Playwright高速取得 v2 - SearchTimeline response捕捉 + スクロール
改善: メディアブロック / 2秒間隔 / -filter:replies / epoch保存 / 全期間
Usage: python3 fetch_fast_v2.py <handle> [window_days] [start_date] [end_date]
"""
import json, time, sqlite3, sys, os
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'x_tweets.db')
STORAGE_STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'x-storage.json')

# 全期間 (アカウント開設〜現在)
FULL_RANGES = {
    'CryptoHayes': ('2018-03-01', '2026-05-16'),
    'smile_danjer': ('2015-01-01', '2026-05-16'),
    'BobLoukas': ('2008-01-01', '2026-05-16'),
    '_Checkmatey_': ('2018-01-01', '2026-05-16'),
    'LynAldenContact': ('2017-01-01', '2026-05-16'),
    'PeterLBrandt': ('2014-01-01', '2026-05-16'),
    '4HpO4Q9Dz3CWkhV': ('2019-09-01', '2026-05-16'),
}

def generate_windows(start, end, days=30):
    windows = []
    d = datetime.strptime(start, '%Y-%m-%d')
    e = datetime.strptime(end, '%Y-%m-%d')
    while d < e:
        since = d.strftime('%Y-%m-%d')
        d += timedelta(days=days)
        if d > e: d = e
        until = d.strftime('%Y-%m-%d')
        windows.append((since, until))
    return windows

def run():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")

    target = sys.argv[1] if len(sys.argv) > 1 else None
    window_days = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    custom_start = sys.argv[3] if len(sys.argv) > 3 else None
    custom_end = sys.argv[4] if len(sys.argv) > 4 else None

    if not target:
        print("Usage: python3 fetch_fast_v2.py <handle> [window_days] [start] [end]")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=STORAGE_STATE, viewport={'width': 1280, 'height': 900})

        # Block non-essential resources (analytics, fonts) to speed up
        # Note: 画像/動画URLはGraphQL JSONレスポンスから取得済み。ブラウザ描画用だけブロック
        context.route("**/analytics.twitter.com/**", lambda route: route.abort())
        context.route("**/*.{woff,woff2,ttf,eot}", lambda route: route.abort())

        for handle, (default_start, default_end) in FULL_RANGES.items():
            if handle != target:
                continue

            start = custom_start or default_start
            end = custom_end or default_end

            windows = generate_windows(start, end, days=window_days)
            db_before = conn.execute("SELECT COUNT(*) FROM tweets WHERE screen_name=?", (handle,)).fetchone()[0]
            print(f'\n=== {handle}: {start} → {end} ({len(windows)} windows, {window_days}d each) ===')
            print(f'DB before: {db_before}')

            for wi, (since, until) in enumerate(windows):
                page = context.new_page()
                total_new = 0
                response_count = 0
                rate_limited = False

                def on_response(response):
                    nonlocal total_new, response_count, rate_limited
                    if 'SearchTimeline' not in response.url:
                        return
                    status = response.status
                    remaining = response.headers.get('x-rate-limit-remaining', '?')
                    reset = response.headers.get('x-rate-limit-reset', '0')

                    if status == 429:
                        rate_limited = True
                        wait = max(int(reset) - int(time.time()) + 5, 60)
                        print(f'    429. Waiting {wait}s (reset: {time.strftime("%H:%M", time.localtime(int(reset)))})')
                        time.sleep(wait)
                        return

                    if status != 200:
                        return

                    try:
                        data = response.json()
                        tweets = []
                        def walk(obj):
                            if not obj or not isinstance(obj, (dict, list)): return
                            if isinstance(obj, list):
                                for i in obj: walk(i)
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

                                # Parse epoch
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
                                    'screen_name': author or handle,
                                    'in_reply_to': legacy.get('in_reply_to_status_id_str'),
                                    'is_quote': 1 if 'quoted_status_result' in obj else 0,
                                    'rt_count': legacy.get('retweet_count', 0),
                                    'fav_count': legacy.get('favorite_count', 0),
                                    'media': json.dumps([{'type': m.get('type'), 'url': m.get('media_url_https')} for m in media]) if media else None,
                                })
                                return
                            for v in obj.values(): walk(v)
                        walk(data)

                        seen = set()
                        unique = [t for t in tweets if not (t['id'] in seen or seen.add(t['id']))]

                        new = 0
                        for t in unique:
                            try:
                                cur = conn.execute(
                                    'INSERT OR IGNORE INTO tweets (tweet_id, screen_name, created_at, created_at_epoch, full_text, in_reply_to_status_id, is_retweet, is_quote, retweet_count, favorite_count, media_json, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                                    (t['id'], t['screen_name'], t['date'], t['epoch'], t['text'], t['in_reply_to'], 0, t['is_quote'], t['rt_count'], t['fav_count'], t['media'], datetime.now().isoformat()))
                                if cur.rowcount > 0: new += 1
                            except: pass
                        conn.commit()
                        total_new += new
                        response_count += 1
                    except: pass

                page.on('response', on_response)

                # Use -filter:replies to exclude replies from search
                query = f'from:{handle} since:{since} until:{until} -filter:replies'
                url = f'https://x.com/search?q={query}&src=typed_query&f=live'
                try:
                    page.goto(url, wait_until='domcontentloaded', timeout=30000)
                except:
                    page.close()
                    continue
                page.wait_for_timeout(3000)

                # Scroll loop - faster interval
                last_total = conn.execute("SELECT COUNT(*) FROM tweets WHERE screen_name=?", (handle,)).fetchone()[0]
                no_new = 0

                for scroll in range(500):
                    if rate_limited:
                        rate_limited = False
                        try:
                            page.reload(wait_until='domcontentloaded', timeout=30000)
                        except:
                            break
                        page.wait_for_timeout(3000)
                        no_new = 0

                    page.mouse.wheel(0, 4000)
                    page.wait_for_timeout(2000)  # 2秒間隔 (3秒→2秒に短縮)

                    current = conn.execute("SELECT COUNT(*) FROM tweets WHERE screen_name=?", (handle,)).fetchone()[0]
                    if current == last_total:
                        no_new += 1
                        if no_new >= 8:  # 16秒新規なし→次のwindow
                            break
                    else:
                        no_new = 0
                        last_total = current

                page.close()

                db_now = conn.execute("SELECT COUNT(*) FROM tweets WHERE screen_name=?", (handle,)).fetchone()[0]
                print(f'  [{wi+1}/{len(windows)}] {since}→{until}: +{total_new} new, {response_count} resp, DB: {db_now}')

            db_after = conn.execute("SELECT COUNT(*) FROM tweets WHERE screen_name=?", (handle,)).fetchone()[0]
            print(f'\n{handle} done: {db_before} → {db_after} (+{db_after - db_before})')

        browser.close()
    conn.close()
    print('\n=== Complete ===')

if __name__ == '__main__':
    run()
