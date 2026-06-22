#!/usr/bin/env node
/**
 * ツイート画像/動画をpbs.twimg.comからダウンロードしてGCSにアップロード
 * ローカルには保存しない（ストリーミング転送）
 */

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const BUCKET = 'gs://btc-research-0549297663';
const CONCURRENCY = 5;
const DELAY = 100; // ms

const ACCOUNTS = [
  'smile_danjer',
  '4HpO4Q9Dz3CWkhV',
  'CryptoHayes',
  '_Checkmatey_',
  'BobLoukas',
  'LynAldenContact',
  'PeterLBrandt',
];

async function downloadAndUpload(url, gcsPath) {
  try {
    const res = await fetch(url, { signal: AbortSignal.timeout(30000) });
    if (!res.ok) return false;
    const buffer = Buffer.from(await res.arrayBuffer());

    // /tmpに一時保存してgsutil cp
    const tmpFile = `/tmp/media_${Date.now()}_${Math.random().toString(36).slice(2)}`;
    fs.writeFileSync(tmpFile, buffer);
    execSync(`gcloud storage cp "${tmpFile}" "${gcsPath}" --quiet 2>/dev/null`, { timeout: 15000 });
    fs.unlinkSync(tmpFile);
    return true;
  } catch (e) {
    return false;
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
  const tweetsFile = path.join(__dirname, `${handle}_tweets.json`);
  if (!fs.existsSync(tweetsFile)) {
    console.log(`  [SKIP] not found`);
    return;
  }

  const data = JSON.parse(fs.readFileSync(tweetsFile, 'utf8'));

  // media付きツイートを収集
  const mediaItems = [];
  for (const tweet of data.tweets) {
    if (!tweet.media) continue;
    const sid = tweet.status_id;

    for (let i = 0; i < (tweet.media.photos || []).length; i++) {
      const photo = tweet.media.photos[i];
      const ext = photo.url.includes('.png') ? 'png' : 'jpg';
      mediaItems.push({
        url: photo.url,
        gcsPath: `${BUCKET}/media/${handle}/${sid}_photo_${i}.${ext}`,
        type: 'photo'
      });
    }
    for (let i = 0; i < (tweet.media.videos || []).length; i++) {
      const video = tweet.media.videos[i];
      if (video.url) {
        mediaItems.push({
          url: video.url,
          gcsPath: `${BUCKET}/media/${handle}/${sid}_video_${i}.mp4`,
          type: 'video'
        });
      }
    }
  }

  // 既にアップ済みか確認(先頭のみ)
  if (mediaItems.length > 0) {
    try {
      const check = execSync(`gcloud storage ls "${BUCKET}/media/${handle}/" --quiet 2>/dev/null | head -5`, { timeout: 10000 }).toString();
      const existingCount = check.split('\n').filter(l => l.trim()).length;
      if (existingCount > mediaItems.length * 0.9) {
        console.log(`  Already uploaded (~${existingCount} files). Skipping.`);
        return;
      }
    } catch (e) {}
  }

  console.log(`  ${mediaItems.length} media files to upload`);
  let ok = 0, fail = 0;

  await parallelMap(mediaItems, async (item, i) => {
    const success = await downloadAndUpload(item.url, item.gcsPath);
    if (success) ok++; else fail++;
    if ((ok + fail) % 50 === 0) {
      process.stdout.write(`\r  Progress: ${ok + fail}/${mediaItems.length} (ok: ${ok}, fail: ${fail})`);
    }
  }, CONCURRENCY, DELAY);

  console.log(`\n  DONE: ${ok} uploaded, ${fail} failed`);
}

async function main() {
  const target = process.argv[2];
  console.log('=== Media Download -> GCS ===\n');

  for (const handle of ACCOUNTS) {
    if (target && handle !== target) continue;
    console.log(`\n[${handle}]`);
    await processAccount(handle);
  }
  console.log('\n=== Complete ===');
}

main().catch(console.error);
