#!/usr/bin/env node
/**
 * 欠落期間をgallery-dl SearchTimelineで日単位取得
 * 単一キュー、直列実行
 */
const { execSync } = require('child_process');
const fs = require('fs');

const PROFILE = process.argv[2] || 'Profile 4';
const LOG = '/tmp/fetch_gaps_daily.log';

// 各アカウントの欠落期間
const GAPS = {
  smile_danjer: { start: '2023-07-01', end: '2024-05-01' },
  BobLoukas: { start: '2021-05-01', end: '2025-03-01' },
  _Checkmatey_: { start: '2020-12-01', end: '2025-08-01' },
  LynAldenContact: { start: '2021-04-01', end: '2025-06-01' },
  PeterLBrandt: { start: '2021-03-01', end: '2025-10-01' },
};

function log(msg) {
  const line = `${new Date().toTimeString().substring(0,5)} ${msg}`;
  console.log(line);
  fs.appendFileSync(LOG, line + '\n');
}

function dateRange(start, end) {
  const dates = [];
  const d = new Date(start);
  const e = new Date(end);
  while (d < e) {
    const since = d.toISOString().split('T')[0];
    d.setDate(d.getDate() + 1);
    const until = d.toISOString().split('T')[0];
    dates.push({ since, until });
  }
  return dates;
}

fs.writeFileSync(LOG, '');
log('=== Daily gap fetch ===');

for (const [handle, gap] of Object.entries(GAPS)) {
  const days = dateRange(gap.start, gap.end);
  const dir = `/tmp/gdl_search_${handle}`;
  execSync(`mkdir -p "${dir}"`);

  log(`${handle}: ${gap.start} → ${gap.end} (${days.length} days)`);

  for (let i = 0; i < days.length; i++) {
    const { since, until } = days[i];
    const query = `from:${handle} since:${since} until:${until}`;
    const url = `https://x.com/search?q=${encodeURIComponent(query)}&f=live`;

    try {
      execSync(
        `gallery-dl --cookies-from-browser "chrome:${PROFILE}" --no-download --write-metadata -d "${dir}" "${url}"`,
        { timeout: 600000, stdio: ['pipe', 'pipe', 'pipe'] }
      );
    } catch (e) {
      // gallery-dlのexit codeが0以外でもデータは取れていることがある
    }

    if ((i + 1) % 30 === 0) {
      const count = execSync(`find "${dir}" -name "*.json" | wc -l`).toString().trim();
      log(`  ${handle} [${i+1}/${days.length}] ${since}: ${count} files total`);
    }
  }

  const count = execSync(`find "${dir}" -name "*.json" | wc -l`).toString().trim();
  log(`${handle} done: ${count} files`);
}

log('=== All done ===');
