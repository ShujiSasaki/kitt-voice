const functions = require('@google-cloud/functions-framework');
const { BigQuery } = require('@google-cloud/bigquery');
const { Storage } = require('@google-cloud/storage');

const bigquery = new BigQuery();
const storage = new Storage();
const DATASET = 'btc_trading';
const GCS_BUCKET = 'btc-research-0549297663';
const PROJECT = 'gen-lang-client-0549297663';

// ============================================================
// btcDataCollector: 5分毎にBinance APIからBTCデータ収集→BQ保存
// ============================================================
functions.http('btcDataCollector', async (req, res) => {
  try {
    const now = new Date();
    const results = {};

    // 並列取得: 価格, OI, FR, 板, 清算, klines(複数時間足)
    const [
      ticker, oi, premium, depth,
      klines1h, klines4h, klines1d,
      recentTrades, forceOrders
    ] = await Promise.all([
      apiFetch('https://fapi.binance.com/fapi/v1/ticker/24hr?symbol=BTCUSDT'),
      apiFetch('https://fapi.binance.com/fapi/v1/openInterest?symbol=BTCUSDT'),
      apiFetch('https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT'),
      apiFetch('https://fapi.binance.com/fapi/v1/depth?symbol=BTCUSDT&limit=20'),
      apiFetch('https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=1h&limit=2'),
      apiFetch('https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=4h&limit=2'),
      apiFetch('https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=1d&limit=2'),
      apiFetch('https://fapi.binance.com/fapi/v1/trades?symbol=BTCUSDT&limit=50'),
      apiFetch('https://fapi.binance.com/fapi/v1/forceOrders?symbol=BTCUSDT&limit=20').catch(() => [])
    ]);

    // === BQ: btc_snapshots (メインテーブル) ===
    const snapshot = {
      timestamp: now.toISOString(),
      price: parseFloat(ticker.lastPrice),
      price_change_24h: parseFloat(ticker.priceChangePercent),
      high_24h: parseFloat(ticker.highPrice),
      low_24h: parseFloat(ticker.lowPrice),
      volume_24h: parseFloat(ticker.quoteVolume),
      trades_24h: parseInt(ticker.count),
      open_interest: parseFloat(oi.openInterest),
      open_interest_usd: parseFloat(oi.openInterest) * parseFloat(ticker.lastPrice),
      funding_rate: parseFloat(premium.lastFundingRate),
      next_funding_time: new Date(parseInt(premium.nextFundingTime)).toISOString(),
      mark_price: parseFloat(premium.markPrice),
      index_price: parseFloat(premium.indexPrice),
      // 板のサマリー
      bid_depth_top5: depth.bids.slice(0, 5).reduce((s, b) => s + parseFloat(b[1]), 0),
      ask_depth_top5: depth.asks.slice(0, 5).reduce((s, a) => s + parseFloat(a[1]), 0),
      bid_depth_top20: depth.bids.reduce((s, b) => s + parseFloat(b[1]), 0),
      ask_depth_top20: depth.asks.reduce((s, a) => s + parseFloat(a[1]), 0),
      best_bid: parseFloat(depth.bids[0][0]),
      best_ask: parseFloat(depth.asks[0][0]),
      spread: parseFloat(depth.asks[0][0]) - parseFloat(depth.bids[0][0]),
      // 直近取引のbuy/sell比率
      buy_volume_recent: recentTrades.filter(t => !t.isBuyerMaker).reduce((s, t) => s + parseFloat(t.quoteQty), 0),
      sell_volume_recent: recentTrades.filter(t => t.isBuyerMaker).reduce((s, t) => s + parseFloat(t.quoteQty), 0),
      // 清算
      liquidation_count: forceOrders.length,
      liquidation_long_usd: forceOrders.filter(o => o.side === 'SELL').reduce((s, o) => s + parseFloat(o.price) * parseFloat(o.origQty), 0),
      liquidation_short_usd: forceOrders.filter(o => o.side === 'BUY').reduce((s, o) => s + parseFloat(o.price) * parseFloat(o.origQty), 0),
    };

    await insertBQ('btc_snapshots', [snapshot]);
    results.snapshot = 'ok';

    // === BQ: btc_klines (ローソク足) ===
    const klineRows = [];
    const parseKline = (k, tf) => ({
      timestamp: new Date(k[0]).toISOString(),
      close_time: new Date(k[6]).toISOString(),
      timeframe: tf,
      open: parseFloat(k[1]),
      high: parseFloat(k[2]),
      low: parseFloat(k[3]),
      close: parseFloat(k[4]),
      volume: parseFloat(k[5]),
      quote_volume: parseFloat(k[7]),
      trades: parseInt(k[8]),
      taker_buy_volume: parseFloat(k[9]),
      taker_buy_quote_volume: parseFloat(k[10]),
    });

    // 最新の確定足のみ保存(index 0 = 前の足 = 確定済み)
    if (klines1h[0]) klineRows.push(parseKline(klines1h[0], '1h'));
    if (klines4h[0]) klineRows.push(parseKline(klines4h[0], '4h'));
    if (klines1d[0]) klineRows.push(parseKline(klines1d[0], '1d'));

    if (klineRows.length > 0) {
      await insertBQ('btc_klines', klineRows);
      results.klines = klineRows.length;
    }

    // === BQ: btc_orderbook (板スナップショット) ===
    const obRow = {
      timestamp: now.toISOString(),
      bids: JSON.stringify(depth.bids.map(b => ({ price: parseFloat(b[0]), qty: parseFloat(b[1]) }))),
      asks: JSON.stringify(depth.asks.map(a => ({ price: parseFloat(a[0]), qty: parseFloat(a[1]) }))),
    };
    await insertBQ('btc_orderbook', [obRow]);
    results.orderbook = 'ok';

    // === BQ: btc_liquidations (清算) ===
    if (forceOrders.length > 0) {
      const liqRows = forceOrders.map(o => ({
        timestamp: new Date(o.time).toISOString(),
        side: o.side === 'SELL' ? 'LONG_LIQUIDATED' : 'SHORT_LIQUIDATED',
        price: parseFloat(o.price),
        qty: parseFloat(o.origQty),
        usd_value: parseFloat(o.price) * parseFloat(o.origQty),
      }));
      await insertBQ('btc_liquidations', liqRows);
      results.liquidations = liqRows.length;
    }

    console.log('btcDataCollector:', JSON.stringify(results));
    res.json({ success: true, ...results, price: snapshot.price, oi: snapshot.open_interest, fr: snapshot.funding_rate });

  } catch (err) {
    console.error('btcDataCollector error:', err);
    res.status(500).json({ error: err.message });
  }
});

