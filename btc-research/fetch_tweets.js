#!/usr/bin/env node
/**
 * BTC自動売買用 X全投稿取得スクリプト
 *
 * 1. oembed API (高速) → 2. Wayback Machine (フォールバック)
 * 並列度制御 + リトライ + 進捗表示
 */

const fs = require('fs');
const path = require('path');

const BASE_DIR = path.join(__dirname, '..');
const OUT_DIR = __dirname;

// 設定
const CONCURRENCY = 5;        // 並列リクエスト数
const OEMBED_DELAY = 200;     // oembed間隔(ms)
const WAYBACK_DELAY = 500;    // wayback間隔(ms)
const MAX_RETRIES = 2;

// アカウント設定 (優先度順)
const ACCOUNTS = [
  { handle: 'smile_danjer', file: 'smile_danjer_wayback_urls.json', priority: 1 },
  { handle: '4HpO4Q9Dz3CWkhV', file: '4HpO4Q9Dz3CWkhV_wayback_urls.json', priority: 1 },
  { handle: 'CryptoHayes', file: 'CryptoHayes_wayback_urls.json', priority: 2 },
  { handle: '_Checkmatey_', file: '_Checkmatey__wayback_urls.json', priority: 2 },
  { handle: 'BobLoukas', file: 'BobLoukas_wayback_urls.json', priority: 3 },
  { handle: 'LynAldenContact', file: 'LynAldenContact_wayback_urls.json', priority: 3 },
  { handle: 'PeterLBrandt', file: 'PeterLBrandt_wayback_urls.json', priority: 3 },
];

// HTMLタグ除去
function stripHtml(html) {
  return html
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<[^>]+>/g, '')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&mdash;/g, '—')
    .replace(/&ndash;/g, '–')
    .trim();
}

// oembed APIでツイート取得
async function fetchOembed(statusId, handle) {
  const url = `https://publish.twitter.com/oembed?url=https://twitter.com/${handle}/status/${statusId}&omit_script=true`;
  try {
    const res = await fetch(url, { signal: AbortSignal.timeout(10000) });
    if (res.status === 404) return null; // ツイート削除済み
    if (!res.ok) return undefined; // リトライ対象
    const data = await res.json();
    const html = data.html || '';
    // <p>タグ内のテキストを抽出
    const pMatch = html.match(/<p[^>]*>([\s\S]*?)<\/p>/);
    const text = pMatch ? stripHtml(pMatch[1]) : null;
    // 日付抽出
    const dateMatch = html.match(/<a[^>]*>([^<]*\d{4})<\/a>\s*<\/blockquote>/);
    const date = dateMatch ? dateMatch[1].trim() : null;
    return text ? { text, date, source: 'oembed' } : null;
  } catch (e) {
    return undefined; // タイムアウト等
  }
}

// Wayback Machineでツイート取得
async function fetchWayback(statusId, handle, timestamp) {
  const twitterUrl = `https://twitter.com/${handle}/status/${statusId}`;
  const url = `https://web.archive.org/web/${timestamp}id_/${twitterUrl}`;
  try {
    const res = await fetch(url, {
      signal: AbortSignal.timeout(15000),
      headers: { 'User-Agent': 'Mozilla/5.0 (compatible; research bot)' }
    });
    if (!res.ok) return null;
    const html = await res.text();

    // 旧Twitter形式: js-tweet-text
    let match = html.match(/class="js-tweet-text[^"]*"[^>]*>([\s\S]*?)<\/p>/);
    if (match) {
      return { text: stripHtml(match[1]), date: extractDate(html), source: 'wayback-old' };
    }

    // OGP description
    match = html.match(/property="og:description"\s+content="([^"]+)"/);
    if (match) {
      return { text: stripHtml(match[1]), date: extractDate(html), source: 'wayback-ogp' };
    }

    // meta description
    match = html.match(/name="description"\s+content="([^"]+)"/);
    if (match) {
      return { text: stripHtml(match[1]), date: extractDate(html), source: 'wayback-meta' };
    }

    return null;
  } catch (e) {
    return null;
  }
}

function extractDate(html) {
  // data-time属性
  let match = html.match(/data-time="(\d+)"/);
  if (match) return new Date(parseInt(match[1]) * 1000).toISOString();
  // datetime属性
  match = html.match(/datetime="([^"]+)"/);
  if (match) return match[1];
  return null;
}

// 並列度制御
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

