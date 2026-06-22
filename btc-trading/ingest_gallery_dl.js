#!/usr/bin/env node
/**
 * gallery-dlのJSONメタデータをSQLiteに投入
 * 走行中にバッチ投入。500件ごとにtransaction。
 */
const fs = require('fs');
const path = require('path');
const Database = require('better-sqlite3');

const DB_PATH = path.join(__dirname, 'x_tweets.db');
const db = new Database(DB_PATH);
db.pragma('journal_mode = WAL');
db.pragma('synchronous = NORMAL');
db.pragma('busy_timeout = 5000');

const insertTweet = db.prepare(`INSERT OR IGNORE INTO tweets (tweet_id, screen_name, created_at, full_text, in_reply_to_status_id, is_retweet, is_quote, retweet_count, favorite_count, media_json, raw_json, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`);

const ACCOUNTS = ['smile_danjer', '4HpO4Q9Dz3CWkhV', 'CryptoHayes', '_Checkmatey_', 'BobLoukas', 'LynAldenContact', 'PeterLBrandt'];

function processAccount(handle) {
  // gallery-dl通常取得 + SearchTimeline取得 の両ディレクトリを処理
  const dirs = [
    `/tmp/gdl_${handle}/twitter/${handle}`,
    `/tmp/gdl_search_${handle}/twitter/${handle}`,
  ];
  let totalNew = 0;
  for (const dir of dirs) {
    if (!fs.existsSync(dir)) continue;
    totalNew += processDir(handle, dir);
  }
  return totalNew;
}

function processDir(handle, dir) {

  const files = fs.readdirSync(dir).filter(f => f.endsWith('.json'));
  let newCount = 0;
  const batch = [];

  for (const file of files) {
    try {
      const raw = fs.readFileSync(path.join(dir, file), 'utf8');
      // tweet_idをJSON文字列から正規表現で抽出(Number精度落ち回避)
      const tidMatch = raw.match(/"tweet_id"\s*:\s*(\d+)/);
      const tweetId = tidMatch ? tidMatch[1] : '';
      const data = JSON.parse(raw);
      if (!tweetId || tweetId.length < 10) continue;

      const media = data.media ? JSON.stringify(data.media) : null;
      const createdAt = data.date ? new Date(data.date).toISOString() : null;

      batch.push([
        tweetId,
        handle,
        createdAt,
        data.content || data.text || '',
        data.reply_to || null,
        data.retweet ? 1 : 0,
        data.quote ? 1 : 0,
        data.retweet_count || 0,
        data.favorite_count || data.like_count || 0,
        media,
        null,
        new Date().toISOString(),
      ]);
    } catch (e) {}
  }

  // バッチ投入
  const tx = db.transaction((rows) => {
    let n = 0;
    for (const row of rows) {
      const c = insertTweet.run(...row);
      if (c.changes > 0) n++;
    }
    return n;
  });
  newCount = tx(batch);
  return newCount;
}

// メイン: 定期スキャン
let totalNew = 0;
for (const handle of ACCOUNTS) {
  const n = processAccount(handle);
  totalNew += n;
  if (n > 0) console.log(`${handle}: +${n} new`);
}

// DB件数確認
const totals = db.prepare('SELECT screen_name, COUNT(*) as c FROM tweets GROUP BY screen_name ORDER BY c DESC').all();
console.log('\n=== DB Totals ===');
let sum = 0;
for (const r of totals) { console.log(`${r.screen_name}: ${r.c}`); sum += r.c; }
console.log(`TOTAL: ${sum} (+${totalNew} new)`);

db.close();
