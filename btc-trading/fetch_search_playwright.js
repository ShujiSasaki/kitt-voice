#!/usr/bin/env node
/**
 * SearchTimeline取得 - Playwright UIスクロール方式
 * Node.js fetchではなくChromium内でX公式クライアントにリクエストさせる
 * GraphQL responseを捕捉してSQLiteに保存
 */

const fs = require('fs');
const path = require('path');
const Database = require('better-sqlite3');
const { chromium } = require('playwright');

// === Config ===
const envFile = fs.readFileSync(path.join(__dirname, '..', '.env'), 'utf8');
const CT0 = envFile.match(/X_CT0=(.+)/)?.[1]?.trim();
const AUTH = envFile.match(/X_AUTH_TOKEN=(.+)/)?.[1]?.trim();

// === SQLite ===
const DB_PATH = path.join(__dirname, 'x_tweets.db');
const db = new Database(DB_PATH);
db.pragma('journal_mode = WAL');

db.exec(`
  CREATE TABLE IF NOT EXISTS tweets (
    tweet_id TEXT PRIMARY KEY,
    screen_name TEXT,
    created_at TEXT,
    full_text TEXT,
    in_reply_to_status_id TEXT,
    is_retweet INTEGER DEFAULT 0,
    is_quote INTEGER DEFAULT 0,
    retweet_count INTEGER,
    favorite_count INTEGER,
    media_json TEXT,
    raw_json TEXT,
    fetched_at TEXT
  );
  CREATE INDEX IF NOT EXISTS idx_tweets_screen ON tweets(screen_name);
`);

const insertTweet = db.prepare(`INSERT OR IGNORE INTO tweets (tweet_id, screen_name, created_at, full_text, in_reply_to_status_id, is_retweet, is_quote, retweet_count, favorite_count, media_json, raw_json, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`);
const countForUser = db.prepare(`SELECT COUNT(*) as c FROM tweets WHERE screen_name = ?`);

function extractTweets(data, targetScreen) {
  const tweets = [];
  function walk(obj) {
    if (!obj || typeof obj !== 'object') return;
    if (obj.legacy?.id_str && obj.legacy?.full_text) {
      const l = obj.legacy;
      const author = obj.core?.user_results?.result?.legacy?.screen_name;
      if (!targetScreen || (author && author.toLowerCase() === targetScreen.toLowerCase())) {
        const media = l.extended_entities?.media || l.entities?.media || [];
        tweets.push({
          tweet_id: l.id_str,
          screen_name: author || targetScreen,
          created_at: l.created_at,
          full_text: l.full_text,
          in_reply_to_status_id: l.in_reply_to_status_id_str || null,
          is_retweet: l.retweeted_status_result ? 1 : 0,
          is_quote: obj.quoted_status_result ? 1 : 0,
          retweet_count: l.retweet_count || 0,
          favorite_count: l.favorite_count || 0,
          media_json: media.length > 0 ? JSON.stringify(media.map(m => ({
            type: m.type, url: m.media_url_https,
            video_url: m.video_info?.variants?.find(v => v.content_type === 'video/mp4')?.url
          }))) : null,
        });
      }
      return;
    }
    if (Array.isArray(obj)) { obj.forEach(walk); return; }
    for (const v of Object.values(obj)) walk(v);
  }
  walk(data);
  const seen = new Set();
  return tweets.filter(t => { if (seen.has(t.tweet_id)) return false; seen.add(t.tweet_id); return true; });
}