// ============================================================
// btcJudge: AI判断エンジン (トレーダーの思考を再現)
// ============================================================
functions.http('btcJudge', async (req, res) => {
  try {
    const { trader = 'smile_danjer' } = req.query;
    const GEMINI_API_KEY = process.env.GEMINI_API_KEY;
    if (!GEMINI_API_KEY) throw new Error('GEMINI_API_KEY not set');

    // 1. 直近の相場データをBQから取得
    const [snapshots] = await bigquery.query({
      query: `SELECT * FROM \`${PROJECT}.${DATASET}.btc_snapshots\` ORDER BY timestamp DESC LIMIT 48`, // 直近4時間(5分x48)
    });

    const [klines4h] = await bigquery.query({
      query: `SELECT * FROM \`${PROJECT}.${DATASET}.btc_klines\` WHERE timeframe = '4h' ORDER BY timestamp DESC LIMIT 60`, // 直近10日
    });

    const [klines1d] = await bigquery.query({
      query: `SELECT * FROM \`${PROJECT}.${DATASET}.btc_klines\` WHERE timeframe = '1d' ORDER BY timestamp DESC LIMIT 90`, // 直近90日
    });

    const [liquidations] = await bigquery.query({
      query: `SELECT * FROM \`${PROJECT}.${DATASET}.btc_liquidations\` ORDER BY timestamp DESC LIMIT 100`,
    });

    // 2. トレーダーのツイートをGCSから取得
    const { Storage } = require('@google-cloud/storage');
    const storage = new Storage();
    const [tweetsFile] = await storage.bucket('btc-research-0549297663').file(`tweets/${trader}_tweets.json`).download();
    const tweetsData = JSON.parse(tweetsFile.toString());

    // トレード関連ツイートをフィルタ(直近2年 + トレード関連キーワード)
    const tradeKeywords = ['BTC', 'ビットコイン', 'ロング', 'ショート', 'エントリー', '利確', '損切', 'OI', 'FR',
      'サイクル', '日足', '週足', '4H', 'MA', 'RSI', 'フィボ', 'エリオット', 'トレンド', 'ポジション',
      'チャート', 'ブレイク', 'サポート', 'レジスタンス', 'long', 'short', 'entry', 'bitcoin'];
    const twoYearsAgo = new Date(Date.now() - 730 * 86400000).toISOString();
    const relevantTweets = tweetsData.tweets
      .filter(t => {
        const date = t.created_at || t.date || '';
        const isRecent = date > twoYearsAgo || !date;
        const isTradeRelated = tradeKeywords.some(kw => t.text.toLowerCase().includes(kw.toLowerCase()));
        return isRecent && isTradeRelated;
      })
      .slice(-500); // 最新500件に制限(トークン制約)

    // 3. 現在の相場サマリーを構築
    const latest = snapshots[0];
    const marketSummary = buildMarketSummary(latest, snapshots, klines4h, klines1d, liquidations);

    // 4. AIに判断させる
    const prompt = buildTraderPrompt(trader, relevantTweets, marketSummary);

    const geminiRes = await fetch(
      `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=${GEMINI_API_KEY}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          contents: [{ parts: [{ text: prompt }] }],
          generationConfig: {
            responseMimeType: 'application/json',
            maxOutputTokens: 4096,
          },
        }),
      }
    );

    const geminiData = await geminiRes.json();
    const responseText = geminiData.candidates?.[0]?.content?.parts?.[0]?.text || '{}';
    let judgment;
    try {
      // Geminiが```json```で囲む場合の対処
      const cleaned = responseText.replace(/```json\n?/g, '').replace(/```\n?/g, '').trim();
      judgment = JSON.parse(cleaned);
    } catch {
      // 部分的にパースを試みる
      try {
        const match = responseText.match(/\{[\s\S]*\}/);
        if (match) judgment = JSON.parse(match[0]);
        else judgment = { raw: responseText };
      } catch {
        judgment = { raw: responseText };
      }
    }

    // 5. 判断結果をBQに保存
    await insertBQ('btc_judgments', [{
      timestamp: new Date().toISOString(),
      trader,
      action: judgment.action || 'NONE',
      direction: judgment.direction || null,
      confidence: judgment.confidence || 0,
      leverage: judgment.leverage || null,
      position_size_pct: judgment.position_size_pct || null,
      entry_price: judgment.entry_price || null,
      stop_loss: judgment.stop_loss || null,
      take_profit: judgment.take_profit || null,
      reasoning: judgment.reasoning || '',
      market_context: JSON.stringify(marketSummary).substring(0, 5000),
      raw_response: responseText.substring(0, 10000),
    }]);

    res.json({ success: true, trader, judgment });

  } catch (err) {
    console.error('btcJudge error:', err);
    res.status(500).json({ error: err.message });
  }
});

// ============================================================
// ヘルパー関数
// ============================================================

async function apiFetch(url) {
  const res = await fetch(url, { signal: AbortSignal.timeout(10000) });
  if (!res.ok) throw new Error(`API ${res.status}: ${url}`);
  return res.json();
}

async function insertBQ(table, rows) {
  try {
    await bigquery.dataset(DATASET).table(table).insert(rows);
  } catch (err) {
    // テーブルが存在しない場合は無視(初回はBQコンソールで作成)
    if (err.code === 404) {
      console.warn(`Table ${table} not found, skipping insert`);
    } else {
      throw err;
    }
  }
}

function buildMarketSummary(latest, snapshots, klines4h, klines1d, liquidations) {
  // 価格変動
  const prices = snapshots.map(s => s.price).reverse();
  const ois = snapshots.map(s => s.open_interest).reverse();

  // 4H足のMA計算
  const closes4h = klines4h.map(k => k.close).reverse();
  const sma20_4h = closes4h.length >= 20 ? closes4h.slice(-20).reduce((a, b) => a + b) / 20 : null;
  const sma50_4h = closes4h.length >= 50 ? closes4h.slice(-50).reduce((a, b) => a + b) / 50 : null;

  // 日足のMA計算
  const closes1d = klines1d.map(k => k.close).reverse();
  const sma20_1d = closes1d.length >= 20 ? closes1d.slice(-20).reduce((a, b) => a + b) / 20 : null;
  const sma50_1d = closes1d.length >= 50 ? closes1d.slice(-50).reduce((a, b) => a + b) / 50 : null;
  const sma200_1d = closes1d.length >= 90 ? closes1d.slice(-90).reduce((a, b) => a + b) / 90 : null; // 90日分しかないので近似

  // OI変化
  const oiNow = latest.open_interest;
  const oiChange = ois.length > 12 ? ((oiNow - ois[ois.length - 13]) / ois[ois.length - 13] * 100) : 0;

  // 清算サマリー
  const recentLiq = liquidations.slice(0, 20);
  const longLiq = recentLiq.filter(l => l.side === 'LONG_LIQUIDATED');
  const shortLiq = recentLiq.filter(l => l.side === 'SHORT_LIQUIDATED');

  return {
    current_price: latest.price,
    price_change_24h_pct: latest.price_change_24h,
    high_24h: latest.high_24h,
    low_24h: latest.low_24h,
    volume_24h_usd: latest.volume_24h,
    open_interest_btc: latest.open_interest,
    open_interest_usd: latest.open_interest_usd,
    oi_change_1h_pct: oiChange,
    funding_rate: latest.funding_rate,
    funding_rate_annualized: latest.funding_rate * 3 * 365 * 100,
    mark_price: latest.mark_price,
    index_price: latest.index_price,
    spread: latest.spread,
    bid_ask_ratio_top5: latest.bid_depth_top5 / (latest.ask_depth_top5 || 1),
    bid_ask_ratio_top20: latest.bid_depth_top20 / (latest.ask_depth_top20 || 1),
    buy_sell_ratio_recent: latest.buy_volume_recent / (latest.sell_volume_recent || 1),
    sma20_4h, sma50_4h,
    sma20_1d, sma50_1d, sma200_1d,
    price_vs_sma20_4h: sma20_4h ? ((latest.price - sma20_4h) / sma20_4h * 100) : null,
    price_vs_sma50_1d: sma50_1d ? ((latest.price - sma50_1d) / sma50_1d * 100) : null,
    recent_long_liquidations: longLiq.length,
    recent_short_liquidations: shortLiq.length,
    recent_long_liq_usd: longLiq.reduce((s, l) => s + l.usd_value, 0),
    recent_short_liq_usd: shortLiq.reduce((s, l) => s + l.usd_value, 0),
    klines_4h_last5: klines4h.slice(0, 5).map(k => ({
      time: k.timestamp, o: k.open, h: k.high, l: k.low, c: k.close, v: k.volume
    })),
    klines_1d_last5: klines1d.slice(0, 5).map(k => ({
      time: k.timestamp, o: k.open, h: k.high, l: k.low, c: k.close, v: k.volume
    })),
  };
}

function buildTraderPrompt(trader, tweets, market) {
  const traderProfiles = {
    smile_danjer: {
      name: 'smile_danjer',
      style: `サイクル理論(4H/30日/90日/1500日)を最重視。フラクタル分析で過去チャートと現在を重ねる。
OI/FR/清算データで需給を読む。エリオット波動でカウント。
4Hサイクル60-80本が核。トランスレーション(右/左)で方向判断。
フィボ0.5が最重要。AM5:00(NY引け)反転アノマリー。木曜最弱。
RR比1:2以上でのみエントリー。レバレッジは状況で変動。`,
    },
    '4HpO4Q9Dz3CWkhV': {
      name: 'ronpochi',
      style: `フラクタル分析(過去チャートの類似パターンマッチ)が核。
チャネルライン+フィボナッチ+水平線のライントレード。
5分割エントリー(最大ポジの50%)。チャネル上限ショート/下限ロング。
損切りした日はノーポジ。わからない時もノーポジ。
月足→週足→日足→4H→1Hの順で必ず上位足から確認。
ダブルトップショート多用。建値ストップ→トレイリング。`,
    },
  };

  const profile = traderProfiles[trader] || { name: trader, style: 'Unknown trader' };

  // ツイートを時系列でフォーマット
  const tweetText = tweets.map(t => {
    const date = t.created_at || t.date || 'unknown';
    const media = t.media ? `[画像${t.media.photos?.length || 0}枚]` : '';
    return `[${date}] ${t.text} ${media}`;
  }).join('\n---\n');

  return `あなたは${profile.name}というBTCトレーダーです。以下はあなたの過去の全投稿です。
あなたの投稿から読み取れるトレードスタイル:
${profile.style}

=== あなたの過去の投稿 (${tweets.length}件) ===
${tweetText}

=== 現在の相場データ ===
${JSON.stringify(market, null, 2)}

=== 指示 ===
上記のあなたの投稿履歴とトレードスタイルに基づいて、現在の相場を分析し、今あなたならどう判断するかを回答してください。

あなたの過去の投稿で示した判断基準・手法・考え方を忠実に再現してください。
単純なルールの適用ではなく、あなたが実際に相場を見ている時のように、複数の情報を総合的に判断してください。

以下のJSON形式で回答:
{
  "action": "LONG" | "SHORT" | "CLOSE" | "HOLD" | "WAIT",
  "direction": "bullish" | "bearish" | "neutral",
  "confidence": 0-100,
  "leverage": レバレッジ倍率(数値),
  "position_size_pct": 資金の何%を投入するか(数値),
  "entry_price": エントリー価格(指値の場合),
  "stop_loss": 損切り価格,
  "take_profit": 利確価格,
  "reasoning": "判断理由を詳細に。サイクル・フラクタル・OI・FR等の各要素をどう読んだか",
  "cycle_analysis": "現在のサイクル位置の分析",
  "risk_assessment": "リスク要因",
  "next_check": "次に確認すべきタイミングや条件"
}`;
}

// ============================================================
// fetchNewTweets: X新規投稿を定期取得してGCSに保存
// danjer: 1時間毎, 他: 週1回
// ============================================================

const X_BEARER = 'AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs=1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA';
const X_ACCOUNTS = {
  smile_danjer: { userId: null, interval: 'hourly' },
  '4HpO4Q9Dz3CWkhV': { userId: null, interval: 'weekly' },
  CryptoHayes: { userId: null, interval: 'weekly' },
  '_Checkmatey_': { userId: null, interval: 'weekly' },
  BobLoukas: { userId: null, interval: 'weekly' },
  LynAldenContact: { userId: null, interval: 'weekly' },
  PeterLBrandt: { userId: null, interval: 'weekly' },
};

async function getGuestToken() {
  const res = await fetch('https://api.twitter.com/1.1/guest/activate.json', {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${X_BEARER}` },
    signal: AbortSignal.timeout(10000),
  });
  const data = await res.json();
  return data.guest_token;
}

