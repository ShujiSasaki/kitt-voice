#!/usr/bin/env python3
"""
gallery-dl subprocess + SQLite永続化 + 再開可能ジョブキュー
複数URLを1プロセスに渡し、stdout逐次読み取り
"""
import json, subprocess, sqlite3, sys, os, time, re
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'x_tweets.db')
PROFILE = sys.argv[1] if len(sys.argv) > 1 else 'Profile 4'

conn = sqlite3.connect(DB_PATH)
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA busy_timeout=5000")

GAPS = {
    'smile_danjer': ('2023-07-01', '2024-05-01'),
    'BobLoukas': ('2021-05-01', '2025-03-01'),
    '_Checkmatey_': ('2020-12-01', '2025-08-01'),
    'LynAldenContact': ('2021-04-01', '2025-06-01'),
    'PeterLBrandt': ('2021-03-01', '2025-10-01'),
}

def generate_urls(handle, start, end, step_days=7):
    urls = []
    d = datetime.strptime(start, '%Y-%m-%d')
    e = datetime.strptime(end, '%Y-%m-%d')
    while d < e:
        since = d.strftime('%Y-%m-%d')
        d += timedelta(days=step_days)
        if d > e: d = e
        until = d.strftime('%Y-%m-%d')
        query = f'from:{handle} since:{since} until:{until}'
        url = f'https://x.com/search?q={query}&f=live'
        urls.append(url)
    return urls

def run_gallery_dl(urls, handle):
    """gallery-dlに複数URLを渡して実行、stdoutから逐次parse"""
    cmd = ['gallery-dl', '--cookies-from-browser', f'chrome:{PROFILE}',
           '--dump-json', '-o', 'sleep-request=19'] + urls

    print(f'  Running gallery-dl with {len(urls)} URLs...')

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    total_new = 0
    buffer = ''

    # stdoutを逐次読み取り
    for line in proc.stdout:
        buffer += line
        # JSON配列の完了を検知(簡易: 最後が]で終わる)
        try:
            data = json.loads(buffer)
            # パース成功 = 1つの完全なJSON配列
            new = save_tweets(data, handle)
            total_new += new
            buffer = ''
        except json.JSONDecodeError:
            continue

    # 残りバッファ
    if buffer.strip():
        try:
            data = json.loads(buffer)
            new = save_tweets(data, handle)
            total_new += new
        except:
            pass

    proc.wait()
    return total_new, proc.returncode

def save_tweets(data, default_handle):
    count = 0
    if not isinstance(data, list):
        return 0

    for item in data:
        if not isinstance(item, list) or len(item) < 2:
            continue
        d = item[1]
        if not isinstance(d, dict):
            continue

        tid = str(d.get('tweet_id', ''))
        if not tid or len(tid) < 10:
            continue

        screen_name = ''
        author = d.get('author', {})
        if isinstance(author, dict):
            screen_name = author.get('name', '')
        if not screen_name:
            screen_name = default_handle

        created_at = str(d.get('date', ''))
        full_text = d.get('content', '') or ''
        in_reply = str(d.get('reply_to', '')) if d.get('reply_to') else None
        is_rt = 1 if d.get('retweet_id') else 0
        is_quote = 1 if d.get('quote_id') else 0
        media = json.dumps(d['media']) if d.get('media') else None

        try:
            cur = conn.execute(
                "INSERT OR IGNORE INTO tweets (tweet_id, screen_name, created_at, full_text, in_reply_to_status_id, is_retweet, is_quote, retweet_count, favorite_count, media_json, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (tid, screen_name, created_at, full_text, in_reply, is_rt, is_quote, d.get('retweet_count', 0), d.get('favorite_count', 0) or d.get('like_count', 0), media, datetime.utcnow().isoformat())
            )
            if cur.rowcount > 0:
                count += 1
        except:
            pass

    conn.commit()
    return count

# === Main ===
target = sys.argv[2] if len(sys.argv) > 2 else None

for handle, (start, end) in GAPS.items():
    if target and handle != target:
        continue

    print(f'\n=== {handle}: {start} → {end} ===')

    urls = generate_urls(handle, start, end, step_days=7)
    print(f'  {len(urls)} weekly jobs')

    db_before = conn.execute("SELECT COUNT(*) FROM tweets WHERE screen_name=?", (handle,)).fetchone()[0]

    # 全URLを1つのgallery-dlプロセスに渡す
    total_new, returncode = run_gallery_dl(urls, handle)

    db_after = conn.execute("SELECT COUNT(*) FROM tweets WHERE screen_name=?", (handle,)).fetchone()[0]
    print(f'\n{handle}: DB {db_before} → {db_after} (+{db_after - db_before}), gallery-dl exit: {returncode}')

conn.close()
print('\n=== Complete ===')
