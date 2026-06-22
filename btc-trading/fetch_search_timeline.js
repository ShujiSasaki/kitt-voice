#!/usr/bin/env node
/**
 * SearchTimeline日別取得(認証済み、SQLite保存、中断再開対応)
 * from:{screen_name} since:YYYY-MM-DD until:YYYY-MM-DD で1日ずつ取得
 */

const fs = require('fs');
const path = require('path');
const Database = require('better-sqlite3');

// === Config ===
const envFile = fs.readFileSync(path.join(__dirname, '..', '.env'), 'utf8');
const CT0 = envFile.match(/X_CT0=(.+)/)?.[1]?.trim();
const AUTH = envFile.match(/X_AUTH_TOKEN=(.+)/)?.[1]?.trim();

// capturedリクエストからSearchTimelineのheaders/features取得
// capturedリクエストからSearchTimelineのURL テンプレートとheadersを取得
let SEARCH_URL_TEMPLATE = ''; // variablesだけ置換して使う
let SEARCH_HEADERS = {};
try {
  const captured = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'logs', 'x_captured_requests.json')));
  const searchReq = captured.find(r => r.url.includes('SearchTimeline'));
  if (searchReq) {
    SEARCH_URL_TEMPLATE = searchReq.url; // 完全URL保存
    SEARCH_HEADERS = { ...searchReq.headers };
    SEARCH_HEADERS.cookie = `auth_token=${AUTH}; ct0=${CT0}`;
  } else {
    console.error('No SearchTimeline in captured requests');
    process.exit(1);
  }
} catch (e) {
  console.error('Failed to load captured requests:', e.message);
  process.exit(1);
}

// === SQLite (共有DB) ===
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
  CREATE TABLE IF NOT EXISTS search_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    screen_name TEXT NOT NULL,
    since_date TEXT NOT NULL,
    until_date TEXT NOT NULL,
    cursor TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    tweet_count INTEGER DEFAULT 0,
    page_count INTEGER DEFAULT 0,
    updated_at TEXT,
    UNIQUE(screen_name, since_date)
  );
  CREATE TABLE IF NOT EXISTS request_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    screen_name TEXT,
    cursor_in TEXT,
    cursor_out TEXT,
    status_code INTEGER,
    tweet_count INTEGER,
    rate_remaining TEXT,
    rate_reset TEXT,
    backoff_policy TEXT,
    error TEXT,
    created_at TEXT
  );
  CREATE INDEX IF NOT EXISTS idx_tweets_screen ON tweets(screen_name);
  CREATE INDEX IF NOT EXISTS idx_tweets_date ON tweets(created_at);
  CREATE INDEX IF NOT EXISTS idx_search_jobs_status ON search_jobs(status);
