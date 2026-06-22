#!/usr/bin/env python3
"""
Playwright高速取得 - SearchTimeline response捕捉 + スクロール
50req/15min = 4,000件/時
月単位検索 → スクロールでpagination → 429で15分sleep → 再開
"""
import json, time, sqlite3, sys, os
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'x_tweets.db')
STORAGE_STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'x-storage.json')

# 欠落期間
GAPS = {
    'smile_danjer': ('2023-07-01', '2024-05-01'),
    'BobLoukas': ('2021-05-01', '2025-03-01'),
    '_Checkmatey_': ('2020-12-01', '2025-08-01'),
    'LynAldenContact': ('2021-04-01', '2025-06-01'),
    'PeterLBrandt': ('2021-03-01', '2025-10-01'),
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

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=STORAGE_STATE, viewport={'width': 1280, 'height': 900})

        for handle, (start, end) in GAPS.items():
            if target and handle != target:
                continue

            windows = generate_windows(start, end, days=window_days)
            print(f'\n=== {handle}: {start} → {end} ({len(windows)} windows) ===')
            db_before = conn.execute("SELECT COUNT(*) FROM tweets WHERE screen_name=?", (handle,)).fetchone()[0]

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
                                tweets.append({
                                    'id': legacy['id_str'],
                                    'text': legacy['full_text'],
                                    'date': legacy.get('created_at', ''),
                                    'screen_name': handle,
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
                                    'INSERT OR IGNORE INTO tweets (tweet_id, screen_name, created_at, full_text, fetched_at) VALUES (?, ?, ?, ?, ?)',
                                    (t['id'], handle, t['date'], t['text'], datetime.utcnow().isoformat()))
                                if cur.rowcount > 0: new += 1
                            except: pass
                        conn.commit()
                        total_new += new
                        response_count += 1
                    except: pass

                page.on('response', on_response)

                query = f'from:{handle} since:{since} until:{until}'
                url = f'https://x.com/search?q={query}&src=typed_query&f=live'
                page.goto(url, wait_until='domcontentloaded', timeout=30000)
                page.wait_for_timeout(5000)

                # スクロールループ
                last_total = conn.execute("SELECT COUNT(*) FROM tweets WHERE screen_name=?", (handle,)).fetchone()[0]
                no_new = 0

                for scroll in range(500):
                    if rate_limited:
                        rate_limited = False
                        page.reload(wait_until='domcontentloaded', timeout=30000)
                        page.wait_for_timeout(5000)
                        no_new = 0

                    page.mouse.wheel(0, 3000)
                    page.wait_for_timeout(3000)

                    current = conn.execute("SELECT COUNT(*) FROM tweets WHERE screen_name=?", (handle,)).fetchone()[0]
                    if current == last_total:
                        no_new += 1
                        if no_new >= 10:
                            break
                    else:
                        no_new = 0
                        last_total = current

                page.close()

                db_now = conn.execute("SELECT COUNT(*) FROM tweets WHERE screen_name=?", (handle,)).fetchone()[0]
                print(f'  [{wi+1}/{len(windows)}] {since}→{until}: +{total_new} new, {response_count} responses, DB: {db_now}')

            db_after = conn.execute("SELECT COUNT(*) FROM tweets WHERE screen_name=?", (handle,)).fetchone()[0]
            print(f'\n{handle} done: {db_before} → {db_after} (+{db_after - db_before})')

        browser.close()
    conn.close()
    print('\n=== Complete ===')

if __name__ == '__main__':
    run()
