#!/usr/bin/env node
/**
 * ツイート画像/動画を一括ダウンロード→/tmpに一時保存→gcloud storage cp -r で一括GCSアップ
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const BUCKET = 'gs://btc-research-0549297663';
const CONCURRENCY = 10;
const DELAY = 50;

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
  await Promise.all(Array.from({ length: Math.min(concurrency, items.length) }, () => worker()));
  return results;
}

async function processAccount(handle) {
  const tweetsFile = path.join(__dirname, `${handle}_tweets.json`);
  if (!fs.existsSync(tweetsFile)) return;

  const data = JSON.parse(fs.readFileSync(tweetsFile, 'utf8'));
  const tmpDir = `/tmp/btc-media-${handle}`;

  // 既にGCSにアップ済みか確認
  try {
    const count = execSync(`gcloud storage ls "${BUCKET}/media/${handle}/" 2>/dev/null | wc -l`, { timeout: 15000 }).toString().trim();
    if (parseInt(count) > 100) {
      console.log(`  Already ${count} files in GCS. Skipping.`);
      return;
    }
  } catch (e) {}

  // /tmpにディレクトリ作成
  if (fs.existsSync(tmpDir)) execSync(`rm -rf "${tmpDir}"`);
  fs.mkdirSync(tmpDir, { recursive: true });

  // メディアアイテム収集
  const items = [];
  for (const tweet of data.tweets) {
    if (!tweet.media) continue;
    const sid = tweet.status_id;
    for (let i = 0; i < (tweet.media.photos || []).length; i++) {
      const p = tweet.media.photos[i];
      const ext = p.url.includes('.png') ? 'png' : 'jpg';
      items.push({ url: p.url, filename: `${sid}_p${i}.${ext}` });
    }
    for (let i = 0; i < (tweet.media.videos || []).length; i++) {
      const v = tweet.media.videos[i];
      if (v.url) items.push({ url: v.url, filename: `${sid}_v${i}.mp4` });
    }
  }

  console.log(`  ${items.length} files to download`);
  let ok = 0, fail = 0;

  // Phase 1: /tmpにダウンロード
  await parallelMap(items, async (item, i) => {
    try {
      const res = await fetch(item.url, { signal: AbortSignal.timeout(30000) });
      if (!res.ok) { fail++; return; }
      const buf = Buffer.from(await res.arrayBuffer());
      fs.writeFileSync(path.join(tmpDir, item.filename), buf);
      ok++;
    } catch (e) { fail++; }
    if ((ok + fail) % 100 === 0) {
      process.stdout.write(`\r  Download: ${ok + fail}/${items.length} (ok: ${ok}, fail: ${fail})`);
    }
  }, CONCURRENCY, DELAY);

  console.log(`\n  Downloaded: ${ok} ok, ${fail} fail`);

  // Phase 2: 一括GCSアップロード
  console.log(`  Uploading to GCS...`);
  try {
    execSync(`gcloud storage cp -r "${tmpDir}/*" "${BUCKET}/media/${handle}/" --quiet 2>&1`, {
      timeout: 600000,
      maxBuffer: 50 * 1024 * 1024
    });
    console.log(`  GCS upload complete!`);
  } catch (e) {
    console.log(`  GCS upload error: ${e.message.substring(0, 200)}`);
  }

  // Phase 3: /tmp削除
  execSync(`rm -rf "${tmpDir}"`);
  console.log(`  Temp files cleaned.`);
}

async function main() {
  const target = process.argv[2];
  console.log('=== Batch Media Download -> GCS ===\n');

  const accounts = ['smile_danjer', '4HpO4Q9Dz3CWkhV', 'CryptoHayes', '_Checkmatey_', 'BobLoukas', 'LynAldenContact', 'PeterLBrandt'];

  for (const handle of accounts) {
    if (target && handle !== target) continue;
    console.log(`\n[${handle}]`);
    await processAccount(handle);
  }
  console.log('\n=== Complete ===');
}

main().catch(console.error);
