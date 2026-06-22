#!/usr/bin/env node
/**
 * ツイート画像/動画URL一括取得 (fxtwitter API)
 * pic.twitter.com含むツイートのみ対象
 * 画像URLを既存のtweets.jsonに追記
 */

const fs = require('fs');
const path = require('path');

const OUT_DIR = __dirname;
const CONCURRENCY = 3;
const DELAY = 300; // ms between requests

const ACCOUNTS = [
  'smile_danjer',
  '4HpO4Q9Dz3CWkhV',
  'CryptoHayes',
  '_Checkmatey_',
  'BobLoukas',
  'LynAldenContact',
  'PeterLBrandt',
];

async function fetchMedia(handle, statusId) {
  const url = `https://api.fxtwitter.com/${handle}/status/${statusId}`;
  try {
    const res = await fetch(url, { signal: AbortSignal.timeout(10000) });
    if (!res.ok) return null;
    const data = await res.json();
    const tweet = data.tweet || {};
    const media = tweet.media || {};
    const result = { photos: [], videos: [] };

    if (media.photos) {
      for (const p of media.photos) {
        result.photos.push({
          url: p.url,
          width: p.width,
          height: p.height
        });
      }
    }
    if (media.videos) {
      for (const v of media.videos) {
        result.videos.push({
          url: v.url,
          thumbnail: v.thumbnail_url,
          width: v.width,
          height: v.height,
          duration: v.duration
        });
      }
    }

    // fxtwitter returns created_at which is more reliable
    const created_at = tweet.created_at || null;

    return { media: result, created_at };
  } catch (e) {
    return null;
  }
}

async function parallelMap(items, fn, concurrency, delayMs) {
  const results = [];
  let idx = 0;

  async function worker() {
    while (idx < items.length) {
      const i = idx++;
      results[i] = await fn(items[i], i);
      if (delayMs > 0) await new Promise(r => setTimeout(r, delayMs));
    }
  }

  const workers = [];
  for (let i = 0; i < Math.min(concurrency, items.length); i++) {
    workers.push(worker());
  }
  await Promise.all(workers);
  return results;
}

async function processAccount(handle) {
  const tweetsFile = path.join(OUT_DIR, `${handle}_tweets.json`);
  if (!fs.existsSync(tweetsFile)) {
    console.log(`  [SKIP] ${tweetsFile} not found`);
    return;
  }

  const data = JSON.parse(fs.readFileSync(tweetsFile, 'utf8'));
  const tweets = data.tweets;

  // pic.twitter.com含むツイートをフィルタ
  const mediaTweets = tweets.filter(t =>
    t.text && t.text.includes('pic.twitter.com') && !t.media
  );

  console.log(`  Total: ${tweets.length}, with media: ${mediaTweets.length} (already fetched: ${tweets.filter(t => t.media).length})`);

  if (mediaTweets.length === 0) {
    console.log(`  Nothing to fetch.`);
    return;
  }

  let fetched = 0;
  let ok = 0;
  let fail = 0;

  const results = await parallelMap(mediaTweets, async (tweet, i) => {
    const result = await fetchMedia(handle, tweet.status_id);
    fetched++;
    if (result && (result.media.photos.length > 0 || result.media.videos.length > 0)) {
      tweet.media = result.media;
      if (result.created_at) tweet.created_at = result.created_at;
      ok++;
    } else {
      fail++;
    }
    if (fetched % 100 === 0) {
      process.stdout.write(`\r  Progress: ${fetched}/${mediaTweets.length} (ok: ${ok}, fail: ${fail})`);
    }
    return result;
  }, CONCURRENCY, DELAY);

  // 統計
  let totalPhotos = 0;
  let totalVideos = 0;
  for (const t of tweets) {
    if (t.media) {
      totalPhotos += (t.media.photos || []).length;
      totalVideos += (t.media.videos || []).length;
    }
  }

  data.media_stats = {
    tweets_with_media: tweets.filter(t => t.media).length,
    total_photos: totalPhotos,
    total_videos: totalVideos,
    media_fetch_failed: fail,
    last_media_update: new Date().toISOString()
  };

  fs.writeFileSync(tweetsFile, JSON.stringify(data, null, 2));
  console.log(`\n  DONE: ${ok} media fetched (${totalPhotos} photos, ${totalVideos} videos, ${fail} failed)`);
}

async function main() {
  const targetHandle = process.argv[2];

  console.log('=== Media URL Fetcher ===\n');

  for (const handle of ACCOUNTS) {
    if (targetHandle && handle !== targetHandle) continue;
    console.log(`\n[${handle}]`);
    await processAccount(handle);
  }

  console.log('\n=== Complete ===');
}

main().catch(console.error);
