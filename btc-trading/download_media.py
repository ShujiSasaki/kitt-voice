#!/usr/bin/env python3
"""
投稿の画像をダウンロードしてローカル保存
Usage: python3 download_media.py <screen_name>
"""
import json, sqlite3, sys, os, subprocess, time, hashlib

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'x_tweets.db')
MEDIA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'media')

conn = sqlite3.connect(DB_PATH)
conn.execute("PRAGMA journal_mode=WAL")

# media tracking table
conn.execute("""CREATE TABLE IF NOT EXISTS media_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tweet_id TEXT NOT NULL,
    screen_name TEXT NOT NULL,
    media_type TEXT,
    url TEXT NOT NULL,
    local_path TEXT,
    file_size INTEGER,
    sha256 TEXT,
    status TEXT DEFAULT 'pending',
    error TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tweet_id, url)
)""")
conn.commit()

handle = sys.argv[1] if len(sys.argv) > 1 else 'smile_danjer'
out_dir = os.path.join(MEDIA_DIR, handle)
os.makedirs(out_dir, exist_ok=True)

print(f"=== Downloading media for {handle} ===", flush=True)

# Extract all media URLs from tweets
rows = conn.execute("""
    SELECT tweet_id, media_json FROM tweets
    WHERE screen_name=? AND media_json IS NOT NULL
    ORDER BY created_at_epoch
""", (handle,)).fetchall()

print(f"Tweets with media: {len(rows)}", flush=True)

# Insert into media_files queue
queued = 0
for tweet_id, media_json in rows:
    try:
        media_list = json.loads(media_json)
        if not isinstance(media_list, list):
            continue
        for m in media_list:
            if not isinstance(m, dict):
                continue
            url = m.get('url', '')
            if not url or not url.startswith('http'):
                continue
            media_type = m.get('type', 'photo')
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO media_files (tweet_id, screen_name, media_type, url) VALUES (?, ?, ?, ?)",
                    (tweet_id, handle, media_type, url))
                queued += 1
            except:
                pass
    except:
        pass
conn.commit()
print(f"Media URLs queued: {queued}", flush=True)

# Download pending
pending = conn.execute(
    "SELECT id, tweet_id, url, media_type FROM media_files WHERE screen_name=? AND status='pending'",
    (handle,)
).fetchall()
print(f"Pending downloads: {len(pending)}", flush=True)

done = 0
errors = 0
for i, (mid, tweet_id, url, media_type) in enumerate(pending):
    # Generate filename
    ext = 'jpg'
    if 'png' in url:
        ext = 'png'
    elif 'mp4' in url:
        ext = 'mp4'
    elif 'gif' in url:
        ext = 'gif'

    filename = f"{tweet_id}_{mid}.{ext}"
    local_path = os.path.join(out_dir, filename)

    if os.path.exists(local_path):
        # Already downloaded
        file_size = os.path.getsize(local_path)
        conn.execute(
            "UPDATE media_files SET local_path=?, file_size=?, status='done' WHERE id=?",
            (local_path, file_size, mid))
        done += 1
        continue

    # Download
    try:
        result = subprocess.run(
            ['curl', '-s', '-L', '--max-time', '30', '-o', local_path, url],
            capture_output=True, timeout=45
        )

        if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
            file_size = os.path.getsize(local_path)
            # sha256
            with open(local_path, 'rb') as f:
                sha = hashlib.sha256(f.read()).hexdigest()
            conn.execute(
                "UPDATE media_files SET local_path=?, file_size=?, sha256=?, status='done' WHERE id=?",
                (local_path, file_size, sha, mid))
            done += 1
        else:
            conn.execute(
                "UPDATE media_files SET status='error', error='empty_file' WHERE id=?", (mid,))
            errors += 1
            if os.path.exists(local_path):
                os.remove(local_path)
    except Exception as e:
        conn.execute(
            "UPDATE media_files SET status='error', error=? WHERE id=?", (str(e)[:200], mid))
        errors += 1

    if (i + 1) % 100 == 0:
        conn.commit()
        print(f"  Progress: {i+1}/{len(pending)} (done={done}, errors={errors})", flush=True)

    time.sleep(0.1)  # 軽いスロットリング

conn.commit()
print(f"\n=== Complete: {done} downloaded, {errors} errors ===", flush=True)

# Summary
total = conn.execute("SELECT COUNT(*) FROM media_files WHERE screen_name=?", (handle,)).fetchone()[0]
done_count = conn.execute("SELECT COUNT(*) FROM media_files WHERE screen_name=? AND status='done'", (handle,)).fetchone()[0]
err_count = conn.execute("SELECT COUNT(*) FROM media_files WHERE screen_name=? AND status='error'", (handle,)).fetchone()[0]
pend_count = conn.execute("SELECT COUNT(*) FROM media_files WHERE screen_name=? AND status='pending'", (handle,)).fetchone()[0]
print(f"Total: {total}, Done: {done_count}, Errors: {err_count}, Pending: {pend_count}", flush=True)

# Disk usage
du = subprocess.run(['du', '-sh', out_dir], capture_output=True, text=True)
print(f"Disk: {du.stdout.strip()}", flush=True)

conn.close()
