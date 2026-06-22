#!/usr/bin/env node
/**
 * X全投稿取得(認証済み、SQLite保存、中断再開対応)
 * Project Rules準拠:
 * - tweet_idで重複排除
 * - cursorを保存
 * - SQLiteへ逐次保存
 * - 途中終了しても再開可能
 * - 取得件数、最古投稿日時、最後のcursorをログ出力
 */

const fs = require('fs');
const path = require('path');
const Database = require('better-sqlite3');

// === Config ===
const envFile = fs.readFileSync(path.join(__dirname, '..', '.env'), 'utf8');
const CT0 = envFile.match(/X_CT0=(.+)/)?.[1]?.trim();
const AUTH = envFile.match(/X_AUTH_TOKEN=(.+)/)?.[1]?.trim();
const BEARER = 'AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA';
const UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36';

// capturedリクエストから直接取得したfeatures(JSON.stringifyの微妙なエスケープ差を回避)
let FEATURES, FIELD_TOGGLES;
try {
  const capturedData = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'logs', 'x_captured_requests.json')));
  const utarReq = capturedData.find(r => r.url.includes('UserTweetsAndReplies'));
  if (utarReq) {
    const capturedUrl = new URL(utarReq.url);
    FEATURES = capturedUrl.searchParams.get('features');
    FIELD_TOGGLES = capturedUrl.searchParams.get('fieldToggles') || '{"withArticlePlainText":false}';
  }
} catch (e) {}
if (!FEATURES) {
  FEATURES = '{"rweb_video_screen_enabled":false,"rweb_cashtags_enabled":true,"profile_label_improvements_pcf_label_in_post_enabled":true,"responsive_web_profile_redirect_enabled":false,"rweb_tipjar_consumption_enabled":false,"verified_phone_label_enabled":false,"creator_subscriptions_tweet_preview_api_enabled":true,"responsive_web_graphql_timeline_navigation_enabled":true,"responsive_web_graphql_skip_user_profile_image_extensions_enabled":false,"premium_content_api_read_enabled":false,"communities_web_enable_tweet_community_results_fetch":true,"c9s_tweet_anatomy_moderator_badge_enabled":true,"responsive_web_grok_analyze_button_fetch_trends_enabled":false,"responsive_web_grok_analyze_post_followups_enabled":true,"rweb_cashtags_composer_attachment_enabled":true,"responsive_web_jetfuel_frame":true,"responsive_web_grok_share_attachment_enabled":true,"responsive_web_grok_annotations_enabled":true,"articles_preview_enabled":true,"responsive_web_edit_tweet_api_enabled":true,"graphql_is_translatable_rweb_tweet_is_translatable_enabled":true,"view_counts_everywhere_api_enabled":true,"longform_notetweets_consumption_enabled":true,"responsive_web_twitter_article_tweet_consumption_enabled":true,"content_disclosure_indicator_enabled":true,"content_disclosure_ai_generated_indicator_enabled":true,"responsive_web_grok_show_grok_translated_post":true,"responsive_web_grok_analysis_button_from_backend":true,"post_ctas_fetch_enabled":false,"freedom_of_speech_not_reach_fetch_enabled":true,"standardized_nudges_misinfo":true,"tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled":true,"longform_notetweets_rich_text_read_enabled":true,"longform_notetweets_inline_media_enabled":false,"responsive_web_grok_image_annotation_enabled":true,"responsive_web_grok_imagine_annotation_enabled":true,"responsive_web_grok_community_note_auto_translation_is_enabled":true,"responsive_web_enhance_cards_enabled":false}';
  FIELD_TOGGLES = '{"withArticlePlainText":false}';
}

// capturedリクエストからヘッダーも取得
let CAPTURED_HEADERS = {};
try {
  const capturedData2 = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'logs', 'x_captured_requests.json')));
  const utarReq2 = capturedData2.find(r => r.url.includes('UserTweetsAndReplies'));
  if (utarReq2) CAPTURED_HEADERS = utarReq2.headers;
} catch (e) {}

const HEADERS = {
  ...CAPTURED_HEADERS,
  'Cookie': `auth_token=${AUTH}; ct0=${CT0}`,
};

const ACCOUNTS = [
  { handle: 'smile_danjer', userId: '3382360819' },
  { handle: '4HpO4Q9Dz3CWkhV', userId: null },
  { handle: 'CryptoHayes', userId: null },
  { handle: '_Checkmatey_', userId: null },
  { handle: 'BobLoukas', userId: null },
  { handle: 'LynAldenContact', userId: null },
  { handle: 'PeterLBrandt', userId: null },
];