async function getXUserId(handle, guestToken) {
  const variables = JSON.stringify({ screen_name: handle, withSafetyModeUserFields: true });
  const features = JSON.stringify({ hidden_profile_subscriptions_enabled: true, rweb_tipjar_consumption_enabled: true, responsive_web_graphql_exclude_directive_enabled: true, verified_phone_label_enabled: false, responsive_web_graphql_timeline_navigation_enabled: true, responsive_web_graphql_skip_user_profile_image_extensions_enabled: false });
  const url = `https://twitter.com/i/api/graphql/IGgvgiOx4QZndDHuD3x9TQ/UserByScreenName?variables=${encodeURIComponent(variables)}&features=${encodeURIComponent(features)}`;
  const res = await fetch(url, { headers: { 'Authorization': `Bearer ${X_BEARER}`, 'x-guest-token': guestToken, 'content-type': 'application/json' }, signal: AbortSignal.timeout(10000) });
  const data = await res.json();
  return data?.data?.user?.result?.rest_id || null;
}

async function getXUserTweets(userId, guestToken) {
  const variables = JSON.stringify({ userId, count: 100, includePromotedContent: false, withQuickPromoteEligibilityTweetFields: true, withVoice: true, withV2Timeline: true });
  const features = JSON.stringify({ rweb_tipjar_consumption_enabled: true, responsive_web_graphql_exclude_directive_enabled: true, verified_phone_label_enabled: false, creator_subscriptions_tweet_preview_api_enabled: true, responsive_web_graphql_timeline_navigation_enabled: true, responsive_web_graphql_skip_user_profile_image_extensions_enabled: false, communities_web_enable_tweet_community_results_fetch: true, c9s_tweet_anatomy_moderator_badge_enabled: true, articles_preview_enabled: true, responsive_web_edit_tweet_api_enabled: true, graphql_is_translatable_rweb_tweet_is_translatable_enabled: true, view_counts_everywhere_api_enabled: true, longform_notetweets_consumption_enabled: true, responsive_web_twitter_article_tweet_consumption_enabled: true, tweet_awards_web_tipping_enabled: false, freedom_of_speech_not_reach_fetch_enabled: true, standardized_nudges_misinfo: true, tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled: true, rweb_video_timestamps_enabled: true, longform_notetweets_rich_text_read_enabled: true, longform_notetweets_inline_media_enabled: true, responsive_web_enhance_cards_enabled: false });
  const url = `https://twitter.com/i/api/graphql/x3B_xLqC0yZawOB7WQhaVQ/UserTweets?variables=${encodeURIComponent(variables)}&features=${encodeURIComponent(features)}`;
  const res = await fetch(url, { headers: { 'Authorization': `Bearer ${X_BEARER}`, 'x-guest-token': guestToken, 'content-type': 'application/json' }, signal: AbortSignal.timeout(15000) });
  const data = await res.json();
  const tweets = [];
  for (const inst of (data?.data?.user?.result?.timeline_v2?.timeline?.instructions || [])) {
    for (const entry of (inst.entries || [])) {
      const result = entry?.content?.itemContent?.tweet_results?.result;
      if (!result?.legacy) continue;
      const l = result.legacy;
      tweets.push({ status_id: l.id_str, text: l.full_text, created_at: l.created_at, media: (l.entities?.media || []).map(m => ({ type: m.type, url: m.media_url_https })) });
    }
  }
  return tweets;
}

