const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ storageState: './x-storage.json' });
  const page = await context.newPage();

  await page.goto('https://x.com/home', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.waitForTimeout(3000);

  let capturedUrl = null;
  let capturedHeaders = null;
  page.on('request', (req) => {
    if (req.url().includes('SearchTimeline') && !capturedHeaders) {
      capturedHeaders = req.headers();
      capturedUrl = req.url();
    }
  });

  await page.goto('https://x.com/search?q=from%3Asmile_danjer%20since%3A2023-11-01%20until%3A2023-12-01&src=typed_query&f=live', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.waitForTimeout(8000);

  if (!capturedUrl) {
    for (let i = 0; i < 3; i++) {
      await page.mouse.wheel(0, 3000);
      await page.waitForTimeout(3000);
      if (capturedUrl) break;
    }
  }

  if (!capturedUrl) { console.log('No URL'); await browser.close(); return; }
  console.log('Captured. Headers:', Object.keys(capturedHeaders).filter(k => k.startsWith('x-') || k === 'authorization').join(', '));

  let cursor = null;
  let totalTweets = 0;

  for (let i = 0; i < 50; i++) {
    const result = await page.evaluate(async ({ baseUrl, cursor, headers }) => {
      const url = new URL(baseUrl);
      if (cursor) {
        const v = JSON.parse(url.searchParams.get('variables'));
        v.cursor = cursor;
        url.searchParams.set('variables', JSON.stringify(v));
      }
      const resp = await fetch(url.toString(), {
        credentials: 'include',
        headers: {
          'authorization': headers.authorization,
          'x-csrf-token': headers['x-csrf-token'],
          'x-twitter-active-user': 'yes',
          'x-twitter-auth-type': 'OAuth2Session',
          'x-client-transaction-id': headers['x-client-transaction-id'] || '',
          'content-type': 'application/json',
        }
      });
      const status = resp.status;
      const remaining = resp.headers.get('x-rate-limit-remaining');
      const reset = resp.headers.get('x-rate-limit-reset');
      if (status !== 200) return { status, remaining, reset, tweets: 0, cursor: null };
      const raw = await resp.text();
      const ids = new Set();
      const re = /\"id_str\":\"(\d{10,})\"/g;
      let m; while ((m = re.exec(raw)) !== null) ids.add(m[1]);
      const cm = raw.match(/"cursor-bottom-[^"]*"[^}]*"value":"([^"]+)"/);
      return { status, remaining, reset, tweets: ids.size, cursor: cm ? cm[1] : null };
    }, { baseUrl: capturedUrl, cursor, headers: capturedHeaders });

    process.stdout.write(`P${i+1}:${result.status}/${result.tweets}t/r=${result.remaining||'?'} `);

    if (result.status === 429) {
      const wait = result.reset ? Math.max(parseInt(result.reset) - Math.floor(Date.now()/1000) + 5, 60) : 900;
      console.log(`\n429. Wait ${wait}s`);
      await page.waitForTimeout(wait * 1000);
      continue;
    }
    if (result.status !== 200) { console.log(`\nError ${result.status}`); break; }

    totalTweets += result.tweets;
    if (!result.cursor || result.cursor === cursor) { console.log('\nDone.'); break; }
    cursor = result.cursor;
    await page.waitForTimeout(500);
  }

  console.log(`\nTotal: ${totalTweets} tweets`);
  await browser.close();
})();
