"""
ロンポチ (@4HpO4Q9Dz3CWkhV) Wayback Machine 取得スクリプト

3者会議 Round 41-43 (戦略Z v11) で確定:
- ロンポチ DNA構築のため Wayback URL 9,874件 (2019-09 〜 2020-09) から
  テキスト本文+画像 を取得して SQLite保管

特徴:
- レート制限: 1.5-3秒間隔 (Wayback Machine 公式マナー)
- 失敗時リトライ: 3回 (1分, 5分, 15分 のexponential backoff)
- 中断耐性: 既に取得済の status_id はスキップ
- 並列実行: 単一スレッド (Wayback Machine BAN回避)
- 画像URL抽出: pbs.twimg.com を Wayback 経由で取得
"""
from __future__ import annotations
import argparse
import hashlib
import json
import logging
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, urlunparse

import requests
from bs4 import BeautifulSoup


# ============================================================
# 設定 (Round 43)
# ============================================================
WAYBACK_BASE = "https://web.archive.org"
URLS_JSON = Path(__file__).parent.parent / "4HpO4Q9Dz3CWkhV_wayback_urls.json"
DATA_DIR = Path(__file__).parent.parent / "btc-trading" / "ronpochi_data"
DB_PATH = DATA_DIR / "ronpochi_posts.db"
IMAGES_DIR = DATA_DIR / "images"
USER_AGENT = (
    "Mozilla/5.0 (compatible; danjer-gaia/1.0; +contact: shuji)"
)
SLEEP_BETWEEN_REQUESTS = 1.8  # 秒、 Wayback マナー範囲
TIMEOUT_SEC = 30
MAX_RETRIES = 3
LOG_EVERY = 50

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("ronpochi_fetch")