async function fetchAccount(screenName, startDate) {
  console.log(`\n[${screenName}] Starting Playwright search...`);

  const storagePath = path.join(__dirname, 'x-storage.json');
  if (!fs.existsSync(storagePath)) {
    console.log('  x-storage.json not found. Run login first.');
    return;
  }
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    storageState: storagePath,
    viewport: { width: 1280, height: 900 },
  });

  const page = await context.newPage();
  let totalNew = 0;
  let responseCount = 0;
  let rateLimitHits = 0;

  // GraphQL response捕捉
  page.on('response', async (response) => {
    const url = response.url();
    if (!url.includes('SearchTimeline')) return;

    try {
      const status = response.status();
      if (status === 429) {
        rateLimitHits++;
        let body = '';
        try { body = await response.text(); } catch {}
        console.log(`  SearchTimeline 429 (hit #${rateLimitHits}): ${body.substring(0, 100)}`);
        return;
      }
      if (status !== 200) {
        let body = '';
        try { body = await response.text(); } catch {}
        console.log(`  SearchTimeline ${status}: ${body.substring(0, 200)}`);
        return;
      }
      rateLimitHits = 0; // 200成功でリセット
      const data = await response.json();
      const tweets = extractTweets(data, screenName);
      responseCount++;

      const tx = db.transaction(() => {
        let n = 0;
        for (const t of tweets) {
          const c = insertTweet.run(t.tweet_id, t.screen_name, t.created_at, t.full_text,
            t.in_reply_to_status_id, t.is_retweet, t.is_quote, t.retweet_count,
            t.favorite_count, t.media_json, null, new Date().toISOString());
          if (c.changes > 0) n++;
        }
        return n;
      });
      const newCount = tx();
      totalNew += newCount;

      if (responseCount % 5 === 0) {
        const total = countForUser.get(screenName).c;
        process.stdout.write(`\r  [${screenName}] responses: ${responseCount}, DB: ${total}, new: ${totalNew}`);
      }
    } catch (e) {
      // response already consumed or parse error
    }
  });

  // ログイン確認(homeを先に開く)
  await page.goto('https://x.com/home', { waitUntil: 'domcontentloaded', timeout: 30000 });
  const homeUrl = page.url();
  if (homeUrl.includes('/login') || homeUrl.includes('/i/flow/login')) {
    console.log('  NOT LOGGED IN. Stopping.');
    await browser.close();
    return;
  }
  console.log('  Logged in OK');
  await page.waitForTimeout(2000);

  // 検索クエリ(日付付き)
  const query = startDate
    ? `from:${screenName} since:${startDate}`
    : `from:${screenName}`;
  const searchUrl = `https://x.com/search?q=${encodeURIComponent(query)}&src=typed_query&f=live`;

  console.log(`  URL: ${searchUrl}`);
  await page.goto(searchUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.waitForTimeout(3000);

  // スクロールループ
  let noNewCount = 0;
  let lastTotal = countForUser.get(screenName).c;
  let maxScrolls = 5000; // 安全弁

  for (let i = 0; i < maxScrolls; i++) {
    await page.mouse.wheel(0, 3000);
    // 通常: 30-90s jitter。429が出たら指数バックオフ
    let waitMs;
    if (rateLimitHits === 0) {
      waitMs = 18000 + Math.random() * 7000; // 18-25s (50req/15min)
    } else if (rateLimitHits === 1) {
      waitMs = 15 * 60000; // 15min
      console.log(`\n  429 detected. Backing off 15min...`);
    } else if (rateLimitHits === 2) {
      waitMs = 30 * 60000; // 30min
      console.log(`\n  429 again. Backing off 30min...`);
    } else {
      waitMs = 60 * 60000; // 1hour
      console.log(`\n  429 persistent. Backing off 1hour...`);
    }
    await page.waitForTimeout(waitMs);

    const currentTotal = countForUser.get(screenName).c;
    if (currentTotal === lastTotal) {
      noNewCount++;
      if (noNewCount >= 10) {
        // 429でstallした場合はリロードして再試行
        if (rateLimitHits > 0) {
          console.log(`\n  Stalled after 429. Reloading page...`);
          rateLimitHits = 0;
          noNewCount = 0;
          await page.reload({ waitUntil: 'domcontentloaded', timeout: 30000 });
          await page.waitForTimeout(5000);
          continue;
        }
        console.log(`\n  No new tweets for 10 scrolls. Done.`);
        break;
      }
    } else {
      noNewCount = 0;
      lastTotal = currentTotal;
    }

    // 進捗表示
    if (i % 20 === 0 && i > 0) {
      console.log(`\n  [${screenName}] scroll ${i}, DB: ${currentTotal}, responses: ${responseCount}`);
    }
  }

  await browser.close();

  const finalTotal = countForUser.get(screenName).c;
  console.log(`\n  === ${screenName} Done ===`);
  console.log(`  Total in DB: ${finalTotal}`);
  console.log(`  New this run: ${totalNew}`);
  console.log(`  GraphQL responses: ${responseCount}`);
}

// === Main ===
async function main() {
  const accounts = process.argv.slice(2);
  if (accounts.length === 0) {
    console.log('Usage: node fetch_search_playwright.js <screen_name> [screen_name2] ...');
    console.log('  Optional: append :YYYY-MM-DD to specify start date');
    console.log('  Example: node fetch_search_playwright.js CryptoHayes:2018-01-01 BobLoukas:2019-01-01');
    process.exit(1);
  }

  console.log('=== Playwright SearchTimeline Fetcher ===\n');

  for (const arg of accounts) {
    const [screenName, startDate] = arg.split(':');
    await fetchAccount(screenName, startDate || null);
  }

  console.log('\n=== All Done ===');
  db.close();
}

main().catch(e => { console.error(e); db.close(); });