`);

const insertTweet = db.prepare(`INSERT OR IGNORE INTO tweets (tweet_id, screen_name, created_at, full_text, in_reply_to_status_id, is_retweet, is_quote, retweet_count, favorite_count, media_json, raw_json, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`);
const upsertSearchJob = db.prepare(`INSERT INTO search_jobs (screen_name, since_date, until_date, cursor, status, tweet_count, page_count, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(screen_name, since_date) DO UPDATE SET cursor=excluded.cursor, status=excluded.status, tweet_count=excluded.tweet_count, page_count=excluded.page_count, updated_at=excluded.updated_at`);
const getSearchJob = db.prepare(`SELECT * FROM search_jobs WHERE screen_name = ? AND since_date = ?`);
const getPendingJobs = db.prepare(`SELECT * FROM search_jobs WHERE screen_name = ? AND status IN ('pending', 'running', 'rate_limited') ORDER BY since_date`);
const insertLog = db.prepare(`INSERT INTO request_log (screen_name, cursor_in, cursor_out, status_code, tweet_count, rate_remaining, rate_reset, backoff_policy, error, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`);
const countTweetsForUser = db.prepare(`SELECT COUNT(*) as c FROM tweets WHERE screen_name = ?`);

// === Tweet extraction ===
function extractTweetsAndCursor(data, screenName) {
  const tweets = [];
  let bottomCursor = null;
  let terminated = false;

  function walk(obj) {
    if (!obj || typeof obj !== 'object') return;
    if (Array.isArray(obj)) { obj.forEach(walk); return; }

    // TimelineTerminateTimeline
    if (obj.type === 'TimelineTerminateTimeline') terminated = true;

    // Bottom cursor
    if (obj.entryId?.startsWith('cursor-bottom-') && obj.content?.value) {
      bottomCursor = obj.content.value;
    }
    if (obj.cursorType === 'Bottom' && obj.value) {
      bottomCursor = obj.value;
    }

    // Tweet
    if (obj.legacy?.id_str && obj.legacy?.full_text) {
      const l = obj.legacy;
      const authorName = obj.core?.user_results?.result?.legacy?.screen_name || screenName;
      // Only include tweets FROM the target user
      if (authorName.toLowerCase() === screenName.toLowerCase()) {
        const media = l.extended_entities?.media || l.entities?.media || [];
        tweets.push({
          tweet_id: l.id_str,
          screen_name: screenName,
          created_at: l.created_at,
          full_text: l.full_text,
          in_reply_to_status_id: l.in_reply_to_status_id_str || null,
          is_retweet: l.retweeted_status_result ? 1 : 0,
          is_quote: obj.quoted_status_result ? 1 : 0,
          retweet_count: l.retweet_count || 0,
          favorite_count: l.favorite_count || 0,
          media_json: media.length > 0 ? JSON.stringify(media.map(m => ({
            type: m.type,
            url: m.media_url_https,
            video_url: m.video_info?.variants?.find(v => v.content_type === 'video/mp4')?.url
          }))) : null,
        });
      }
      return; // Don't recurse into already-extracted tweet
    }

    for (const v of Object.values(obj)) walk(v);
  }

  walk(data);

  const seen = new Set();
  const unique = tweets.filter(t => { if (seen.has(t.tweet_id)) return false; seen.add(t.tweet_id); return true; });
  return { tweets: unique, bottomCursor, terminated };
}

// === Fetch one day ===
async function fetchDay(screenName, sinceDate, untilDate) {
  const existingJob = getSearchJob.get(screenName, sinceDate);
  if (existingJob?.status === 'done') return { skipped: true };

  let cursor = existingJob?.cursor || null;
  let pageCount = existingJob?.page_count || 0;
  let dayTweets = 0;

  upsertSearchJob.run(screenName, sinceDate, untilDate, cursor, 'running', 0, pageCount, new Date().toISOString());

  while (true) {
    const rawQuery = `from:${screenName} since:${sinceDate} until:${untilDate}`;
    const variables = { rawQuery, count: 20, querySource: 'typed_query', product: 'Latest' };
    if (cursor) variables.cursor = cursor;

    // capturedURLのvariablesだけ置換(features/fieldTogglesはそのまま)
    const url = SEARCH_URL_TEMPLATE.replace(/variables=[^&]+/, 'variables=' + encodeURIComponent(JSON.stringify(variables)));

    try {
      const res = await fetch(url, { headers: SEARCH_HEADERS, signal: AbortSignal.timeout(15000) });
      const statusCode = res.status;
      const rateRemaining = res.headers.get('x-rate-limit-remaining');
      const rateReset = res.headers.get('x-rate-limit-reset');
      const backoff = res.headers.get('backoff-policy');

      if (statusCode === 429) {
        const resetTime = rateReset ? new Date(parseInt(rateReset) * 1000) : null;
        const waitMs = resetTime ? Math.max(resetTime.getTime() - Date.now() + 5000, 60000) : 900000;
        insertLog.run(screenName, cursor, null, 429, 0, rateRemaining, rateReset, backoff, 'rate_limited', new Date().toISOString());
        upsertSearchJob.run(screenName, sinceDate, untilDate, cursor, 'rate_limited', dayTweets, pageCount, new Date().toISOString());
        console.log(`    429. Waiting ${Math.round(waitMs/1000)}s`);
        await new Promise(r => setTimeout(r, waitMs));
        continue;
      }

      if (statusCode !== 200) {
        insertLog.run(screenName, cursor, null, statusCode, 0, rateRemaining, rateReset, backoff, `HTTP ${statusCode}`, new Date().toISOString());
        upsertSearchJob.run(screenName, sinceDate, untilDate, cursor, 'failed', dayTweets, pageCount, new Date().toISOString());
        return { error: `HTTP ${statusCode}`, dayTweets };
      }

      const data = await res.json();
      const { tweets, bottomCursor, terminated } = extractTweetsAndCursor(data, screenName);

      // Save tweets
      const insertMany = db.transaction((tws) => {
        let n = 0;
        for (const t of tws) {
          const c = insertTweet.run(t.tweet_id, t.screen_name, t.created_at, t.full_text, t.in_reply_to_status_id, t.is_retweet, t.is_quote, t.retweet_count, t.favorite_count, t.media_json, null, new Date().toISOString());
          if (c.changes > 0) n++;
        }
        return n;
      });
      const newInserted = insertMany(tweets);
      dayTweets += newInserted;
      pageCount++;

      insertLog.run(screenName, cursor, bottomCursor, statusCode, tweets.length, rateRemaining, rateReset, backoff, null, new Date().toISOString());

      // Stop conditions
      if (terminated || !bottomCursor || bottomCursor === cursor || tweets.length === 0) {
        upsertSearchJob.run(screenName, sinceDate, untilDate, bottomCursor, 'done', dayTweets, pageCount, new Date().toISOString());
        return { dayTweets, pageCount };
      }

      cursor = bottomCursor;
      upsertSearchJob.run(screenName, sinceDate, untilDate, cursor, 'running', dayTweets, pageCount, new Date().toISOString());

      // Rate limit: 6-10s jitter
      await new Promise(r => setTimeout(r, 6000 + Math.random() * 4000));

    } catch (e) {
      insertLog.run(screenName, cursor, null, 0, 0, null, null, null, e.message, new Date().toISOString());
      console.log(`    Error: ${e.message}. Waiting 30s`);
      await new Promise(r => setTimeout(r, 30000));
    }
  }
}

// === Generate date range ===
function dateRange(startDate, endDate) {
  const dates = [];
  const d = new Date(startDate);
  const end = new Date(endDate);
  while (d < end) {
    const since = d.toISOString().split('T')[0];
    d.setDate(d.getDate() + 1);
    const until = d.toISOString().split('T')[0];
    dates.push({ since, until });
  }
  return dates;
}

// === Main ===
async function main() {
  const screenName = process.argv[2];
  const startDate = process.argv[3] || '2019-01-01';
  const endDate = process.argv[4] || new Date().toISOString().split('T')[0];

  if (!screenName) {
    console.log('Usage: node fetch_search_timeline.js <screen_name> [start_date] [end_date]');
    process.exit(1);
  }

  console.log(`=== SearchTimeline日別: @${screenName} ===`);
  console.log(`Period: ${startDate} → ${endDate}`);

  const days = dateRange(startDate, endDate);
  console.log(`Days: ${days.length}`);

  // Skip already done days
  const pendingDays = days.filter(d => {
    const job = getSearchJob.get(screenName, d.since);
    return !job || job.status !== 'done';
  });
  console.log(`Pending: ${pendingDays.length} (${days.length - pendingDays.length} already done)\n`);

  let totalNew = 0;
  let daysProcessed = 0;

  for (const day of pendingDays) {
    const result = await fetchDay(screenName, day.since, day.until);

    if (result.skipped) continue;
    if (result.error) {
      console.log(`  ${day.since}: ERROR ${result.error}`);
      // 403/404ならPlaywright再捕捉が必要
      if (result.error.includes('403') || result.error.includes('404')) {
        console.log('  Need Playwright recapture. Stopping.');
        break;
      }
      continue;
    }

    totalNew += result.dayTweets || 0;
    daysProcessed++;

    if (daysProcessed % 10 === 0) {
      const total = countTweetsForUser.get(screenName).c;
      console.log(`  ${day.since}: +${result.dayTweets} (DB total: ${total}, days: ${daysProcessed}/${pendingDays.length})`);
    }
  }

  // Final stats
  const total = countTweetsForUser.get(screenName).c;
  const doneJobs = db.prepare(`SELECT COUNT(*) as c FROM search_jobs WHERE screen_name = ? AND status = 'done'`).get(screenName).c;
  const failedJobs = db.prepare(`SELECT COUNT(*) as c FROM search_jobs WHERE screen_name = ? AND status = 'failed'`).get(screenName).c;

  console.log(`\n=== @${screenName} Final Stats ===`);
  console.log(`Total tweets in DB: ${total}`);
  console.log(`New this run: ${totalNew}`);
  console.log(`Days done: ${doneJobs}/${days.length}`);
  console.log(`Days failed: ${failedJobs}`);
}

main().catch(e => { console.error(e); }).finally(() => db.close());