# ============================================================
# DB Init
# ============================================================
def init_db() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            status_id TEXT PRIMARY KEY,
            wayback_timestamp TEXT,
            wayback_url TEXT,
            tweet_text TEXT,
            tweet_html TEXT,
            image_count INTEGER DEFAULT 0,
            fetch_status TEXT,
            fetched_at TEXT,
            error TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            status_id TEXT,
            image_url TEXT,
            wayback_image_url TEXT,
            local_path TEXT,
            sha256 TEXT,
            file_size INTEGER,
            fetch_status TEXT,
            fetched_at TEXT,
            error TEXT,
            FOREIGN KEY (status_id) REFERENCES posts (status_id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON posts(status_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_img_status ON images(status_id)")
    conn.commit()
    return conn


# ============================================================
# Wayback URL builder
# ============================================================
def wayback_url(timestamp: str, original: str) -> str:
    """ノーマルWayback URL"""
    return f"{WAYBACK_BASE}/web/{timestamp}/{original}"


def wayback_image_url(timestamp: str, image_url: str) -> str:
    """画像取得用URL (im_ サフィックス、 Wayback 仕様)"""
    return f"{WAYBACK_BASE}/web/{timestamp}im_/{image_url}"


# ============================================================
# HTML fetch
# ============================================================
def fetch_with_retry(url: str, session: requests.Session,
                     binary: bool = False) -> Optional[bytes | str]:
    """Wayback HTTP取得 (リトライ付き)"""
    backoffs = [60, 300, 900]  # 1分、 5分、 15分
    for attempt in range(MAX_RETRIES):
        try:
            r = session.get(url, timeout=TIMEOUT_SEC)
            if r.status_code == 200:
                return r.content if binary else r.text
            if r.status_code == 404:
                return None  # アーカイブなし、 リトライ不要
            if r.status_code == 429 or r.status_code >= 500:
                sleep_for = backoffs[attempt] if attempt < len(backoffs) else 60
                log.warning(f"HTTP {r.status_code} for {url[:80]}; sleep {sleep_for}s")
                time.sleep(sleep_for)
                continue
            log.warning(f"HTTP {r.status_code} for {url[:80]}; skip")
            return None
        except Exception as e:
            sleep_for = backoffs[attempt] if attempt < len(backoffs) else 60
            log.warning(f"exception {e} for {url[:80]}; sleep {sleep_for}s")
            time.sleep(sleep_for)
    return None


# ============================================================
# Tweet HTML parse
# ============================================================
TWEET_TEXT_SELECTORS = [
    'div.permalink-tweet-container .tweet-text',
    'div[data-testid="tweetText"]',
    'p.tweet-text',
    'p.TweetTextSize',
    'div.js-tweet-text-container',
    'article div[lang]',
]


def extract_tweet_text(soup: BeautifulSoup) -> str:
    """複数Twitter HTML フォーマットに対応した本文抽出"""
    for selector in TWEET_TEXT_SELECTORS:
        elements = soup.select(selector)
        if elements:
            texts = [e.get_text(separator=" ", strip=True) for e in elements]
            joined = " ".join(t for t in texts if t)
            if joined and len(joined) > 5:
                return joined
    # フォールバック: og:description
    og = soup.find("meta", property="og:description")
    if og and og.get("content"):
        return og["content"]
    return ""


def extract_image_urls(soup: BeautifulSoup, base_text: str = "") -> list[str]:
    """ツイート画像URL抽出 (pbs.twimg.com のみ)"""
    urls = set()
    # img タグから
    for img in soup.find_all("img"):
        src = img.get("src", "") or img.get("data-src", "")
        if "pbs.twimg.com" in src and "/media/" in src:
            # /web/<timestamp>/<actual_url> の <actual_url> 部分抽出
            cleaned = clean_wayback_prefix(src)
            urls.add(cleaned)
    # og:image
    for og_image in soup.find_all("meta", property="og:image"):
        src = og_image.get("content", "")
        if "pbs.twimg.com" in src and "/media/" in src:
            urls.add(clean_wayback_prefix(src))
    # 本文中のpbs.twimg.com URL
    for m in re.finditer(r"https?://pbs\.twimg\.com/media/[\w\-.?=&%]+", base_text):
        urls.add(m.group(0))
    return list(urls)


def clean_wayback_prefix(url: str) -> str:
    """/web/<timestamp>/ プレフィックスを削除して 元URL取得"""
    m = re.search(r"https?://pbs\.twimg\.com/media/[\w\-.?=&%]+", url)
    if m:
        # ?name=orig付加で原寸取得
        base = m.group(0)
        base = re.sub(r"\?.*$", "", base)
        return f"{base}?name=orig"
    return url


# ============================================================
# Image fetch
# ============================================================
def fetch_image(image_url: str, timestamp: str, status_id: str,
                session: requests.Session) -> Optional[dict]:
    """画像実体取得 (Wayback Machine 経由)"""
    wb_url = wayback_image_url(timestamp, image_url)
    data = fetch_with_retry(wb_url, session, binary=True)
    if not data or len(data) < 100:
        return {"status": "failed", "url": image_url, "wb_url": wb_url}
    sha = hashlib.sha256(data).hexdigest()
    # 拡張子推定
    ext = ".jpg"
    if data.startswith(b"\x89PNG"):
        ext = ".png"
    elif data.startswith(b"GIF8"):
        ext = ".gif"
    elif data.startswith(b"\xff\xd8\xff"):
        ext = ".jpg"
    fname = f"{status_id}_{sha[:12]}{ext}"
    fpath = IMAGES_DIR / fname
    with open(fpath, "wb") as f:
        f.write(data)
    return {
        "status": "ok",
        "url": image_url,
        "wb_url": wb_url,
        "local_path": str(fpath.relative_to(DATA_DIR.parent.parent)),
        "sha256": sha,
        "file_size": len(data),
    }


# ============================================================
# Main loop
# ============================================================
def load_url_list() -> list[dict]:
    with open(URLS_JSON) as f:
        return json.load(f)


def already_fetched(conn: sqlite3.Connection, status_id: str) -> bool:
    cur = conn.execute(
        "SELECT fetch_status FROM posts WHERE status_id = ? AND fetch_status = 'ok'",
        (status_id,),
    )
    return cur.fetchone() is not None


def fetch_post(entry: dict, session: requests.Session,
               conn: sqlite3.Connection, fetch_images: bool = True) -> dict:
    """1ツイート取得"""
    status_id = entry["status_id"]
    timestamp = entry["timestamp"]
    original_url = entry["url"]
    wb_url = wayback_url(timestamp, original_url)

    html_text = fetch_with_retry(wb_url, session)
    if html_text is None:
        conn.execute(
            """INSERT OR REPLACE INTO posts
               (status_id, wayback_timestamp, wayback_url, tweet_text, image_count,
                fetch_status, fetched_at, error)
               VALUES (?, ?, ?, '', 0, 'failed', ?, 'HTTP failed')""",
            (status_id, timestamp, wb_url, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return {"status_id": status_id, "fetch_status": "failed"}

    soup = BeautifulSoup(html_text, "html.parser")
    tweet_text = extract_tweet_text(soup)
    image_urls = extract_image_urls(soup, tweet_text) if fetch_images else []

    # posts レコード
    conn.execute(
        """INSERT OR REPLACE INTO posts
           (status_id, wayback_timestamp, wayback_url, tweet_text, tweet_html,
            image_count, fetch_status, fetched_at, error)
           VALUES (?, ?, ?, ?, ?, ?, 'ok', ?, NULL)""",
        (status_id, timestamp, wb_url, tweet_text, html_text[:200_000],
         len(image_urls), datetime.now(timezone.utc).isoformat()),
    )

    # images レコード+実体取得
    fetched_imgs = 0
    for img_url in image_urls:
        # 重複取得防止
        existing = conn.execute(
            "SELECT id FROM images WHERE status_id = ? AND image_url = ? AND fetch_status = 'ok'",
            (status_id, img_url),
        ).fetchone()
        if existing:
            continue
        time.sleep(SLEEP_BETWEEN_REQUESTS)
        result = fetch_image(img_url, timestamp, status_id, session)
        if result and result["status"] == "ok":
            fetched_imgs += 1
            conn.execute(
                """INSERT INTO images
                   (status_id, image_url, wayback_image_url, local_path,
                    sha256, file_size, fetch_status, fetched_at)
                   VALUES (?, ?, ?, ?, ?, ?, 'ok', ?)""",
                (status_id, img_url, result["wb_url"], result["local_path"],
                 result["sha256"], result["file_size"],
                 datetime.now(timezone.utc).isoformat()),
            )
        else:
            conn.execute(
                """INSERT INTO images
                   (status_id, image_url, wayback_image_url, fetch_status,
                    fetched_at, error)
                   VALUES (?, ?, ?, 'failed', ?, ?)""",
                (status_id, img_url, result.get("wb_url", "") if result else "",
                 datetime.now(timezone.utc).isoformat(),
                 "image_fetch_failed"),
            )
    conn.commit()
    return {
        "status_id": status_id,
        "fetch_status": "ok",
        "text_len": len(tweet_text),
        "image_urls_found": len(image_urls),
        "images_fetched": fetched_imgs,
    }


def main():
    parser = argparse.ArgumentParser(description="ロンポチ Wayback Machine 取得")
    parser.add_argument("--limit", type=int, default=None,
                        help="取得件数 (test時、 例: 10)")
    parser.add_argument("--skip-images", action="store_true",
                        help="画像取得スキップ (テキストのみ)")
    parser.add_argument("--resume-from", type=int, default=0,
                        help="開始位置 (中断後の再開)")
    args = parser.parse_args()

    log.info(f"DB: {DB_PATH}")
    log.info(f"Images dir: {IMAGES_DIR}")
    conn = init_db()

    entries = load_url_list()
    log.info(f"全 {len(entries)}件 のエントリ読み込み")
    if args.resume_from:
        entries = entries[args.resume_from:]
        log.info(f"resume from index {args.resume_from}")
    if args.limit:
        entries = entries[: args.limit]
        log.info(f"limit to {args.limit} entries")

    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    stats = {"ok": 0, "failed": 0, "skipped": 0,
             "images_fetched": 0, "text_total_chars": 0}
    start = time.time()
    for i, entry in enumerate(entries):
        status_id = entry["status_id"]
        if already_fetched(conn, status_id):
            stats["skipped"] += 1
            continue

        result = fetch_post(entry, session, conn,
                            fetch_images=not args.skip_images)
        if result["fetch_status"] == "ok":
            stats["ok"] += 1
            stats["text_total_chars"] += result.get("text_len", 0)
            stats["images_fetched"] += result.get("images_fetched", 0)
        else:
            stats["failed"] += 1

        if (i + 1) % LOG_EVERY == 0:
            elapsed = time.time() - start
            rate = (i + 1) / elapsed
            eta_min = (len(entries) - i - 1) / rate / 60
            log.info(
                f"[{i+1}/{len(entries)}] ok={stats['ok']} "
                f"failed={stats['failed']} skipped={stats['skipped']} "
                f"imgs={stats['images_fetched']} "
                f"rate={rate:.2f}/s ETA={eta_min:.1f}min"
            )

        time.sleep(SLEEP_BETWEEN_REQUESTS)

    log.info(
        f"完了: ok={stats['ok']} failed={stats['failed']} "
        f"skipped={stats['skipped']} imgs={stats['images_fetched']} "
        f"text_total_chars={stats['text_total_chars']:,}"
    )


if __name__ == "__main__":
    main()