// === SQLite Setup ===
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
  CREATE TABLE IF NOT EXISTS crawl_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    screen_name TEXT NOT NULL,
    cursor TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    stop_reason TEXT,
    page_count INTEGER DEFAULT 0,
    tweet_count INTEGER DEFAULT 0,
    oldest_tweet_date TEXT,
    newest_tweet_date TEXT,
    updated_at TEXT,
    UNIQUE(screen_name)
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
`);

const insertTweet = db.prepare(`INSERT OR IGNORE INTO tweets (tweet_id, screen_name, created_at, full_text, in_reply_to_status_id, is_retweet, is_quote, retweet_count, favorite_count, media_json, raw_json, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`);
const upsertJob = db.prepare(`INSERT INTO crawl_jobs (screen_name, cursor, status, page_count, tweet_count, oldest_tweet_date, newest_tweet_date, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(screen_name) DO UPDATE SET cursor=excluded.cursor, status=excluded.status, page_count=excluded.page_count, tweet_count=excluded.tweet_count, oldest_tweet_date=excluded.oldest_tweet_date, newest_tweet_date=excluded.newest_tweet_date, updated_at=excluded.updated_at`);
const insertLog = db.prepare(`INSERT INTO request_log (screen_name, cursor_in, cursor_out, status_code, tweet_count, rate_remaining, rate_reset, backoff_policy, error, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`);
const getJob = db.prepare(`SELECT * FROM crawl_jobs WHERE screen_name = ?`);
const countTweets = db.prepare(`SELECT COUNT(*) as c FROM tweets WHERE screen_name = ?`);
const oldestTweet = db.prepare(`SELECT MIN(created_at) as d FROM tweets WHERE screen_name = ?`);
const newestTweet = db.prepare(`SELECT MAX(created_at) as d FROM tweets WHERE screen_name = ?`);

// === API Functions ===
async function getUserId(handle) {
  const v = JSON.stringify({ screen_name: handle });
  const f = JSON.stringify({ hidden_profile_subscriptions_enabled: true, responsive_web_graphql_timeline_navigation_enabled: true, responsive_web_graphql_skip_user_profile_image_extensions_enabled: false });
  const url = `https://x.com/i/api/graphql/IGgvgiOx4QZndDHuD3x9TQ/UserByScreenName?variables=${encodeURIComponent(v)}&features=${encodeURIComponent(f)}`;
  const res = await fetch(url, { headers: HEADERS, signal: AbortSignal.timeout(10000) });
  const data = await res.json();
  return data?.data?.user?.result?.rest_id || null;
}

function extractTweetsAndCursor(data, screenName) {
  const tweets = [];
  let bottomCursor = null;
  let terminated = false;

  function findInstructions(obj) {
    if (!obj || typeof obj !== 'object') return [];
    if (Array.isArray(obj) && obj.length > 0 && obj[0]?.type) return obj;
    for (const v of Object.values(obj)) {
      const r = findInstructions(v);
      if (r.length > 0) return r;
    }
    return [];
  }

  const instructions = findInstructions(data);

  for (const inst of instructions) {
    if (inst.type === 'TimelineTerminateTimeline') {
      terminated = true;
    }

    const entries = inst.entries || [];
    for (const entry of entries) {
      // Bottom cursor
      if (entry.entryId?.startsWith('cursor-bottom-')) {
        bottomCursor = entry.content?.value;
      }
      if (entry.content?.cursorType === 'Bottom') {
        bottomCursor = entry.content?.value;
      }

      // Tweet extraction (recursive)
      extractTweetsFromObj(entry, tweets, screenName);
    }

    // moduleItems
    for (const item of (inst.moduleItems || [])) {
      extractTweetsFromObj(item, tweets, screenName);
    }
  }

  // Dedupe
  const seen = new Set();
  const unique = tweets.filter(t => { if (seen.has(t.tweet_id)) return false; seen.add(t.tweet_id); return true; });
  return { tweets: unique, bottomCursor, terminated };
}

function extractTweetsFromObj(obj, tweets, screenName) {
  if (!obj || typeof obj !== 'object') return;
  const legacy = obj.legacy;
  if (legacy?.id_str && legacy?.full_text) {
    const media = legacy.extended_entities?.media || legacy.entities?.media || [];
    tweets.push({
      tweet_id: legacy.id_str,
      screen_name: screenName,
      created_at: legacy.created_at,
      full_text: legacy.full_text,
      in_reply_to_status_id: legacy.in_reply_to_status_id_str || null,
      is_retweet: legacy.retweeted_status_result ? 1 : 0,
      is_quote: obj.quoted_status_result ? 1 : 0,
      retweet_count: legacy.retweet_count || 0,
      favorite_count: legacy.favorite_count || 0,
      media_json: media.length > 0 ? JSON.stringify(media.map(m => ({ type: m.type, url: m.media_url_https, video_url: m.video_info?.variants?.find(v => v.content_type === 'video/mp4')?.url }))) : null,
    });
    return;
  }
  for (const v of Object.values(obj)) {
    if (typeof v === 'object') extractTweetsFromObj(v, tweets, screenName);
  }
}

// === Main Fetch Loop ===
async function fetchAllTweets(handle, userId) {
  // Resume from saved cursor
  const existingJob = getJob.get(handle);
  let cursor = null;
  let pageCount = 0;
  let totalNew = 0;

  if (existingJob && existingJob.status === 'running' && existingJob.cursor) {
    cursor = existingJob.cursor;
    pageCount = existingJob.page_count || 0;
    console.log(`  Resuming from page ${pageCount}, cursor: ${cursor.substring(0, 30)}...`);
  }

  upsertJob.run(handle, cursor, 'running', pageCount, countTweets.get(handle).c, null, null, new Date().toISOString());

  let sameCursorCount = 0;
  let emptyPageCount = 0;

  while (true) {
    const variables = { userId, count: 20, includePromotedContent: true, withCommunity: true, withVoice: true };
    if (cursor) variables.cursor = cursor;

    const url = `https://x.com/i/api/graphql/3YJONShMAajim63A8iF-sw/UserTweetsAndReplies?variables=${encodeURIComponent(JSON.stringify(variables))}&features=${encodeURIComponent(FEATURES)}&fieldToggles=${encodeURIComponent(FIELD_TOGGLES)}`;

    let statusCode, rateRemaining, rateReset, backoff, error;
    try {
      const res = await fetch(url, { headers: HEADERS, signal: AbortSignal.timeout(15000) });
      statusCode = res.status;
      rateRemaining = res.headers.get('x-rate-limit-remaining');
      rateReset = res.headers.get('x-rate-limit-reset');
      backoff = res.headers.get('backoff-policy');

      if (statusCode === 429) {
        const resetTime = rateReset ? new Date(parseInt(rateReset) * 1000) : null;
        const waitMs = resetTime ? Math.max(resetTime.getTime() - Date.now() + 5000, 60000) : 900000;
        console.log(`  Rate limited. Waiting ${Math.round(waitMs/1000)}s (reset: ${resetTime?.toISOString() || 'unknown'})`);
        insertLog.run(handle, cursor, null, 429, 0, rateRemaining, rateReset, backoff, 'rate_limited', new Date().toISOString());
        upsertJob.run(handle, cursor, 'rate_limited', pageCount, countTweets.get(handle).c, oldestTweet.get(handle).d, newestTweet.get(handle).d, new Date().toISOString());
        await new Promise(r => setTimeout(r, waitMs));
        upsertJob.run(handle, cursor, 'running', pageCount, countTweets.get(handle).c, oldestTweet.get(handle).d, newestTweet.get(handle).d, new Date().toISOString());
        continue;
      }

      if (statusCode !== 200) {
        error = `HTTP ${statusCode}`;
        insertLog.run(handle, cursor, null, statusCode, 0, rateRemaining, rateReset, backoff, error, new Date().toISOString());
        console.log(`  ${error}. Stopping.`);
        upsertJob.run(handle, cursor, 'failed', pageCount, countTweets.get(handle).c, oldestTweet.get(handle).d, newestTweet.get(handle).d, new Date().toISOString());
        break;
      }

      if (backoff) {
        console.log(`  Backoff detected: ${backoff}`);
        await new Promise(r => setTimeout(r, 30000));
      }

      const data = await res.json();
      const { tweets, bottomCursor, terminated } = extractTweetsAndCursor(data, handle);

      // Save tweets to SQLite
      const insertMany = db.transaction((tws) => {
        let inserted = 0;
        for (const t of tws) {
          const changes = insertTweet.run(t.tweet_id, t.screen_name, t.created_at, t.full_text, t.in_reply_to_status_id, t.is_retweet, t.is_quote, t.retweet_count, t.favorite_count, t.media_json, null, new Date().toISOString());
          if (changes.changes > 0) inserted++;
        }
        return inserted;
      });
      const newInserted = insertMany(tweets);
      totalNew += newInserted;
      pageCount++;

      // Log request
      insertLog.run(handle, cursor, bottomCursor, statusCode, tweets.length, rateRemaining, rateReset, backoff, null, new Date().toISOString());

      // Progress
      if (pageCount % 10 === 0) {
        const total = countTweets.get(handle).c;
        const oldest = oldestTweet.get(handle).d || '?';
        process.stdout.write(`\r  Page ${pageCount}: ${total} tweets (oldest: ${oldest?.substring(0, 10) || '?'}) cursor: ${(bottomCursor || '').substring(0, 20)}...`);
      }

      // Stop conditions
      if (terminated) {
        console.log(`\n  TimelineTerminateTimeline received. Done.`);
        upsertJob.run(handle, bottomCursor, 'done', pageCount, countTweets.get(handle).c, oldestTweet.get(handle).d, newestTweet.get(handle).d, new Date().toISOString());
        break;
      }

      if (tweets.length === 0) {
        emptyPageCount++;
        if (emptyPageCount >= 3) {
          console.log(`\n  3 consecutive empty pages. Done.`);
          upsertJob.run(handle, bottomCursor, 'done', pageCount, countTweets.get(handle).c, oldestTweet.get(handle).d, newestTweet.get(handle).d, new Date().toISOString());
          break;
        }
      } else {
        emptyPageCount = 0;
      }

      if (!bottomCursor) {
        console.log(`\n  No bottom cursor. Done.`);
        upsertJob.run(handle, null, 'done', pageCount, countTweets.get(handle).c, oldestTweet.get(handle).d, newestTweet.get(handle).d, new Date().toISOString());
        break;
      }

      if (bottomCursor === cursor) {
        sameCursorCount++;
        if (sameCursorCount >= 3) {
          console.log(`\n  Same cursor 3 times. Done.`);
          upsertJob.run(handle, cursor, 'done', pageCount, countTweets.get(handle).c, oldestTweet.get(handle).d, newestTweet.get(handle).d, new Date().toISOString());
          break;
        }
      } else {
        sameCursorCount = 0;
      }

      cursor = bottomCursor;

      // Save job state every page
      upsertJob.run(handle, cursor, 'running', pageCount, countTweets.get(handle).c, oldestTweet.get(handle).d, newestTweet.get(handle).d, new Date().toISOString());

      // Rate limit: 18-27s jitter (GPT-5.5推奨)
      const jitter = 18000 + Math.random() * 9000;
      await new Promise(r => setTimeout(r, jitter));

    } catch (e) {
      error = e.message;
      insertLog.run(handle, cursor, null, statusCode || 0, 0, null, null, null, error, new Date().toISOString());
      console.log(`  Error: ${error}. Waiting 30s...`);
      await new Promise(r => setTimeout(r, 30000));
    }
  }

  // Final stats
  const total = countTweets.get(handle).c;
  const oldest = oldestTweet.get(handle).d;
  const newest = newestTweet.get(handle).d;
  console.log(`\n  === ${handle} Final Stats ===`);
  console.log(`  Total tweets in DB: ${total}`);
  console.log(`  New this run: ${totalNew}`);
  console.log(`  Pages fetched: ${pageCount}`);
  console.log(`  Oldest: ${oldest || 'none'}`);
  console.log(`  Newest: ${newest || 'none'}`);
}

// === Main ===
async function main() {
  const targetHandle = process.argv[2];
  console.log(`=== X Full Tweet Fetch (Auth + SQLite) ===`);
  console.log(`DB: ${DB_PATH}\n`);

  for (const account of ACCOUNTS) {
    if (targetHandle && account.handle !== targetHandle) continue;

    console.log(`\n[${account.handle}]`);

    let userId = account.userId;
    if (!userId) {
      userId = await getUserId(account.handle);
      if (!userId) { console.log('  User not found. Skipping.'); continue; }
      console.log(`  userId: ${userId}`);
    }

    await fetchAllTweets(account.handle, userId);
  }

  console.log('\n=== Complete ===');
  db.close();
}

main().catch(e => { console.error(e); db.close(); });
