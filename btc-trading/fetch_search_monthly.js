#!/usr/bin/env node
/**
 * SearchTimeline月単位取得 - Playwright 1セッションで月ごとにページ遷移
 * 1つのブラウザを開きっぱなしにして、月ごとにURLを変えてスクロール
 * rate limit: 50req/15min、18秒間隔
 */

const fs = require('fs');
const path = require('path');
const Database = require('better-sqlite3');
const { chromium } = require('playwright');

const DB_PATH = path.join(__dirname, 'x_tweets.db');
const db = new Database(DB_PATH);
db.pragma('journal_mode = WAL');

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
          tweet_id: l.id_str, screen_name: author || targetScreen,
          created_at: l.created_at, full_text: l.full_text,
          in_reply_to_status_id: l.in_reply_to_status_id_str || null,
          is_retweet: l.retweeted_status_result ? 1 : 0,
          is_quote: obj.quoted_status_result ? 1 : 0,
          retweet_count: l.retweet_count || 0, favorite_count: l.favorite_count || 0,
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

// 月リスト生成
function generateMonths(startDate, endDate) {
  const months = [];
  const d = new Date(startDate);
  const end = new Date(endDate);
  while (d < end) {
    const since = d.toISOString().split('T')[0];
    d.setMonth(d.getMonth() + 1);
    const until = d.toISOString().split('T')[0];
    months.push({ since, until });
  }
  return months;
}

async function main() {
  const screenName = process.argv[2];
  const startDate = process.argv[3] || '2019-01-01';
  const endDate = process.argv[4] || new Date().toISOString().split('T')[0];

  if (!screenName) {
    console.log('Usage: node fetch_search_monthly.js <screen_name> [start_date] [end_date]');
    process.exit(1);
  }

  const months = generateMonths(startDate, endDate);
  console.log(`=== SearchTimeline Monthly: @${screenName} ===`);
  console.log(`Period: ${startDate} → ${endDate} (${months.length} months)`);
  console.log(`DB before: ${countForUser.get(screenName).c}\n`);

  const storagePath = path.join(__dirname, 'x-storage.json');
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    storageState: storagePath,
    viewport: { width: 1280, height: 900 },
  });
  const page = await context.newPage();

  // ログイン確認
  await page.goto('https://x.com/home', { waitUntil: 'domcontentloaded', timeout: 30000 });
  if (page.url().includes('/login')) {
    console.log('NOT LOGGED IN. Stopping.');
    await browser.close(); db.close(); return;
  }
  console.log('Logged in OK\n');
  await page.waitForTimeout(3000);

  let totalNew = 0;
  let rateLimitRemaining = 50;
  let rateLimitReset = 0;

  // response捕捉
  page.on('response', async (res) => {
    const url = res.url();
    if (!url.includes('SearchTimeline')) return;
    const status = res.status();
    const headers = res.headers();

    // rate limit更新
    if (headers['x-rate-limit-remaining']) rateLimitRemaining = parseInt(headers['x-rate-limit-remaining']);
    if (headers['x-rate-limit-reset']) rateLimitReset = parseInt(headers['x-rate-limit-reset']);

    if (status === 429) {
      console.log(`  429! remaining=${rateLimitRemaining} reset=${new Date(rateLimitReset*1000).toISOString()}`);
      return;
    }
    if (status !== 200) return;

    try {
      const data = await res.json();
      const tweets = extractTweets(data, screenName);
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
      totalNew += tx();
    } catch {}
  });

  // 月ごとにページ遷移+スクロール
  for (let mi = 0; mi < months.length; mi++) {
    const m = months[mi];
    const query = `from:${screenName} since:${m.since} until:${m.until}`;
    const searchUrl = `https://x.com/search?q=${encodeURIComponent(query)}&src=typed_query&f=live`;

    // rate limit確認: remaining少なければresetまで待つ
    if (rateLimitRemaining <= 2) {
      const waitSec = Math.max(rateLimitReset - Math.floor(Date.now()/1000) + 5, 60);
      console.log(`  Rate limit low (${rateLimitRemaining}). Waiting ${waitSec}s...`);
      await page.waitForTimeout(waitSec * 1000);
    }

    await page.goto(searchUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.waitForTimeout(5000);

    // スクロールループ
    let noNewCount = 0;
    let lastTotal = countForUser.get(screenName).c;
    const maxScrolls = 200;

    for (let s = 0; s < maxScrolls; s++) {
      // rate limit確認
      if (rateLimitRemaining <= 2) {
        const waitSec = Math.max(rateLimitReset - Math.floor(Date.now()/1000) + 5, 60);
        console.log(`  Rate limit low. Waiting ${waitSec}s...`);
        await page.waitForTimeout(waitSec * 1000);
        // リロードしてスクロール再開
        await page.reload({ waitUntil: 'domcontentloaded', timeout: 30000 });
        await page.waitForTimeout(5000);
        noNewCount = 0;
      }

      await page.mouse.wheel(0, 3000);
      await page.waitForTimeout(18000 + Math.random() * 7000); // 18-25s

      const currentTotal = countForUser.get(screenName).c;
      if (currentTotal === lastTotal) {
        noNewCount++;
        if (noNewCount >= 5) break; // この月は完了
      } else {
        noNewCount = 0;
        lastTotal = currentTotal;
      }
    }

    const monthTotal = countForUser.get(screenName).c;
    const monthNew = monthTotal - (mi === 0 ? countForUser.get(screenName).c - totalNew : months[mi-1]?._lastTotal || 0);
    process.stdout.write(`\r  [${mi+1}/${months.length}] ${m.since}: DB=${monthTotal} (+${totalNew} total new) remain=${rateLimitRemaining}`);
    months[mi]._lastTotal = monthTotal;

    // 月間切替時に少し待機
    await page.waitForTimeout(3000);
  }

  await browser.close();

  const finalTotal = countForUser.get(screenName).c;
  console.log(`\n\n=== @${screenName} Final ===`);
  console.log(`DB: ${finalTotal} (+${totalNew} new)`);
  db.close();
}

main().catch(e => { console.error(e); db.close(); });