// 1アカウント分のツイート取得
async function processAccount(account) {
  const filePath = path.join(BASE_DIR, account.file);
  if (!fs.existsSync(filePath)) {
    console.log(`  [SKIP] ${account.file} not found`);
    return;
  }

  const outFile = path.join(OUT_DIR, `${account.handle}_tweets.json`);

  // 既存結果の読み込み (再開対応)
  let existing = {};
  if (fs.existsSync(outFile)) {
    try {
      const data = JSON.parse(fs.readFileSync(outFile, 'utf8'));
      if (data.tweets) {
        for (const t of data.tweets) {
          existing[t.status_id] = t;
        }
      }
      console.log(`  [RESUME] ${Object.keys(existing).length} tweets already fetched`);
    } catch (e) {}
  }

  // wayback URLを読み込み+重複排除
  const raw = JSON.parse(fs.readFileSync(filePath, 'utf8'));
  const byId = {};
  for (const item of raw) {
    const sid = item.status_id;
    if (!sid || sid.length < 10 || /%/.test(sid)) continue;
    if (!byId[sid]) byId[sid] = item;
  }

  const allIds = Object.keys(byId);
  const toFetch = allIds.filter(id => !existing[id]);
  console.log(`  ${allIds.length} unique tweets, ${toFetch.length} to fetch`);

  if (toFetch.length === 0) return;

  let fetched = 0;
  let oembedOk = 0;
  let waybackOk = 0;
  let failed = 0;

  // Phase 1: oembed (高速)
  console.log(`  Phase 1: oembed API...`);
  const oembedResults = await parallelMap(toFetch, async (sid, i) => {
    const result = await fetchOembed(sid, account.handle);
    fetched++;
    if (fetched % 100 === 0) {
      process.stdout.write(`\r  Progress: ${fetched}/${toFetch.length} (oembed: ${oembedOk}, wayback pending)`);
    }
    if (result) oembedOk++;
    return { sid, result };
  }, CONCURRENCY, OEMBED_DELAY);

  // oembed失敗分をwaybackで取得
  const waybackNeeded = oembedResults.filter(r => r.result === null || r.result === undefined);
  console.log(`\n  Phase 2: Wayback Machine for ${waybackNeeded.length} remaining...`);

  if (waybackNeeded.length > 0) {
    await parallelMap(waybackNeeded, async (item, i) => {
      const wb = byId[item.sid];
      const result = await fetchWayback(item.sid, account.handle, wb.timestamp);
      if (result) {
        item.result = result;
        waybackOk++;
      } else {
        failed++;
      }
      if ((i + 1) % 50 === 0) {
        process.stdout.write(`\r  Wayback: ${i + 1}/${waybackNeeded.length} (ok: ${waybackOk}, fail: ${failed})`);
      }
    }, 3, WAYBACK_DELAY);
  }

  // 結果をマージ
  const tweets = { ...existing };
  for (const r of oembedResults) {
    if (r.result && r.result.text) {
      tweets[r.sid] = {
        status_id: r.sid,
        handle: account.handle,
        text: r.result.text,
        date: r.result.date,
        source: r.result.source
      };
    }
  }

  // 保存
  const tweetList = Object.values(tweets).sort((a, b) => (a.status_id > b.status_id ? 1 : -1));
  const output = {
    handle: account.handle,
    total_wayback_urls: allIds.length,
    fetched_count: tweetList.length,
    oembed_count: oembedOk,
    wayback_count: waybackOk,
    failed_count: toFetch.length - oembedOk - waybackOk,
    last_updated: new Date().toISOString(),
    tweets: tweetList
  };

  fs.writeFileSync(outFile, JSON.stringify(output, null, 2));
  console.log(`\n  DONE: ${tweetList.length}/${allIds.length} tweets saved to ${path.basename(outFile)}`);
  console.log(`    oembed: ${oembedOk}, wayback: ${waybackOk}, failed: ${toFetch.length - oembedOk - waybackOk}`);
}

// メイン
async function main() {
  const targetHandle = process.argv[2]; // 特定アカウントのみ指定可能

  console.log('=== BTC X Tweet Fetcher ===\n');

  for (const account of ACCOUNTS) {
    if (targetHandle && account.handle !== targetHandle) continue;
    console.log(`\n[${account.handle}] (priority: ${account.priority})`);
    await processAccount(account);
  }

  console.log('\n=== Complete ===');
}

main().catch(console.error);