functions.http('fetchNewTweets', async (req, res) => {
  try {
    const mode = req.query.mode || 'hourly';
    const targetHandle = req.query.handle;
    const results = {};
    const guestToken = await getGuestToken();
    if (!guestToken) throw new Error('Failed to get guest token');

    for (const [handle, config] of Object.entries(X_ACCOUNTS)) {
      if (targetHandle && handle !== targetHandle) continue;
      if (mode !== config.interval && !targetHandle) continue;
      try {
        let userId = config.userId;
        if (!userId) {
          userId = await getXUserId(handle, guestToken);
          if (!userId) { results[handle] = 'user not found'; continue; }
          X_ACCOUNTS[handle].userId = userId;
        }
        let latestId = '0';
        try {
          const [file] = await storage.bucket(GCS_BUCKET).file(`tweets/${handle}_tweets.json`).download();
          const existing = JSON.parse(file.toString());
          if (existing.tweets?.length > 0) latestId = existing.tweets.reduce((max, t) => t.status_id > max ? t.status_id : max, '0');
        } catch (e) {}
        const newTweets = await getXUserTweets(userId, guestToken);
        const genuinelyNew = newTweets.filter(t => t.status_id > latestId);
        if (genuinelyNew.length === 0) { results[handle] = { new: 0 }; continue; }
        // fxtwitter APIで画像URL補完
        for (const tweet of genuinelyNew) {
          try {
            const fxRes = await fetch(`https://api.fxtwitter.com/${handle}/status/${tweet.status_id}`, { signal: AbortSignal.timeout(5000) });
            if (fxRes.ok) {
              const fx = await fxRes.json();
              const media = fx.tweet?.media;
              if (media?.photos?.length > 0) tweet.media = { photos: media.photos.map(p => ({ url: p.url, width: p.width, height: p.height })) };
              if (media?.videos?.length > 0) { tweet.media = tweet.media || {}; tweet.media.videos = media.videos.map(v => ({ url: v.url, thumbnail: v.thumbnail_url })); }
              if (fx.tweet?.created_at) tweet.created_at = fx.tweet.created_at;
            }
          } catch (e) {}
        }
        let existing = { handle, tweets: [] };
        try { const [file] = await storage.bucket(GCS_BUCKET).file(`tweets/${handle}_tweets.json`).download(); existing = JSON.parse(file.toString()); } catch (e) {}
        existing.tweets = [...existing.tweets, ...genuinelyNew];
        existing.tweets.sort((a, b) => a.status_id.localeCompare(b.status_id));
        existing.fetched_count = existing.tweets.length;
        existing.last_updated = new Date().toISOString();
        await storage.bucket(GCS_BUCKET).file(`tweets/${handle}_tweets.json`).save(JSON.stringify(existing, null, 2), { contentType: 'application/json' });
        results[handle] = { new: genuinelyNew.length, total: existing.tweets.length };
      } catch (e) { results[handle] = { error: e.message }; }
      await new Promise(r => setTimeout(r, 1000));
    }
    console.log('fetchNewTweets:', JSON.stringify(results));
    res.json({ success: true, mode, results });
  } catch (err) {
    console.error('fetchNewTweets error:', err);
    res.status(500).json({ error: err.message });
  }
});
