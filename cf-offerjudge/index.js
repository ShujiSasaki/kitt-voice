const functions = require('@google-cloud/functions-framework');
const { BigQuery } = require('@google-cloud/bigquery');
const { Storage } = require('@google-cloud/storage');
// Firebase RTDB via REST API (no SDK needed)

// --- Config ---
const PROJECT_ID = 'gen-lang-client-0549297663';
const DATASET = 'ubereats_analytics';
const FIREBASE_DB_URL = 'https://ubereats-kitt-default-rtdb.asia-southeast1.firebasedatabase.app';
const FIREBASE_DB_SECRET = process.env.FIREBASE_DB_SECRET || '';
const GEMINI_API_KEY = process.env.GEMINI_API_KEY || '';
const CF_API_KEY = process.env.CF_API_KEY || '';
const GEMINI_MODEL = 'gemini-2.5-flash';
const GCS_BUCKET = 'kitt-screenshots-0549297663';

// --- Init ---
const bigquery = new BigQuery({ projectId: PROJECT_ID });
const storage = new Storage({ projectId: PROJECT_ID });

// --- GCS Screenshot Upload ---
async function uploadScreenshot(base64Data, prefix) {
  try {
    const ext = base64Data.startsWith('/9j/') ? 'jpg' : 'png';
    const mime = ext === 'jpg' ? 'image/jpeg' : 'image/png';
    const filename = `${prefix}_${Date.now()}.${ext}`;
    const bucket = storage.bucket(GCS_BUCKET);
    const file = bucket.file(filename);
    const buffer = Buffer.from(base64Data, 'base64');
    await file.save(buffer, { contentType: mime, metadata: { cacheControl: 'public, max-age=86400' } });
    return `https://storage.googleapis.com/${GCS_BUCKET}/${filename}`;
  } catch (e) {
    console.warn('GCS upload error:', e.message);
    return null;
  }
}
// Firebase RTDB accessed via REST API

// --- Auth Helper ---
function checkApiKey(req) {
  if (!CF_API_KEY) return true;
  const key = req.headers['x-api-key'] || req.query.key || '';
  return key === CF_API_KEY;
}

// --- In-Memory Cache (persists between warm requests) ---
const cache = {
  coefficients: { data: null, expiry: 0 },
  storeHistory: new Map(),  // storeName -> { data, expiry }
  recentTrends: { data: null, expiry: 0 }
};
const CACHE_TTL_COEFFICIENTS = 10 * 60 * 1000;  // 10分
const CACHE_TTL_TRENDS = 2 * 60 * 1000;          // 2分
const CACHE_TTL_STORE = 5 * 60 * 1000;           // 5分

// ============================================================
// ENDPOINT 1: /offerJudge - Main offer judgment
// ============================================================
functions.http('offerJudge', async (req, res) => {
  const startTime = Date.now();
  try {
    // Warmup ping (Cloud Scheduler GET)
    if (req.method === 'GET') {
      return res.status(200).json({ status: 'warm', timestamp: new Date().toISOString() });
    }
    if (req.method !== 'POST') {
      return res.status(405).json({ error: 'Method not allowed' });
    }
    if (!checkApiKey(req)) {
      return res.status(401).json({ error: 'Unauthorized' });
    }

    let body = req.body; if(body[""]&&typeof body[""]=="object") body=body[""];
    const {
      lat, lng, address, wireless_charging,
      ocr_text,
      image_base64,
      store_name: rawStoreName,
      reward: rawReward,
      distance_km: rawDistance,
      duration_min: rawDuration
    } = body;

    // Step 1: Parse offer data (from OCR text or explicit fields)
    let storeName = rawStoreName || '';
    let reward = parseFloat(rawReward) || 0;
    let distanceKm = parseFloat(rawDistance) || 0;
    let durationMin = parseInt(rawDuration) || 0;

    if (ocr_text && (!storeName || !reward)) {
      const parsed = parseOcrText(ocr_text);
      storeName = storeName || parsed.storeName;
      reward = reward || parsed.reward;
      distanceKm = distanceKm || parsed.distanceKm;
      durationMin = durationMin || parsed.durationMin;
    }

    // Step 2: Parallel fetch - coefficients + store history + recent trends + weather
    const [coefficients, storeHistory, recentTrends, questInfo, weather] = await Promise.all([
      getCoefficients(),
      getStoreHistory(storeName),
      getRecentTrends(),
      getLatestContext('quest'),
      getWeather(lat, lng)
    ]);

    // Step 3: Need Gemini for image analysis? (fallback if OCR failed)
    let geminiAnalysis = null;
    if (image_base64 && (!reward || !storeName)) {
      geminiAnalysis = await analyzeOfferImage(image_base64, coefficients);
      if (geminiAnalysis) {
        storeName = storeName || geminiAnalysis.store_name || '';
        reward = reward || geminiAnalysis.reward || 0;
        distanceKm = distanceKm || geminiAnalysis.distance_km || 0;
        durationMin = durationMin || geminiAnalysis.duration_min || 0;
      }
    }

    // Step 4: Scoring calculation
    const now = new Date();
    const hourJST = (now.getUTCHours() + 9) % 24;
    const dayOfWeek = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'][now.getUTCDay()];
    const isWeekend = dayOfWeek === 'Sat' || dayOfWeek === 'Sun';

    const score = calculateScore({
      reward, distanceKm, durationMin,
      coefficients, storeHistory, recentTrends,
      hourJST, isWeekend, wireless_charging, questInfo, weather
    });

    const decision = score.total >= score.threshold ? 'accept' : 'reject';
    const confidence = score.total >= score.threshold * 1.3 ? 'high'
      : score.total >= score.threshold * 0.8 ? 'medium' : 'low';

    const estHourlyRate = durationMin > 0 ? (reward / durationMin) * 60 : 0;

    const reason = buildDecisionReason(decision, score, reward, distanceKm, durationMin, estHourlyRate, coefficients);

    // Step 5: Parallel write - BigQuery + Firebase RTDB + GCS screenshot
    const logId = `offer_${Date.now()}_${Math.random().toString(36).substr(2,6)}`;
    const responseTimeMs = Date.now() - startTime;
    const offerImageUrl = image_base64 ? await uploadScreenshot(image_base64, 'offer') : null;

    // [FIX #3] TTS text: accept/reject で明確に指示を変える
    const ttsText = buildTtsText(decision, confidence, score, reward, distanceKm, durationMin, estHourlyRate, storeName, coefficients);

    // RTDB書き込みURL: シークレット認証付き
    const rtdbUrl = FIREBASE_DB_URL + '/offer_tts.json' + (FIREBASE_DB_SECRET ? '?auth=' + FIREBASE_DB_SECRET : '');

    // BQ insert と RTDB write を独立実行（RTDB失敗でBQを巻き込まない）
    await insertOfferLog({
      logId, lat, lng, address, wireless_charging,
      storeName, reward, distanceKm, durationMin,
      decision, confidence, estHourlyRate, reason,
      responseTimeMs, hourJST, dayOfWeek,
      weather: weather ? weather.condition : null,
      scoreDetail: JSON.stringify(score),
      rawGeminiResponse: geminiAnalysis ? JSON.stringify(geminiAnalysis) : null,
      rawOcrText: ocr_text || null,
      imageUrl: offerImageUrl
    });
    fetch(rtdbUrl, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          offer: { decision, confidence, store_name: storeName, reward, distance_km: distanceKm, duration_min: durationMin, estimated_hourly_rate: Math.round(estHourlyRate), reason, score: Math.round(score.total * 100) / 100 },
          context: { hour_jst: hourJST, is_weekend: isWeekend },
          timestamp: new Date().toISOString()
        })
      }).catch(e => console.warn('RTDB write error:', e.message));

    // Step 6: Response
    const responseBody = {
      decision,
      confidence,
      estimated_hourly_rate: Math.round(estHourlyRate),
      score: Math.round(score.total * 100) / 100,
      threshold: Math.round(score.threshold * 100) / 100,
      reason,
      tts_text: ttsText,
      store_name: storeName,
      reward,
      distance_km: distanceKm,
      duration_min: durationMin,
      response_time_ms: responseTimeMs
    };

    res.status(200).json(responseBody);

  } catch (error) {
    console.error('offerJudge error:', error);
    const responseTimeMs = Date.now() - startTime;
    res.status(500).json({
      decision: 'error',
      reason: error.message,
      response_time_ms: responseTimeMs
    });
  }
});

// ============================================================
// ENDPOINT 2: /nandemoBox - Anything box (context submission)
// ============================================================
functions.http('nandemoBox', async (req, res) => {
  const startTime = Date.now();
  try {
    if (req.method !== 'POST') {
      return res.status(405).json({ error: 'Method not allowed' });
    }
    if (!checkApiKey(req)) {
      return res.status(401).json({ error: 'Unauthorized' });
    }

    const { image_base64, ocr_text, lat, lng } = req.body;

    // Step 1: Gemini分析のみ先に実行 (GCSはレスポンス後)
    const analysisResult = image_base64 ? await analyzeNandemoImage(image_base64, ocr_text) :
      ocr_text ? await analyzeNandemoText(ocr_text) : null;

    if (!analysisResult) {
      return res.status(400).json({ error: 'No image or text provided' });
    }

    const logId = `ctx_${Date.now()}_${Math.random().toString(36).substr(2,6)}`;
    let logType = analysisResult.type || 'nandemo';

    // Step 2: レスポンスを即返す (通知表示用にsummaryを1行に整形)
    const displaySummary = (analysisResult.summary || '').replace(/\n/g, ' ').substring(0, 80);
    res.status(200).json({
      status: 'ok',
      type: analysisResult.type,
      summary: displaySummary,
      processing_time_ms: Date.now() - startTime
    });

    // Step 3: GCSアップロード (レスポンス後にバックグラウンドで)
    let imageUrl = null;
    if (image_base64) {
      imageUrl = await uploadScreenshot(image_base64, 'nandemo').catch(() => null);
    }

    // Step 3: バックグラウンドでBQ書き込み + sync (レスポンス後)
    try {
      // Merge consecutive accepted entries (within 60s) into one
      let merged = false;
      if (logType === 'accepted') {
        try {
          const [recentRows] = await bigquery.query({
            query: `SELECT log_id, summary FROM \`${PROJECT_ID}.${DATASET}.context_logs\` WHERE type = 'accepted' AND timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 60 SECOND) ORDER BY timestamp DESC LIMIT 1`
          });
          if (recentRows.length > 0) {
            await bigquery.query({
              query: `UPDATE \`${PROJECT_ID}.${DATASET}.context_logs\` SET summary = @summary, ai_note = CONCAT(IFNULL(ai_note,''), ' | ', @note) WHERE log_id = @logId`,
              params: { summary: analysisResult.summary || recentRows[0].summary, note: analysisResult.ai_note || '', logId: recentRows[0].log_id }
            });
            merged = true;
          }
        } catch(e) { console.warn('merge check error:', e.message); }
      }

      // 同一案件の追加スクショ判定: 直前エントリと画像内容が同じ案件か判断して画像追記
      if (!merged && imageUrl) {
        try {
          const [recentEntries] = await bigquery.query({
            query: `SELECT log_id, type, summary, structured_data, image_url FROM \`${PROJECT_ID}.${DATASET}.context_logs\` WHERE timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 5 MINUTE) ORDER BY timestamp DESC LIMIT 1`,
            params: {}
          });
          if (recentEntries.length > 0) {
            const prev = recentEntries[0];
            let isSame = false;
            const curData = analysisResult.structured_data || {};
            let prevData = {};
            try { prevData = typeof prev.structured_data === 'string' ? JSON.parse(prev.structured_data) : (prev.structured_data || {}); } catch(e) {}

            // 判定1: result/order_detail → 店名一致
            if ((logType === 'result' || logType === 'order_detail') && prev.type === logType) {
              const curStore = (curData.store_name || '').replace(/\s/g, '');
              const prevStore = (prevData.store_name || '').replace(/\s/g, '');
              if (curStore && prevStore && curStore.substring(0, 6) === prevStore.substring(0, 6)) isSame = true;
            }
            // 判定2: quest → quest_type + quest_period一致
            if (logType === 'quest' && prev.type === 'quest') {
              if (curData.quest_type && curData.quest_type === prevData.quest_type) {
                if (curData.quest_period && curData.quest_period === prevData.quest_period) isSame = true;
                if (!curData.quest_period && !prevData.quest_period) isSame = true; // 雨クエスト等period無し同士
              }
            }
            // 判定3: accepted → 店名一致
            if (logType === 'accepted' && prev.type === 'accepted') {
              const curStore = (curData.store_name || '').replace(/\s/g, '');
              const prevStore = (prevData.store_name || '').replace(/\s/g, '');
              if (curStore && prevStore && curStore.substring(0, 6) === prevStore.substring(0, 6)) isSame = true;
            }
            // 判定4: nandemo同士 → summary先頭10文字一致
            if (logType === 'nandemo' && prev.type === 'nandemo') {
              const curKey = (analysisResult.summary || '').substring(0, 10);
              const prevKey = (prev.summary || '').substring(0, 10);
              if (curKey === prevKey && curKey.length > 3) isSame = true;
            }

            if (isSame) {
              const existingUrls = prev.image_url || '';
              const newUrls = existingUrls ? existingUrls + ',' + imageUrl : imageUrl;
              await bigquery.query({
                query: `UPDATE \`${PROJECT_ID}.${DATASET}.context_logs\` SET image_url = @urls WHERE log_id = @logId`,
                params: { urls: newUrls, logId: prev.log_id }
              });
              merged = true;
            }
          }
        } catch(e) { /* streaming buffer等は無視 */ }
      }

      const bgTasks = [];
      if (!merged) {
        bgTasks.push(bigquery.dataset(DATASET).table('context_logs').insert([{
          log_id: logId,
          timestamp: BigQuery.timestamp(new Date()),
          type: logType,
          summary: analysisResult.summary || '',
          structured_data: JSON.stringify(analysisResult.structured_data || {}),
          ai_note: analysisResult.ai_note || '',
          raw_gemini_response: JSON.stringify(analysisResult),
          image_size_kb: image_base64 ? Math.round(image_base64.length * 0.75 / 1024) : 0,
          image_url: imageUrl || null,
          processing_time_sec: (Date.now() - startTime) / 1000
        }]));
      }

      // Sync + RTDB in parallel
      let syncResult = null;
      if ((analysisResult.type === 'result' || analysisResult.type === 'order_detail') && analysisResult.structured_data) {
        bgTasks.push(syncDeliveryResult(logId, analysisResult.structured_data).then(r => { syncResult = r; }).catch(e => console.warn('sync error:', e.message)));
      }
      if (analysisResult.coefficient_updates) {
        bgTasks.push(updateCoefficients(analysisResult.coefficient_updates).catch(e => console.warn('coeff error:', e.message)));
      }

      await Promise.all(bgTasks);

      // RTDB notification (fire and forget)
      const nandemoRtdbUrl = FIREBASE_DB_URL + '/offer_tts.json' + (FIREBASE_DB_SECRET ? '?auth=' + FIREBASE_DB_SECRET : '');
      fetch(nandemoRtdbUrl, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          offer: { reward: 0, distance: 0, duration: 0, store_name: '', nandemo_type: analysisResult.type || 'nandemo', nandemo_summary: analysisResult.summary || '', nandemo_sync: syncResult },
          timestamp: Date.now(), is_nandemo: true
        })
      }).catch(e => console.warn('RTDB write error:', e.message));
    } catch(bgErr) {
      console.error('nandemoBox background error:', bgErr);
    }

  } catch (error) {
    console.error('nandemoBox error:', error);
    if (!res.headersSent) res.status(500).json({ error: error.message });
  }
});

// ============================================================
// ENDPOINT 3: /chargingEvent - Wireless charging ON/OFF
// ============================================================
functions.http('chargingEvent', async (req, res) => {
  try {
    if (req.method !== 'POST') {
      return res.status(405).json({ error: 'Method not allowed' });
    }
    if (!checkApiKey(req)) {
      return res.status(401).json({ error: 'Unauthorized' });
    }

    const { wireless_charging, lat, lng } = req.body;
    const now = new Date();
    const jstOffset = 9 * 60 * 60 * 1000;
    const jst = new Date(now.getTime() + jstOffset);

    await bigquery.dataset(DATASET).table('charging_logs').insert([{
      timestamp_utc: now.toISOString(),
      timestamp_jst: jst.toISOString().replace('T',' ').substring(0,19),
      wireless_charging: wireless_charging === true || wireless_charging === 'true',
      lat: parseFloat(lat) || 0,
      lng: parseFloat(lng) || 0,
      near_parking: false,
      is_work_session: true,
      cleanup_after: null
    }]);

    res.status(200).json({
      status: 'ok',
      event: wireless_charging ? 'charging_on' : 'charging_off',
      timestamp: now.toISOString()
    });

  } catch (error) {
    console.error('chargingEvent error:', error);
    res.status(500).json({ error: error.message });
  }
});

// ============================================================
// ENDPOINT 3.5: /offerScreenshot - Attach screenshot to latest offer
// ============================================================
functions.http('offerScreenshot', async (req, res) => {
  res.set('Access-Control-Allow-Origin', '*');
  if (req.method === 'OPTIONS') { res.set('Access-Control-Allow-Headers', 'Content-Type, X-API-Key'); return res.status(204).send(''); }
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });
  if (!checkApiKey(req)) return res.status(401).json({ error: 'Unauthorized' });
  try {
    let body = req.body; if(body[""]&&typeof body[""]=="object") body=body[""];
    const { image_base64 } = body;
    if (!image_base64) return res.status(400).json({ error: 'No image' });
    // Upload to GCS
    const imageUrl = await uploadScreenshot(image_base64, 'offer');
    if (!imageUrl) return res.status(500).json({ error: 'Upload failed' });
    // Save URL to RTDB (instant) - PWA will match by timestamp
    const rtdbUrl = FIREBASE_DB_URL + '/offer_images.json' + (FIREBASE_DB_SECRET ? '?auth=' + FIREBASE_DB_SECRET : '');
    const ts = Date.now();
    await fetch(rtdbUrl.replace('.json', `/${ts}.json`), {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: imageUrl, t: ts })
    });
    // Also try BQ update (may fail due to streaming buffer, that's ok)
    bigquery.query({
      query: `UPDATE \`${PROJECT_ID}.${DATASET}.offer_logs\` SET image_url = @url WHERE log_id = (SELECT log_id FROM \`${PROJECT_ID}.${DATASET}.offer_logs\` WHERE timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 5 MINUTE) AND (image_url IS NULL OR image_url = '') ORDER BY timestamp DESC LIMIT 1)`,
      params: { url: imageUrl }
    }).catch(() => {}); // Ignore streaming buffer error
    res.status(200).json({ status: 'ok', image_url: imageUrl });
  } catch (e) {
    console.error('offerScreenshot error:', e);
    res.status(500).json({ error: e.message });
  }
});

// ============================================================
// ENDPOINT 4: /dashboardFeed - Recent logs for KITT dashboard
// ============================================================
functions.http('dashboardFeed', async (req, res) => {
  res.set('Access-Control-Allow-Origin', '*');
  if (req.method === 'OPTIONS') { res.set('Access-Control-Allow-Headers', 'Content-Type'); return res.status(204).send(''); }
  try {
    const since = req.query.since || new Date(Date.now() - 24*60*60*1000).toISOString();
    const [offerRows] = await bigquery.query({
      query: `SELECT timestamp, gemini_decision as decision, store_name, offer_reward as reward, offer_distance as distance, offer_duration as duration, estimated_hourly_rate as hourly, decision_reason as reason, confidence, ROUND(SAFE_CAST(JSON_VALUE(decision_reason_detail, '$.total') AS FLOAT64), 2) as score, image_url FROM \`${PROJECT_ID}.${DATASET}.offer_logs\` WHERE timestamp > @since ORDER BY timestamp DESC LIMIT 200`,
      params: { since }
    });
    const [nandemoRows] = await bigquery.query({
      query: `SELECT timestamp,
        CASE
          WHEN type = 'nandemo' AND REGEXP_CONTAINS(summary, r'"type":\\s*"(quest|accepted|result|quest_result|order_detail)"')
            THEN REGEXP_EXTRACT(summary, r'"type":\\s*"([^"]+)"')
          WHEN (type = 'nandemo' OR type = 'quest') AND REGEXP_CONTAINS(summary, r'(クエスト達成|乗車クエスト.*達成|乗車達成|クエスト.*件達成)')
            THEN 'quest_result'
          ELSE type END as type,
        REPLACE(
          CASE WHEN type = 'nandemo' AND REGEXP_CONTAINS(summary, r'"summary":\\s*"')
            THEN REGEXP_EXTRACT(summary, r'"summary":\\s*"([^"]+)"') ELSE summary END,
          'ピーク条件', 'ピーク') as summary,
        image_url
        FROM \`${PROJECT_ID}.${DATASET}.context_logs\` WHERE timestamp > @since ORDER BY timestamp DESC LIMIT 300`,
      params: { since }
    });
    res.status(200).json({ offers: offerRows, nandemo: nandemoRows });
  } catch (error) {
    console.error('dashboardFeed error:', error);
    res.status(500).json({ error: error.message });
  }
});

// ============================================================
// ENDPOINT 4.3: /externalResearch - 外部情報自動収集
// ============================================================
functions.http('externalResearch', async (req, res) => {
  res.set('Access-Control-Allow-Origin', '*');
  if (req.method === 'OPTIONS') { res.set('Access-Control-Allow-Headers', 'Content-Type'); return res.status(204).send(''); }
  try {
    const mode = req.query.mode || req.body?.mode || 'realtime'; // 'realtime' (10分) or 'daily'
    const results = [];

    if (mode === 'realtime') {
      // 1. X/Twitter風: Google News RSSでデリバリー関連ニュース検索
      const socialKws = ['Uber+福岡+配達', '出前館+福岡', 'UberEats+福岡', 'フードデリバリー+福岡'];
      for (const kw of socialKws) {
        try {
          const rssUrl = `https://news.google.com/rss/search?q=${encodeURIComponent(kw)}&hl=ja&gl=JP&ceid=JP:ja`;
          const rssResp = await fetch(rssUrl);
          const rssText = await rssResp.text();
          // Simple XML parse for <item><title>...</title><link>...</link><pubDate>...</pubDate></item>
          const items = [...rssText.matchAll(/<item>[\s\S]*?<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?<\/title>[\s\S]*?<link>(.*?)<\/link>[\s\S]*?<pubDate>(.*?)<\/pubDate>[\s\S]*?<\/item>/g)];
          for (const item of items.slice(0, 3)) {
            results.push({ source: 'GoogleNews', title: item[1].replace(/&amp;/g,'&').replace(/&lt;/g,'<').replace(/&gt;/g,'>'), url: item[2], published_at: item[3], search_query: kw });
          }
        } catch(e) { console.warn('RSS error:', kw, e.message); }
      }

      // 2. 交通情報: JARTIC的な情報 or Google検索
      try {
        const trafficKws = ['福岡+交通規制+今日', '福岡+渋滞+リアルタイム'];
        for (const kw of trafficKws) {
          const rssUrl = `https://news.google.com/rss/search?q=${encodeURIComponent(kw)}&hl=ja&gl=JP&ceid=JP:ja`;
          const rssResp = await fetch(rssUrl);
          const rssText = await rssResp.text();
          const items = [...rssText.matchAll(/<item>[\s\S]*?<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?<\/title>[\s\S]*?<link>(.*?)<\/link>[\s\S]*?<pubDate>(.*?)<\/pubDate>[\s\S]*?<\/item>/g)];
          for (const item of items.slice(0, 2)) {
            results.push({ source: 'Traffic', title: item[1].replace(/&amp;/g,'&'), url: item[2], published_at: item[3], search_query: kw });
          }
        }
      } catch(e) { console.warn('Traffic error:', e.message); }

      // 3. 5ch/Reddit風: 配達員コミュニティ情報
      try {
        const communityKws = ['UberEats+配達員+2026', 'フードデリバリー+配達+稼ぎ'];
        for (const kw of communityKws) {
          const rssUrl = `https://news.google.com/rss/search?q=${encodeURIComponent(kw)}&hl=ja&gl=JP&ceid=JP:ja`;
          const rssResp = await fetch(rssUrl);
          const rssText = await rssResp.text();
          const items = [...rssText.matchAll(/<item>[\s\S]*?<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?<\/title>[\s\S]*?<link>(.*?)<\/link>[\s\S]*?<pubDate>(.*?)<\/pubDate>[\s\S]*?<\/item>/g)];
          for (const item of items.slice(0, 2)) {
            results.push({ source: 'Community', title: item[1].replace(/&amp;/g,'&'), url: item[2], published_at: item[3], search_query: kw });
          }
        }
      } catch(e) {}

    } else if (mode === 'daily') {
      // 日次: 幅広い情報収集
      const dailyKws = [
        'UberEats+日本+最新+2026', '出前館+配達員+2026', 'フードデリバリー+料金改定',
        'Wolt+日本+2026', 'menu+配達+2026', 'ロケットナウ+配達',
        '福岡+イベント+今週', '福岡+マラソン+交通規制', '福岡+祭り+2026',
        'UberEats+インセンティブ+変更', 'フードデリバリー+法律+規制',
        '配達員+事故+保険', 'ギグワーカー+日本+制度'
      ];
      for (const kw of dailyKws) {
        try {
          const rssUrl = `https://news.google.com/rss/search?q=${encodeURIComponent(kw)}&hl=ja&gl=JP&ceid=JP:ja`;
          const rssResp = await fetch(rssUrl);
          const rssText = await rssResp.text();
          const items = [...rssText.matchAll(/<item>[\s\S]*?<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?<\/title>[\s\S]*?<link>(.*?)<\/link>[\s\S]*?<pubDate>(.*?)<\/pubDate>[\s\S]*?<\/item>/g)];
          for (const item of items.slice(0, 5)) {
            results.push({ source: 'DailyResearch', title: item[1].replace(/&amp;/g,'&').replace(/&lt;/g,'<').replace(/&gt;/g,'>'), url: item[2], published_at: item[3], search_query: kw });
          }
        } catch(e) {}
      }
    }

    // Deduplicate by title
    const seen = new Set();
    const unique = results.filter(r => {
      const key = r.title.substring(0, 50);
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });

    // BQに保存 (重複チェック: 同じタイトルがあればスキップ)
    if (unique.length > 0) {
      const rows = unique.map(r => ({
        id: `ext_${Date.now()}_${Math.random().toString(36).substr(2,6)}`,
        timestamp: BigQuery.timestamp(new Date()),
        source: r.source,
        title: r.title.substring(0, 500),
        url: r.url || '',
        description: '',
        published_at: r.published_at || '',
        search_query: r.search_query
      }));
      try {
        await bigquery.dataset(DATASET).table('external_research').insert(rows);
      } catch(e) {
        // Ignore duplicate errors
        if (!e.message?.includes('duplicate')) console.warn('BQ insert warning:', e.message?.substring(0, 200));
      }
    }

    // RTDB にサマリー保存 (KITTが参照)
    const rtdbUrl = FIREBASE_DB_URL + '/research.json' + (FIREBASE_DB_SECRET ? '?auth=' + FIREBASE_DB_SECRET : '');
    await fetch(rtdbUrl, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        last_updated: Date.now(),
        mode,
        latest_count: unique.length,
        latest_titles: unique.slice(0, 5).map(r => r.title.substring(0, 80))
      })
    });

    res.status(200).json({ status: 'ok', mode, collected: unique.length });
  } catch (e) {
    console.error('externalResearch error:', e);
    res.status(500).json({ error: e.message });
  }
});

// ============================================================
// ENDPOINT 4.34: /systemHealth - 自己診断・自己修復 (10分毎)
// ============================================================
functions.http('systemHealth', async (req, res) => {
  res.set('Access-Control-Allow-Origin', '*');
  if (req.method === 'OPTIONS') { res.set('Access-Control-Allow-Headers', 'Content-Type'); return res.status(204).send(''); }
  try {
    const issues = [];
    const fixes = [];

    // Check 1: reward=0のオファー（OCRパース失敗）
    const [rewardZero] = await bigquery.query({ query: `
      SELECT COUNT(*) as cnt FROM \`${PROJECT_ID}.${DATASET}.offer_logs\`
      WHERE offer_reward = 0 AND timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
    `});
    const r0 = rewardZero[0]?.cnt || 0;
    if (r0 > 0) issues.push({ severity: 'high', type: 'ocr_reward_zero', count: r0, msg: `過去24hで報酬0円が${r0}件（OCRパース失敗）` });

    // Check 2: duration=0のオファー
    const [durZero] = await bigquery.query({ query: `
      SELECT COUNT(*) as cnt FROM \`${PROJECT_ID}.${DATASET}.offer_logs\`
      WHERE offer_duration = 0 AND offer_reward > 0 AND timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
    `});
    const d0 = durZero[0]?.cnt || 0;
    if (d0 > 0) issues.push({ severity: 'high', type: 'ocr_duration_zero', count: d0, msg: `過去24hで時間0分が${d0}件（時給計算不能）` });

    // Check 3: ゴミ店名
    const [garbageStore] = await bigquery.query({ query: `
      SELECT COUNT(*) as cnt FROM \`${PROJECT_ID}.${DATASET}.offer_logs\`
      WHERE (LENGTH(store_name) <= 2 OR REGEXP_CONTAINS(store_name, r'^[0-9:]+$'))
        AND offer_reward > 0 AND timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
    `});
    const gs = garbageStore[0]?.cnt || 0;
    if (gs > 0) issues.push({ severity: 'medium', type: 'garbage_store', count: gs, msg: `過去24hでゴミ店名が${gs}件` });

    // Check 4: actual_payout未マッチ率
    const [matchRate] = await bigquery.query({ query: `
      SELECT
        COUNTIF(actual_payout IS NOT NULL) as matched,
        COUNT(*) as total
      FROM \`${PROJECT_ID}.${DATASET}.offer_logs\`
      WHERE gemini_decision = 'accept' AND timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
    `});
    const mr = matchRate[0];
    const matchPct = mr.total > 0 ? Math.round(mr.matched / mr.total * 100) : 0;
    if (matchPct < 30 && mr.total > 10) issues.push({ severity: 'high', type: 'low_match_rate', pct: matchPct, msg: `実績マッチ率${matchPct}%（目標95%）` });

    // Check 5: 係数の鮮度
    const [coeffAge] = await bigquery.query({ query: `
      SELECT MAX(last_updated) as latest FROM \`${PROJECT_ID}.${DATASET}.dynamic_coefficients\`
    `});
    const latestCoeff = coeffAge[0]?.latest?.value ? new Date(coeffAge[0].latest.value) : null;
    const coeffAgeH = latestCoeff ? Math.round((Date.now() - latestCoeff.getTime()) / 3600000) : 999;
    if (coeffAgeH > 48) issues.push({ severity: 'medium', type: 'stale_coefficients', hours: coeffAgeH, msg: `係数が${coeffAgeH}時間前から更新なし` });

    // Check 6: delivery_historyに未マッチのreward>0がある → 再マッチ試行
    const [unmatchedDeliveries] = await bigquery.query({ query: `
      SELECT COUNT(*) as cnt FROM \`${PROJECT_ID}.${DATASET}.delivery_history\` d
      WHERE d.reward > 0 AND d.store_name != ''
        AND NOT EXISTS (
          SELECT 1 FROM \`${PROJECT_ID}.${DATASET}.offer_logs\` o
          WHERE o.actual_payout IS NOT NULL
            AND REGEXP_REPLACE(o.store_name, r'\\s+', '') LIKE CONCAT('%', LEFT(REGEXP_REPLACE(d.store_name, r'\\s+', ''), 6), '%')
            AND ABS(TIMESTAMP_DIFF(o.timestamp, d.timestamp, HOUR)) < 6
        )
    `}).catch(() => [{ cnt: 0 }]);

    // Auto-fix: 未マッチdeliveryを再マッチ
    try {
      const [reMatch] = await bigquery.query({ query: `
        UPDATE \`${PROJECT_ID}.${DATASET}.offer_logs\` o
        SET actual_accepted = true, actual_payout = matched.reward,
            actual_duration_minutes = matched.duration, actual_distance_km = matched.distance
        FROM (
          SELECT o2.log_id as offer_log_id, d.reward, d.duration, d.distance,
            ROW_NUMBER() OVER (PARTITION BY o2.log_id ORDER BY
              CASE WHEN REGEXP_REPLACE(o2.store_name, r'\\s+', '') LIKE CONCAT('%', LEFT(REGEXP_REPLACE(d.store_name, r'\\s+', ''), 6), '%') THEN 0 ELSE 1 END,
              ABS(TIMESTAMP_DIFF(o2.timestamp, d.timestamp, SECOND))
            ) as rn
          FROM \`${PROJECT_ID}.${DATASET}.offer_logs\` o2
          JOIN \`${PROJECT_ID}.${DATASET}.delivery_history\` d
            ON d.reward > 0 AND d.store_name != ''
            AND o2.actual_accepted IS NULL AND o2.offer_reward > 0
            AND ABS(TIMESTAMP_DIFF(o2.timestamp, d.timestamp, HOUR)) < 6
            AND (
              REGEXP_REPLACE(o2.store_name, r'\\s+', '') LIKE CONCAT('%', LEFT(REGEXP_REPLACE(d.store_name, r'\\s+', ''), 6), '%')
              OR (o2.offer_reward BETWEEN d.reward * 0.7 AND d.reward * 1.3 AND ABS(TIMESTAMP_DIFF(o2.timestamp, d.timestamp, MINUTE)) < 60)
            )
        ) matched
        WHERE o.log_id = matched.offer_log_id AND matched.rn = 1
      `});
      const reMatchCount = reMatch?.numDmlAffectedRows || 0;
      if (reMatchCount > 0) fixes.push({ type: 're_match', count: reMatchCount, msg: `${reMatchCount}件の未マッチオファーを再突き合わせ` });
    } catch(e) { /* streaming buffer等で失敗しても無視 */ }

    // Check 7: 天気データの鮮度
    try {
      const weatherResp = await fetch(FIREBASE_DB_URL + '/weather/timestamp.json');
      const weatherTs = await weatherResp.json();
      const weatherAge = weatherTs ? Math.round((Date.now() - weatherTs) / 60000) : 999;
      if (weatherAge > 30) issues.push({ severity: 'low', type: 'stale_weather', minutes: weatherAge, msg: `天気データが${weatherAge}分前` });
    } catch(e) {}

    // Check 8: 異常な時給値 (推定時給が10万以上)
    const [abnormalHourly] = await bigquery.query({ query: `
      SELECT COUNT(*) as cnt FROM \`${PROJECT_ID}.${DATASET}.offer_logs\`
      WHERE estimated_hourly_rate > 100000 AND timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
    `});
    const ah = abnormalHourly[0]?.cnt || 0;
    if (ah > 0) issues.push({ severity: 'medium', type: 'abnormal_hourly', count: ah, msg: `異常時給(10万超)が${ah}件` });

    // Check 9: データ整合性クロスチェック (actual_payout件数がBQタブの表示と一致するか)
    try {
      const [crossCheck] = await bigquery.query({ query: `
        SELECT
          (SELECT COUNT(*) FROM \`${PROJECT_ID}.${DATASET}.offer_logs\` WHERE actual_payout IS NOT NULL) as bq_matched,
          (SELECT COUNT(*) FROM \`${PROJECT_ID}.${DATASET}.delivery_history\` WHERE reward > 0) as deliveries_with_reward,
          (SELECT COUNT(*) FROM \`${PROJECT_ID}.${DATASET}.offer_logs\` WHERE actual_payout IS NOT NULL AND offer_duration > 0 AND offer_reward > 0) as bq_matched_valid
      `});
      const cc = crossCheck[0];
      if (cc.deliveries_with_reward > 0 && cc.bq_matched < cc.deliveries_with_reward * 0.5) {
        issues.push({ severity: 'high', type: 'match_gap', msg: `delivery ${cc.deliveries_with_reward}件中 ${cc.bq_matched}件しかoffer_logsに紐付いてない` });
      }
      // BQタブのズレ分析が返すべき件数との整合性
      if (cc.bq_matched > 0 && cc.bq_matched_valid < cc.bq_matched * 0.8) {
        issues.push({ severity: 'medium', type: 'invalid_matched', msg: `紐付済${cc.bq_matched}件中 有効(reward>0,duration>0)は${cc.bq_matched_valid}件のみ` });
      }
    } catch(e) {}

    // Check 10: PDCA結果の妥当性 (重みの合計が1.0に近いか、閾値が異常でないか)
    try {
      const c = await getCoefficients();
      const weightSum = (c.weight_hourly_rate||0) + (c.weight_reward_per_km||0) + (c.weight_distance||0) + (c.weight_store_reputation||0) + (c.weight_market||0) + (c.weight_quest_adjusted||0) + (c.weight_opportunity||0);
      if (Math.abs(weightSum - 1.0) > 0.05) {
        issues.push({ severity: 'high', type: 'weight_sum_off', msg: `重みの合計が${weightSum.toFixed(3)}（1.0であるべき）` });
        // Auto-fix: 正規化
        const keys = ['weight_hourly_rate','weight_reward_per_km','weight_distance','weight_store_reputation','weight_market','weight_quest_adjusted','weight_opportunity'];
        const fixedWeights = {};
        for (const k of keys) fixedWeights[k] = Math.round(((c[k] || 0) / weightSum) * 1000) / 1000;
        await updateCoefficients(fixedWeights);
        cache.coefficients = { data: null, expiry: 0 };
        fixes.push({ type: 'normalize_weights', msg: `重みを正規化 (${weightSum.toFixed(3)}→1.000)` });
      }
      if (c.score_threshold > 1.5 || c.score_threshold < 0.3) {
        issues.push({ severity: 'high', type: 'threshold_extreme', msg: `閾値が${c.score_threshold}（異常値）` });
      }
    } catch(e) {}

    // Save report to RTDB
    const report = {
      timestamp: Date.now(),
      issues_count: issues.length,
      fixes_count: fixes.length,
      issues,
      fixes,
      status: issues.filter(i => i.severity === 'high').length > 0 ? 'warning' : 'healthy'
    };
    const rtdbUrl = FIREBASE_DB_URL + '/health.json' + (FIREBASE_DB_SECRET ? '?auth=' + FIREBASE_DB_SECRET : '');
    fetch(rtdbUrl, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(report) }).catch(() => {});

    res.status(200).json(report);
  } catch (e) {
    console.error('systemHealth error:', e);
    res.status(500).json({ error: e.message });
  }
});

// ============================================================
// ENDPOINT 4.35: /pdcaCycle - 日次PDCA自動最適化 (Cloud Scheduler 4:30AM)
// ============================================================
functions.http('pdcaCycle', async (req, res) => {
  res.set('Access-Control-Allow-Origin', '*');
  if (req.method === 'OPTIONS') { res.set('Access-Control-Allow-Headers', 'Content-Type'); return res.status(204).send(''); }
  try {
    const results = {};

    // Step 1: 係数再計算（実績データ優先）
    await recalculateCoefficients();
    results.coefficients = 'updated';

    // Step 2: 重み自動最適化
    results.optimization = await optimizeWeights();

    // Step 3: store_master再構築
    try {
      await bigquery.query({ query: `
        CREATE OR REPLACE TABLE \`${PROJECT_ID}.${DATASET}.store_master\` AS
        WITH all_names AS (
          SELECT store_name, COUNT(*) as cnt
          FROM \`${PROJECT_ID}.${DATASET}.offer_logs\`
          WHERE store_name != '' AND LENGTH(store_name) > 2
          GROUP BY store_name
        ),
        normalized AS (
          SELECT store_name, cnt,
            REGEXP_REPLACE(REGEXP_REPLACE(REGEXP_REPLACE(REGEXP_REPLACE(store_name,
              r"\\s*(McDonald's|Sukiya|Matsuya|Yoshinoya|Burrger King|Burger King|Gansoramen|NIKUNOANDES|SRILANKA|KOREAN DINING.*|VIETNAMESE.*|Bikkuri donkey|ganso hakata|Pizza Hut.*|SUBWAY.*|Karatora|kabeya|CoCo Ichibanya|Curry House.*)\\s*$", ''),
              r'\\s*LOTTERIA.*$', ''), r'\\s*ZETTERIA\\s*', ' '), r'[【】「」（）()]+', '') as name_clean
          FROM all_names
        ),
        cleaned AS (
          SELECT store_name, cnt, TRIM(REGEXP_REPLACE(REGEXP_REPLACE(name_clean, r'[　]+', ''), r'\\s{2,}', ' ')) as norm_key
          FROM normalized
        ),
        filtered AS (
          SELECT * FROM cleaned WHERE LENGTH(norm_key) >= 3
            AND NOT REGEXP_CONTAINS(norm_key, r'^[0-9:.,\\s]+$')
            AND REGEXP_CONTAINS(norm_key, r'[\\p{Han}\\p{Hiragana}\\p{Katakana}]')
        ),
        ranked AS (
          SELECT norm_key, store_name, cnt,
            ROW_NUMBER() OVER (PARTITION BY norm_key ORDER BY cnt DESC) as rn,
            SUM(cnt) OVER (PARTITION BY norm_key) as total_cnt
          FROM filtered
        )
        SELECT norm_key as store_id, store_name as canonical_name, total_cnt
        FROM ranked WHERE rn = 1 ORDER BY total_cnt DESC
      `});
      results.store_master = 'rebuilt';
    } catch(e) { results.store_master = 'error: ' + e.message; }

    // Step 4: PDCA結果をRTDBに保存
    const rtdbUrl = FIREBASE_DB_URL + '/pdca.json' + (FIREBASE_DB_SECRET ? '?auth=' + FIREBASE_DB_SECRET : '');
    await fetch(rtdbUrl, { method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ last_cycle: { timestamp: Date.now(), results } })
    });

    console.log('PDCA cycle completed:', JSON.stringify(results));
    res.status(200).json({ status: 'ok', results });
  } catch (e) {
    console.error('pdcaCycle error:', e);
    res.status(500).json({ error: e.message });
  }
});

// ============================================================
// ENDPOINT 4.4: /weatherCheck - 定期天気チェック (Cloud Scheduler)
// ============================================================
functions.http('weatherCheck', async (req, res) => {
  res.set('Access-Control-Allow-Origin', '*');
  if (req.method === 'OPTIONS') { res.set('Access-Control-Allow-Headers', 'Content-Type'); return res.status(204).send(''); }
  try {
    // 福岡中心部
    const lat = 33.59, lng = 130.40;
    const url = `https://api.open-meteo.com/v1/forecast?latitude=${lat}&longitude=${lng}&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m,precipitation&hourly=temperature_2m,precipitation_probability,precipitation,weather_code,wind_speed_10m&timezone=Asia/Tokyo&forecast_days=1`;
    const resp = await fetch(url);
    const data = await resp.json();

    const now = new Date();
    const jstHour = (now.getUTCHours() + 9) % 24;

    // 今後6時間の降水予報を抽出
    const hourly = data.hourly || {};
    const forecast = [];
    for (let i = 0; i < (hourly.time || []).length; i++) {
      // Open-Meteo returns local time (JST) as "2026-03-30T13:00"
      const fHour = parseInt((hourly.time[i] || '').split('T')[1]);
      if (isNaN(fHour)) continue;
      // 現在JST時刻から6時間先まで
      if (fHour >= jstHour && fHour < jstHour + 6) {
        forecast.push({
          hour: fHour,
          temp: hourly.temperature_2m?.[i],
          precip_prob: hourly.precipitation_probability?.[i],
          precip_mm: hourly.precipitation?.[i],
          weather_code: hourly.weather_code?.[i],
          wind: hourly.wind_speed_10m?.[i]
        });
      }
    }

    // 天気コード→日本語
    const weatherName = (code) => {
      if (code <= 1) return '晴れ';
      if (code <= 3) return '曇り';
      if (code <= 49) return '霧';
      if (code <= 59) return '小雨';
      if (code <= 69) return '雨';
      if (code <= 79) return 'みぞれ';
      if (code <= 82) return '強い雨';
      if (code <= 86) return '雪';
      if (code <= 99) return '雷雨';
      return '不明';
    };

    const current = data.current || {};
    const weatherData = {
      timestamp: Date.now(),
      current: {
        temp: current.temperature_2m,
        humidity: current.relative_humidity_2m,
        weather: weatherName(current.weather_code),
        weather_code: current.weather_code,
        wind: current.wind_speed_10m,
        precip_mm: current.precipitation
      },
      forecast: forecast.map(f => ({
        ...f,
        weather: weatherName(f.weather_code)
      })),
      rain_alert: forecast.some(f => f.precip_prob > 50) ? '降水注意' : forecast.some(f => f.precip_prob > 30) ? '降水可能性あり' : null
    };

    // RTDB に保存 (KITT PWAが読む)
    const rtdbUrl = FIREBASE_DB_URL + '/weather.json' + (FIREBASE_DB_SECRET ? '?auth=' + FIREBASE_DB_SECRET : '');
    await fetch(rtdbUrl, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(weatherData)
    });

    res.status(200).json({ status: 'ok', weather: weatherData });
  } catch (e) {
    console.error('weatherCheck error:', e);
    res.status(500).json({ error: e.message });
  }
});

// ============================================================
// ENDPOINT 4.5: /bqStats - BigQuery stats for KITT dashboard
// ============================================================
functions.http('bqStats', async (req, res) => {
  res.set('Access-Control-Allow-Origin', '*');
  if (req.method === 'OPTIONS') { res.set('Access-Control-Allow-Headers', 'Content-Type'); return res.status(204).send(''); }
  try {
    const [tables, coefficients, offerStats, contextStats, storeRanking, hourlyStats, offerGapRaw, storeWaitRaw, storeMasterRaw, questsRaw] = await Promise.all([
      // 1. Table row counts
      bigquery.query({ query: `
        SELECT 'offer_logs' as t, COUNT(*) as cnt, CAST(MIN(timestamp) AS STRING) as oldest, CAST(MAX(timestamp) AS STRING) as newest FROM \`${PROJECT_ID}.${DATASET}.offer_logs\`
        UNION ALL SELECT 'context_logs', COUNT(*), CAST(MIN(timestamp) AS STRING), CAST(MAX(timestamp) AS STRING) FROM \`${PROJECT_ID}.${DATASET}.context_logs\`
        UNION ALL SELECT 'delivery_history', COUNT(*), CAST(MIN(timestamp) AS STRING), CAST(MAX(timestamp) AS STRING) FROM \`${PROJECT_ID}.${DATASET}.delivery_history\`
        UNION ALL SELECT 'charging_logs', COUNT(*), MIN(timestamp_utc), MAX(timestamp_utc) FROM \`${PROJECT_ID}.${DATASET}.charging_logs\`
        UNION ALL SELECT 'dynamic_coefficients', COUNT(*), NULL, NULL FROM \`${PROJECT_ID}.${DATASET}.dynamic_coefficients\`
      `}).then(r => r[0]),
      // 2. All coefficients
      bigquery.query({ query: `SELECT coefficient_name, coefficient_value, last_updated, description FROM \`${PROJECT_ID}.${DATASET}.dynamic_coefficients\` ORDER BY coefficient_name` }).then(r => r[0]),
      // 3. Offer stats (last 7 days)
      bigquery.query({ query: `
        SELECT COUNT(*) as total, COUNTIF(gemini_decision='accept') as accepted, COUNTIF(gemini_decision='reject') as rejected,
        ROUND(AVG(offer_reward),0) as avg_reward, ROUND(AVG(offer_distance),2) as avg_dist, ROUND(AVG(offer_duration),0) as avg_dur,
        ROUND(AVG(estimated_hourly_rate),0) as avg_hourly,
        ROUND(AVG(CASE WHEN gemini_decision='accept' THEN estimated_hourly_rate END),0) as avg_hourly_accept,
        ROUND(AVG(CASE WHEN gemini_decision='reject' THEN estimated_hourly_rate END),0) as avg_hourly_reject,
        ROUND(AVG(response_time_ms),0) as avg_response_ms
        FROM \`${PROJECT_ID}.${DATASET}.offer_logs\` WHERE timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
      `}).then(r => r[0]),
      // 4. Context logs by type
      bigquery.query({ query: `SELECT type, COUNT(*) as cnt FROM \`${PROJECT_ID}.${DATASET}.context_logs\` GROUP BY type ORDER BY cnt DESC` }).then(r => r[0]),
      // 5. Store ranking (store_masterで正規化)
      bigquery.query({ query: `
        WITH norm AS (
          SELECT o.*, COALESCE(m.store_id, REGEXP_REPLACE(REGEXP_REPLACE(o.store_name, r'\\s+', ''), r'[　]', '')) as sid
          FROM \`${PROJECT_ID}.${DATASET}.offer_logs\` o
          LEFT JOIN \`${PROJECT_ID}.${DATASET}.store_master\` m ON o.store_name = m.canonical_name
          WHERE o.store_name != '' AND LENGTH(o.store_name) > 2
            AND o.timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
            AND NOT REGEXP_CONTAINS(o.store_name, r'^[0-9:iX•\\s]+$')
        )
        SELECT sid as store_name, COUNT(*) as cnt, ROUND(AVG(offer_reward),0) as avg_reward,
          ROUND(AVG(CASE WHEN offer_duration > 0 THEN estimated_hourly_rate END),0) as avg_hourly,
          COUNTIF(gemini_decision='accept') as accepts
        FROM norm GROUP BY sid HAVING cnt >= 2 ORDER BY cnt DESC LIMIT 20
      `}).then(r => r[0]),
      // 6. Hourly breakdown (last 7 days)
      bigquery.query({ query: `
        SELECT hour_of_day, COUNT(*) as cnt, ROUND(AVG(offer_reward),0) as avg_reward, ROUND(AVG(estimated_hourly_rate),0) as avg_hourly,
        COUNTIF(gemini_decision='accept') as accepts
        FROM \`${PROJECT_ID}.${DATASET}.offer_logs\` WHERE timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
        GROUP BY hour_of_day ORDER BY hour_of_day
      `}).then(r => r[0]),
            // 7. オファー vs 実績のズレ (actual_*フィールドから直接計算)
      bigquery.query({ query: `
        SELECT
          COUNT(*) as match_count,
          ROUND(AVG(offer_reward), 0) as avg_offer_reward,
          ROUND(AVG(actual_payout), 0) as avg_actual_reward,
          ROUND(AVG(actual_payout - offer_reward), 0) as avg_reward_gap,
          ROUND(AVG(offer_duration), 0) as avg_offer_dur,
          ROUND(AVG(actual_duration_minutes), 0) as avg_actual_dur,
          ROUND(AVG(actual_duration_minutes - offer_duration), 1) as avg_duration_gap,
          ROUND(AVG(offer_distance), 2) as avg_offer_dist,
          ROUND(AVG(actual_distance_km), 2) as avg_actual_dist,
          ROUND(AVG(actual_distance_km - offer_distance), 2) as avg_distance_gap
        FROM \`${PROJECT_ID}.${DATASET}.offer_logs\`
        WHERE actual_payout IS NOT NULL AND offer_reward > 0 AND offer_duration > 0
      `}).then(r => r[0]),
      // 8. 店舗別待機時間ランキング (充電ON→次のOFFをLEAD()でペアリング)
      bigquery.query({ query: `
        WITH charging_seq AS (
          SELECT PARSE_TIMESTAMP('%Y-%m-%dT%H:%M:%E*SZ', timestamp_utc) as ts, wireless_charging,
            LEAD(PARSE_TIMESTAMP('%Y-%m-%dT%H:%M:%E*SZ', timestamp_utc)) OVER (ORDER BY timestamp_utc) as next_ts,
            LEAD(wireless_charging) OVER (ORDER BY timestamp_utc) as next_charging
          FROM \`${PROJECT_ID}.${DATASET}.charging_logs\`
          WHERE timestamp_utc IS NOT NULL
        ),
        pairs AS (
          SELECT ts as arrive_ts, next_ts as leave_ts,
            TIMESTAMP_DIFF(next_ts, ts, SECOND)/60.0 as wait_min
          FROM charging_seq
          WHERE wireless_charging = true AND next_charging = false
            AND TIMESTAMP_DIFF(next_ts, ts, MINUTE) BETWEEN 1 AND 25
        ),
        with_store AS (
          SELECT p.wait_min, p.arrive_ts,
            REGEXP_REPLACE(REGEXP_REPLACE(TRIM(REGEXP_REPLACE(o.store_name, r"\\s+(McDonald's|Sukiya|Matsuya|Yoshinoya|Burrger King|Burger King|LOTTERIA|ZETTERIA|Gansoramen).*$", '')), r'\\s+', ''), r'[　【】「」()]', '') as store_norm,
            ROW_NUMBER() OVER (PARTITION BY p.arrive_ts ORDER BY ABS(TIMESTAMP_DIFF(o.timestamp, p.arrive_ts, MINUTE))) as rn
          FROM pairs p
          JOIN \`${PROJECT_ID}.${DATASET}.offer_logs\` o
            ON ABS(TIMESTAMP_DIFF(o.timestamp, p.arrive_ts, MINUTE)) < 30
            AND o.store_name != '' AND LENGTH(o.store_name) > 2
            AND REGEXP_CONTAINS(o.store_name, r'[\p{Han}\p{Hiragana}\p{Katakana}]')
        )
        SELECT store_norm as store_name, COUNT(*) as cnt,
          ROUND(AVG(wait_min), 1) as avg_wait_min,
          ROUND(MAX(wait_min), 1) as max_wait_min
        FROM with_store WHERE rn = 1 AND LENGTH(store_norm) >= 3
        GROUP BY store_norm HAVING cnt >= 2
        ORDER BY avg_wait_min DESC LIMIT 15
      `}).then(r => r[0]),
      // 9. Store master (名寄せ一覧)
      bigquery.query({ query: `SELECT store_id, total_cnt FROM \`${PROJECT_ID}.${DATASET}.store_master\` ORDER BY total_cnt DESC LIMIT 50` }).then(r => r[0]),
      // 10. クエスト情報 (有効なもののみ、開始時間順)
      bigquery.query({ query: `
        WITH raw_quests AS (
          -- type=questはそのまま、type=nandemoでJSON内にquest情報があるものはsummaryを抽出
          SELECT
            CASE WHEN type = 'quest' THEN summary
                 WHEN type = 'nandemo' AND REGEXP_CONTAINS(summary, r'"type":\\s*"quest"')
                   THEN REGEXP_EXTRACT(summary, r'"summary":\\s*"([^"]+)"')
                 ELSE NULL END as summary,
            timestamp
          FROM \`${PROJECT_ID}.${DATASET}.context_logs\`
          WHERE (type = 'quest' OR (type = 'nandemo' AND REGEXP_CONTAINS(summary, r'"type":\\s*"quest"')))
            AND timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 14 DAY)
        ),
        valid_quests AS (
          SELECT summary, timestamp,
            CASE
              WHEN REGEXP_CONTAINS(summary, r'(ピーク|クエスト).*\\d{1,2}/\\d{1,2}.*\\d{1,2}:\\d{2}-') THEN CONCAT('peak_', REGEXP_EXTRACT(summary, r'(\\d{1,2}/\\d{1,2}.*?\\d{1,2}:\\d{2}-\\d{1,2}:\\d{2})'))
              WHEN REGEXP_CONTAINS(summary, r'週前半') THEN 'weekly_first'
              WHEN REGEXP_CONTAINS(summary, r'週後半') THEN 'weekly_second'
              WHEN REGEXP_CONTAINS(summary, r'連続') THEN 'consecutive'
              WHEN REGEXP_CONTAINS(summary, r'^雨') THEN 'rain'
              WHEN REGEXP_CONTAINS(summary, r'^乗車ボーナス') THEN 'ride_bonus'
              ELSE NULL
            END as quest_key,
            SAFE_CAST(REGEXP_EXTRACT(summary, r'(\\d{1,2})/\\d{1,2}') AS INT64) * 100 + SAFE_CAST(REGEXP_EXTRACT(summary, r'\\d{1,2}/(\\d{1,2})') AS INT64) as sort_date,
            SAFE_CAST(REGEXP_EXTRACT(summary, r'(\\d{1,2}):\\d{2}-') AS INT64) as sort_hour
          FROM raw_quests
          WHERE summary IS NOT NULL
            AND (REGEXP_CONTAINS(summary, r'^ピーク\\s+\\d') OR REGEXP_CONTAINS(summary, r'^クエスト\\s+\\d{1,2}/') OR REGEXP_CONTAINS(summary, r'^週前半') OR REGEXP_CONTAINS(summary, r'^週後半')
                 OR REGEXP_CONTAINS(summary, r'^雨\\s') OR REGEXP_CONTAINS(summary, r'^乗車ボーナス')
                 OR (REGEXP_CONTAINS(summary, r'^連続') AND timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)))
        ),
        deduped AS (
          SELECT summary, quest_key, sort_date, sort_hour,
            ROW_NUMBER() OVER (PARTITION BY quest_key ORDER BY timestamp DESC) as rn
          FROM valid_quests
          WHERE quest_key IS NOT NULL
        )
        SELECT summary, sort_date, sort_hour FROM deduped WHERE rn = 1
        ORDER BY
          CASE WHEN quest_key LIKE 'weekly%' THEN 0 WHEN quest_key = 'consecutive' THEN 1 ELSE 2 END,
          sort_date ASC, sort_hour ASC
      `}).then(r => r[0])
    ]);
    const offerGap = (offerGapRaw || [])[0] || {};
    res.status(200).json({ tables, coefficients, offerStats: offerStats[0] || {}, contextStats, storeRanking, hourlyStats, offerGap, storeWait: storeWaitRaw || [], storeMaster: storeMasterRaw || [], quests: questsRaw || [] });
  } catch (error) {
    console.error('bqStats error:', error);
    res.status(500).json({ error: error.message });
  }
});

// ============================================================
// ENDPOINT 5: /kittConfig - Save/load KITT settings + memory
// ============================================================
functions.http('kittConfig', async (req, res) => {
  res.set('Access-Control-Allow-Origin', '*');
  res.set('Access-Control-Allow-Headers', 'Content-Type, X-API-Key');
  if (req.method === 'OPTIONS') return res.status(204).send('');

  if (req.method === 'GET') {
    // Load latest config from BQ
    try {
      const [rows] = await bigquery.query({
        query: `SELECT config_json FROM \`${PROJECT_ID}.${DATASET}.kitt_config\` ORDER BY updated_at DESC LIMIT 1`
      });
      if (rows.length > 0) {
        res.status(200).json(JSON.parse(rows[0].config_json));
      } else {
        res.status(200).json({});
      }
    } catch (e) {
      // Table might not exist yet
      res.status(200).json({});
    }
    return;
  }

  if (req.method === 'POST') {
    if (!checkApiKey(req)) return res.status(401).json({ error: 'Unauthorized' });
    try {
      const configData = req.body;
      // Create table if not exists, then upsert
      const tableId = 'kitt_config';
      try {
        await bigquery.dataset(DATASET).table(tableId).get();
      } catch (e) {
        // Table doesn't exist, create it
        await bigquery.dataset(DATASET).createTable(tableId, {
          schema: {
            fields: [
              { name: 'config_json', type: 'STRING' },
              { name: 'updated_at', type: 'TIMESTAMP' }
            ]
          }
        });
      }
      // Delete old and insert new (simple upsert)
      await bigquery.query({ query: `DELETE FROM \`${PROJECT_ID}.${DATASET}.${tableId}\` WHERE TRUE` });
      await bigquery.dataset(DATASET).table(tableId).insert([{
        config_json: JSON.stringify(configData),
        updated_at: BigQuery.timestamp(new Date())
      }]);
      res.status(200).json({ status: 'ok' });
    } catch (e) {
      console.error('kittConfig save error:', e.message);
      res.status(500).json({ error: e.message });
    }
    return;
  }

  res.status(405).json({ error: 'Method not allowed' });
});

// ============================================================
// Helper Functions
// ============================================================

function parseOcrText(text) {
  const result = { storeName: '', reward: 0, distanceKm: 0, durationMin: 0 };

  // Reward: 「合計XX分」行の近くにある報酬を最優先 → fallbackで上から探索
  const rewardLines = text.split(/\\n|\n/);
  const goukeiIdx = rewardLines.findIndex(l => /合計.*分/.test(l));

  // Strategy 1: 合計行の上5行以内で中点パターン(·XXX)を探す = 最も信頼度が高い
  if (goukeiIdx > 0) {
    for (let i = goukeiIdx - 1; i >= Math.max(0, goukeiIdx - 5); i--) {
      const trimmed = rewardLines[i].trim();
      if (/[¥￥·•]\s*\d{1,2}\s*配達/.test(trimmed)) continue;
      // +·156 (追加オファー) も有効
      const m = trimmed.match(/\+?\s*[·•]\s*([0-9,]{3,})/) || trimmed.match(/[¥￥]\s*([0-9,]{3,})/);
      if (m) {
        const val = parseInt(m[1].replace(/,/g, ''));
        if (val >= 100 && val <= 9999) { result.reward = val; break; }
      }
    }
  }

  // Strategy 2: Fallback - 上から探すが中点パターン(·)を優先
  if (!result.reward) {
    for (const rl of rewardLines) {
      const trimmed = rl.trim();
      if (/[¥￥·•]\s*\d{1,2}\s*配達/.test(trimmed)) continue;
      // +·156 (追加オファー) も有効
      const m = trimmed.match(/\+?\s*[·•]\s*([0-9,]{3,})/);
      if (m) {
        const val = parseInt(m[1].replace(/,/g, ''));
        if (val >= 100 && val <= 9999) { result.reward = val; break; }
      }
    }
  }

  // Strategy 3: Last resort - ¥パターン (地図数字の誤検知リスクあり)
  if (!result.reward) {
    for (const rl of rewardLines) {
      const trimmed = rl.trim();
      if (/[¥￥·•]\s*\d{1,2}\s*配達/.test(trimmed)) continue;
      // +·156 (追加オファー) も有効
      const m = trimmed.match(/[¥￥]\s*([0-9,]{3,})/);
      if (m) {
        const val = parseInt(m[1].replace(/,/g, ''));
        if (val >= 100 && val <= 3000) { result.reward = val; break; } // ¥パターンは3000円以下のみ
      }
    }
  }

  // Distance: 「合計XX分（Y.Ykm）」を最優先
  const distMatch = text.match(/合計.*?([0-9]+\.?[0-9]*)\s*km/i) || text.match(/([0-9]+\.?[0-9]*)\s*(?:km|キロ)/i);
  if (distMatch) result.distanceKm = parseFloat(distMatch[1]);

  // Duration: 「合計XX分」を最優先（バッテリー%等の誤検知防止）
  const durMatch = text.match(/合計\s*\+?\s*([0-9]+)\s*分/) || text.match(/合計\s*([0-9]+)\s*時間\s*([0-9]+)\s*分/) || text.match(/約\s*([0-9]+)\s*分/);
  if (durMatch) {
    result.durationMin = durMatch[2] ? parseInt(durMatch[1]) * 60 + parseInt(durMatch[2]) : parseInt(durMatch[1]);
  } else {
    // Fallback: 「XX分」だが合計行の近くにあるものだけ
    const fallback = text.match(/([0-9]+)\s*min/i);
    if (fallback) result.durationMin = parseInt(fallback[1]);
  }

  // Store name: 「合計XX分」行の直後の行が最有力。バリデーション付き。
  const storeSkip = /^[0-9:,.\s¥￥·•+\-=—–×%]+$|^[a-zA-Z]$|^\d{1,2}:\d{2}|^配達|^ピック|^ドロップ|^合計|^距離|^時間|^予想|^到着|^注文|^承諾|^限定|^申込|^Uber|^現金|^クレジット|^稼働|^サイカ|^技術サービス|^\+?[·•]/;
  const storeValid = (s) => s && s.length >= 2 && !storeSkip.test(s) && /[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]/.test(s);
  const lines = text.split(/\\n|\n/).filter(l => l.trim());

  // Strategy 1: 合計行の直後
  for (let i = 0; i < lines.length; i++) {
    if (/合計/.test(lines[i]) && i + 1 < lines.length) {
      const candidate = lines[i + 1].trim();
      if (storeValid(candidate)) { result.storeName = candidate; break; }
      // 次の行もチェック
      if (i + 2 < lines.length) {
        const candidate2 = lines[i + 2].trim();
        if (storeValid(candidate2)) { result.storeName = candidate2; break; }
      }
    }
  }
  // Strategy 2: 「店」「屋」「亭」「堂」等を含む行
  if (!result.storeName) {
    for (const line of lines) {
      const t = line.trim();
      if (storeValid(t) && /[店屋亭堂丸庵房軒家]|マクドナルド|すき家|吉野家|松屋|ガスト|スタバ|ドミノ|モス|ケンタ|CoCo/.test(t)) {
        result.storeName = t; break;
      }
    }
  }
  // Strategy 3: 日本語3文字以上の最初の行
  if (!result.storeName) {
    for (const line of lines) {
      const t = line.trim();
      if (t.length >= 3 && storeValid(t)) { result.storeName = t; break; }
    }
  }

  return result;
}

async function getCoefficients() {
  const now = Date.now();
  if (cache.coefficients.data && now < cache.coefficients.expiry) {
    return cache.coefficients.data;
  }
  try {
    const [rows] = await bigquery.dataset(DATASET).table('dynamic_coefficients').getRows();
    const coeffMap = {};
    for (const row of rows) {
      coeffMap[row.coefficient_name] = row.coefficient_value;
    }
    const result = {
      base_hourly_wage: coeffMap.base_hourly_wage || 1993,
      avg_reward: coeffMap.avg_reward || 689,
      avg_distance: coeffMap.avg_distance || 3.21,
      avg_duration: coeffMap.avg_duration || 21,
      avg_reward_per_km: coeffMap.avg_reward_per_km || 224,
      avg_speed_kmh: coeffMap.avg_speed_kmh || 9.37,
      avg_hourly_wage_lunch: coeffMap.avg_hourly_wage_lunch || 2111,
      avg_hourly_wage_dinner: coeffMap.avg_hourly_wage_dinner || 2186,
      avg_hourly_wage_morning: coeffMap.avg_hourly_wage_morning || 1887,
      avg_hourly_wage_weekend: coeffMap.avg_hourly_wage_weekend || 2143,
      avg_hourly_wage_weekday: coeffMap.avg_hourly_wage_weekday || 2099,
      waiting_expectation_value: coeffMap.waiting_expectation_value || 1000,
      next_offer_interval_sec: coeffMap.next_offer_interval_sec || 300,
      // スコアリング重み (BQで動的調整可能)
      weight_reward_per_km: coeffMap.weight_reward_per_km || 0.20,
      weight_hourly_rate: coeffMap.weight_hourly_rate || 0.30,
      weight_distance: coeffMap.weight_distance || 0.10,
      weight_store_reputation: coeffMap.weight_store_reputation || 0.10,
      weight_market: coeffMap.weight_market || 0.15,
      weight_quest_adjusted: coeffMap.weight_quest_adjusted || 0.05,
      weight_opportunity: coeffMap.weight_opportunity || 0.10,
      // 閾値 (BQで動的調整可能)
      score_threshold: coeffMap.score_threshold || 0.85,
      ...coeffMap
    };
    cache.coefficients = { data: result, expiry: now + CACHE_TTL_COEFFICIENTS };
    return result;
  } catch (e) {
    console.warn('getCoefficients fallback:', e.message);
    return {
      base_hourly_wage: 1993, avg_reward: 689, avg_distance: 3.21,
      avg_duration: 21, avg_reward_per_km: 224, avg_speed_kmh: 9.37,
      avg_hourly_wage_lunch: 2111, avg_hourly_wage_dinner: 2186,
      avg_hourly_wage_morning: 1887, avg_hourly_wage_weekend: 2143,
      avg_hourly_wage_weekday: 2099, waiting_expectation_value: 1000,
      next_offer_interval_sec: 300,
      weight_reward_per_km: 0.20, weight_hourly_rate: 0.30,
      weight_distance: 0.10, weight_store_reputation: 0.10,
      weight_market: 0.15, weight_quest_adjusted: 0.05,
      weight_opportunity: 0.10, score_threshold: 0.85
    };
  }
}

async function getStoreHistory(storeName) {
  if (!storeName) return null;
  const now = Date.now();
  const cached = cache.storeHistory.get(storeName);
  if (cached && now < cached.expiry) return cached.data;
  try {
    const query = `SELECT store_name, COUNT(*) as offer_count, COUNTIF(gemini_decision = 'accept') as accept_count, AVG(offer_reward) as avg_reward, AVG(offer_distance) as avg_distance, AVG(offer_duration) as avg_duration, AVG(CASE WHEN offer_distance > 0 THEN offer_reward / offer_distance END) as avg_reward_per_km, AVG(CASE WHEN offer_duration > 0 THEN (offer_reward / offer_duration) * 60 END) as avg_hourly_rate FROM \`${PROJECT_ID}.${DATASET}.offer_logs\` WHERE store_name = @storeName GROUP BY store_name`;
    const [rows] = await bigquery.query({ query, params: { storeName } });
    const result = rows[0] || null;
    cache.storeHistory.set(storeName, { data: result, expiry: now + CACHE_TTL_STORE });
    // Keep cache size reasonable
    if (cache.storeHistory.size > 100) {
      const firstKey = cache.storeHistory.keys().next().value;
      cache.storeHistory.delete(firstKey);
    }
    return result;
  } catch (e) {
    console.warn('getStoreHistory error:', e.message);
    return null;
  }
}

async function getRecentTrends() {
  const now = Date.now();
  if (cache.recentTrends.data && now < cache.recentTrends.expiry) {
    return cache.recentTrends.data;
  }
  try {
    const query = `SELECT COUNT(*) as total_offers, COUNTIF(gemini_decision = 'accept') as accepts, AVG(offer_reward) as avg_reward, AVG(estimated_hourly_rate) as avg_hourly FROM \`${PROJECT_ID}.${DATASET}.offer_logs\` WHERE timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 2 HOUR)`;
    const [rows] = await bigquery.query({ query });
    const result = rows[0] || null;
    cache.recentTrends = { data: result, expiry: now + CACHE_TTL_TRENDS };
    return result;
  } catch (e) {
    console.warn('getRecentTrends error:', e.message);
    return null;
  }
}

async function getLatestContext(type) {
  try {
    const query = `SELECT summary, structured_data FROM \`${PROJECT_ID}.${DATASET}.context_logs\` WHERE type = @type ORDER BY timestamp DESC LIMIT 1`;
    const [rows] = await bigquery.query({ query, params: { type } });
    return rows[0] || null;
  } catch (e) {
    console.warn('getLatestContext error:', e.message);
    return null;
  }
}

// --- Weather API (Open-Meteo, free, no key) ---
async function getWeather(lat, lng) {
  if (!lat || !lng) return null;
  try {
    const url = `https://api.open-meteo.com/v1/forecast?latitude=${lat}&longitude=${lng}&current=temperature_2m,weather_code,wind_speed_10m,precipitation&timezone=Asia%2FTokyo`;
    const resp = await fetch(url);
    if (!resp.ok) return null;
    const data = await resp.json();
    const cur = data.current;
    if (!cur) return null;
    // WMO weather codes: 0-3 clear/cloudy, 51-67 drizzle/rain, 71-77 snow, 80-82 rain showers, 95-99 thunderstorm
    const code = cur.weather_code || 0;
    let condition = 'clear';
    if (code >= 51 && code <= 67) condition = 'rain';
    else if (code >= 71 && code <= 77) condition = 'snow';
    else if (code >= 80 && code <= 82) condition = 'rain';
    else if (code >= 95) condition = 'storm';
    else if (code >= 3) condition = 'cloudy';
    return {
      condition,
      code,
      temp: cur.temperature_2m,
      wind: cur.wind_speed_10m,
      precipitation: cur.precipitation,
      isRaining: condition === 'rain' || condition === 'storm'
    };
  } catch (e) {
    console.warn('getWeather error:', e.message);
    return null;
  }
}

function calculateScore({ reward, distanceKm, durationMin, coefficients, storeHistory, recentTrends, hourJST, isWeekend, wireless_charging, questInfo, weather }) {
  const c = coefficients;
  const scores = {};
  const rewardPerKm = distanceKm > 0 ? reward / distanceKm : 0;
  scores.reward_per_km = rewardPerKm / (c.avg_reward_per_km || 224);
  const estHourly = durationMin > 0 ? (reward / durationMin) * 60 : 0;
  const timeSlotAvg = getTimeSlotAvg(hourJST, isWeekend, c);
  scores.hourly_rate = timeSlotAvg > 0 ? estHourly / timeSlotAvg : 0;
  scores.distance = c.avg_distance > 0 ? c.avg_distance / Math.max(distanceKm, 0.5) : 1;
  scores.distance = Math.min(scores.distance, 2);
  if (storeHistory && storeHistory.offer_count >= 3) {
    const storeAcceptRate = storeHistory.accept_count / storeHistory.offer_count;
    let storeScore = 0.8 + (storeAcceptRate * 0.4);
    // 店舗の実績時給が低い場合はペナルティ
    if (storeHistory.avg_hourly_rate && storeHistory.avg_hourly_rate < (c.base_hourly_wage || 1993) * 0.7) {
      storeScore *= 0.85;
    }
    // 店舗の平均距離が全体平均の1.5倍超ならペナルティ
    if (storeHistory.avg_distance && storeHistory.avg_distance > (c.avg_distance || 3.21) * 1.5) {
      storeScore *= 0.9;
    }
    scores.store_reputation = storeScore;
  } else {
    scores.store_reputation = 1.0;
  }
  if (recentTrends && recentTrends.total_offers > 0) {
    const marketAvgReward = recentTrends.avg_reward || c.avg_reward;
    scores.market = reward / marketAvgReward;
  } else {
    scores.market = reward / (c.avg_reward || 689);
  }
  let questBonus = 0;
  if (questInfo && questInfo.summary) {
    // 金額パターン: "4,000円" or "¥1,300" を探す (日付の3/28等を拾わない)
    const questMatch = questInfo.summary.match(/([0-9,]{3,})円/) || questInfo.summary.match(/¥([0-9,]{3,})/);
    if (questMatch) {
      questBonus = parseInt(questMatch[1].replace(/,/g, ''));
      if (reward > 0) { scores.quest_adjusted = (reward + questBonus) / reward; }
    }
  }
  if (!scores.quest_adjusted) scores.quest_adjusted = 1.0;
  const waitIntervalSec = c.next_offer_interval_sec || 300;
  const waitCostPerMin = (c.base_hourly_wage || 1993) / 60;
  const estimatedWaitMin = waitIntervalSec / 60;
  if (durationMin > 0) {
    const opportunityCostRatio = reward / ((durationMin + estimatedWaitMin) * waitCostPerMin);
    scores.opportunity = Math.min(opportunityCostRatio, 2);
  } else {
    scores.opportunity = 1.0;
  }
  const weights = {
    reward_per_km: c.weight_reward_per_km || 0.20,
    hourly_rate: c.weight_hourly_rate || 0.30,
    distance: c.weight_distance || 0.10,
    store_reputation: c.weight_store_reputation || 0.10,
    market: c.weight_market || 0.15,
    quest_adjusted: c.weight_quest_adjusted || 0.05,
    opportunity: c.weight_opportunity || 0.10
  };
  let total = 0;
  for (const [key, weight] of Object.entries(weights)) {
    total += (scores[key] != null ? scores[key] : 1.0) * weight;
  }
  // Weather adjustment: 係数テーブルから読み込み
  let weatherNote = null;
  if (weather) {
    const precip = weather.precipitation || 0;
    const isRaining = weather.isRaining || precip > 0;
    const rainLight = 1 + (c.rain_boost_light || 0.10);
    const rainHeavy = 1 + (c.rain_boost_heavy || 0.15);
    const rainFarPenalty = 1 + (c.rain_penalty_far || -0.05);
    const tempBoost = 1 + (c.temp_extreme_boost || 0.05);
    if (isRaining) {
      if (precip >= 5) {
        if (distanceKm <= (c.avg_distance || 3.21) * 1.2) {
          total *= rainHeavy; weatherNote = 'heavy_rain_bonus';
        } else {
          total *= rainFarPenalty; weatherNote = 'heavy_rain_far_penalty';
        }
      } else if (precip >= 1 || isRaining) {
        total *= rainLight; weatherNote = 'rain_bonus';
      }
    }
    const temp = weather.temperature || 0;
    if (temp >= 33) { total *= tempBoost; weatherNote = (weatherNote || '') + '_hot'; }
    else if (temp <= 5) { total *= tempBoost; weatherNote = (weatherNote || '') + '_cold'; }
  }
  const threshold = c.score_threshold || 0.85;
  return { total, threshold, scores, weights, questBonus, timeSlotAvg, weatherNote };
}

function getTimeSlotAvg(hourJST, isWeekend, c) {
  if (isWeekend) return c.avg_hourly_wage_weekend || 2143;
  if (hourJST >= 11 && hourJST < 14) return c.avg_hourly_wage_lunch || 2111;
  if (hourJST >= 17 && hourJST < 21) return c.avg_hourly_wage_dinner || 2186;
  if (hourJST >= 7 && hourJST < 11) return c.avg_hourly_wage_morning || 1887;
  if (hourJST >= 22 || hourJST < 7) return c.avg_hourly_wage_late_night || 1887;
  return c.avg_hourly_wage_weekday || 2099;
}

function buildDecisionReason(decision, score, reward, distanceKm, durationMin, estHourlyRate, coefficients) {
  const parts = [];
  const rewardPerKm = distanceKm > 0 ? Math.round(reward / distanceKm) : 0;
  if (decision === 'accept') {
    if (score.scores.hourly_rate > 1.2) parts.push('高時給');
    if (score.scores.reward_per_km > 1.2) parts.push('高km単価');
    if (score.scores.store_reputation > 1.1) parts.push('優良店');
    if (score.scores.distance > 1.3) parts.push('近場');
    if (score.questBonus > 0) parts.push(`Quest+${score.questBonus}`);
    if (parts.length === 0) parts.push('基準以上');
  } else {
    if (score.scores.hourly_rate < 0.8) parts.push('低時給');
    if (score.scores.reward_per_km < 0.7) parts.push('低km単価');
    if (score.scores.distance < 0.7) parts.push('遠距離');
    if (score.scores.store_reputation < 0.85) parts.push('地雷店');
    if (parts.length === 0) parts.push('基準以下');
  }
  const waitMin = (coefficients.next_offer_interval_sec || 300) / 60;
  const effectiveRate = durationMin > 0 ? Math.round((reward / (durationMin + waitMin)) * 60) : 0;
  return `${decision === 'accept' ? '\u53D7\u3051\u308B' : '\u30D1\u30B9'} \xA5${Math.round(estHourlyRate).toLocaleString()}/h${effectiveRate > 0 ? '(AI\xA5' + effectiveRate.toLocaleString() + '/h)' : ''}`;
}

// [NEW] KITT向けTTSテキスト生成 - 1-2文、5秒以内で読める長さ
function buildTtsText(decision, confidence, score, reward, distanceKm, durationMin, estHourlyRate, storeName, coefficients) {
  const hourlyRound = Math.round(estHourlyRate);
  const rewardPerKm = distanceKm > 0 ? Math.round(reward / distanceKm) : 0;
  const timeSlotAvg = score.timeSlotAvg || coefficients.base_hourly_wage || 1993;
  const hourlyVsAvg = timeSlotAvg > 0 ? Math.round((estHourlyRate / timeSlotAvg) * 100) : 0;

  if (decision === 'accept') {
    // 受けるべき理由を端的に
    const highlights = [];
    if (score.scores.hourly_rate > 1.3) highlights.push('高時給');
    else if (score.scores.hourly_rate > 1.1) highlights.push('時給良好');
    if (score.scores.reward_per_km > 1.3) highlights.push('近くて高単価');
    if (score.scores.store_reputation > 1.1) highlights.push('優良店');
    if (score.questBonus > 0) highlights.push(`クエスト加算${score.questBonus}円`);
    if (score.weatherNote?.includes('rain_bonus')) highlights.push('雨で需要増、狙い目');
    if (score.weatherNote?.includes('heavy_rain_bonus')) highlights.push('強雨ブースト');
    if (score.weatherNote?.includes('hot')) highlights.push('猛暑ブースト');
    if (score.weatherNote?.includes('cold')) highlights.push('寒さブースト');

    const highlightText = highlights.length > 0 ? highlights.join('、') : '総合スコア良好';

    if (confidence === 'high') {
      return `受けろ。${reward}円、${distanceKm}キロ。時給${hourlyRound}円、平均の${hourlyVsAvg}%。${highlightText}。`;
    } else {
      return `受けていい。${reward}円、${distanceKm}キロ。時給${hourlyRound}円。${highlightText}。`;
    }
  } else {
    // スキップすべき理由を端的に
    const problems = [];
    if (score.scores.hourly_rate < 0.7) problems.push('時給が低すぎる');
    else if (score.scores.hourly_rate < 0.9) problems.push('時給が平均以下');
    if (score.scores.reward_per_km < 0.6) problems.push('距離の割に安い');
    if (score.scores.distance < 0.7) problems.push('遠すぎる');
    if (score.weatherNote === 'rain_penalty') problems.push('雨で遠い、危険');

    const problemText = problems.length > 0 ? problems.join('、') : '基準に届かない';

    if (confidence === 'low') {
      // score.total が threshold に近い = 微妙なライン
      return `微妙。${reward}円、${distanceKm}キロ、時給${hourlyRound}円。${problemText}。待った方がいい。`;
    } else {
      return `スキップ。${reward}円、${distanceKm}キロ、時給${hourlyRound}円。${problemText}。`;
    }
  }
}

async function insertOfferLog(data) {
  const row = {
    log_id: data.logId,
    timestamp: BigQuery.timestamp(new Date()),
    lat: parseFloat(data.lat) || 0,
    lng: parseFloat(data.lng) || 0,
    address: data.address || '',
    wireless_charging: data.wireless_charging === true || data.wireless_charging === 'true',
    gemini_decision: data.decision,
    estimated_hourly_rate: data.estHourlyRate || 0,
    decision_reason: data.reason || '',
    confidence: data.confidence || 'medium',
    // [FIX #2] coefficients を正しく参照
    base_hourly_wage: data.coefficients?.base_hourly_wage || 0,
    offer_reward: data.reward || 0,
    offer_distance: data.distanceKm || 0,
    offer_duration: data.durationMin || 0,
    weather_condition: data.weather || null, traffic_status: null, quest_progress: null,
    actual_accepted: null, actual_payout: null, actual_duration_minutes: null,
    actual_distance_km: null, response_time_ms: data.responseTimeMs || 0,
    raw_gemini_response: data.rawGeminiResponse || null,
    raw_ocr_text: data.rawOcrText || null,
    weather_info: null, store_name: data.storeName || '',
    day_of_week: ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'][new Date().getUTCDay()],
    hour_of_day: (new Date().getUTCHours() + 9) % 24,
    decision_reason_detail: data.scoreDetail || null,
    image_url: data.imageUrl || null
  };
  await bigquery.dataset(DATASET).table('offer_logs').insert([row]);
}

async function analyzeOfferImage(imageBase64, coefficients) {
  if (!GEMINI_API_KEY) return null;
  try {
    const prompt = 'UberEats offer screenshot. Extract JSON: store_name, reward, distance_km, duration_min, pickup_address, dropoff_address';
    const response = await fetch(
      `https://generativelanguage.googleapis.com/v1beta/models/${GEMINI_MODEL}:generateContent?key=${GEMINI_API_KEY}`,
      { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ contents: [{ parts: [{ text: prompt }, { inline_data: { mime_type: 'image/png', data: imageBase64 }}]}], generationConfig: { temperature: 0.1, maxOutputTokens: 500 }})
      });
    const result = await response.json();
    const text = result.candidates?.[0]?.content?.parts?.[0]?.text || '';
    const jsonMatch = text.match(/\{[\s\S]*\}/);
    if (jsonMatch) return JSON.parse(jsonMatch[0]);
    return null;
  } catch (e) { console.error('analyzeOfferImage error:', e.message); return null; }
}

async function analyzeNandemoImage(imageBase64, ocrText) {
  if (!GEMINI_API_KEY) return { type: 'nandemo', summary: ocrText || 'image received', structured_data: {} };
  try {
    const prompt = `UberEatsの配達に関するスクリーンショットを分析してJSON形式で返してください。
summaryには必ず画面に表示されている具体的な数字・日時・金額を含めてください。

配達完了画面の場合(summaryは「店舗名 ドロップ先町名 HH:MM ¥金額 時間 距離 件数」の順。HH:MMは配達完了時刻(「Delivery・2026年3月29日・午後2時29分」の「午後2時29分」→14:29)を24時間形式で。ステータスバーの時刻ではない。町名は市区より後だけ。件数=画面に表示されているポイント数。「2ポイント」なら「2件」):
{"type":"result","summary":"大衆焼肉港のたまや 警固 18:51 ¥576 31分 3.64km 2件","structured_data":{"store_name":"大衆焼肉 港のたまや","delivery_fee":"576","distance":"3.64 km","duration":"31分49秒","dropoff_address":"警固1丁目","delivery_date":"2026年3月24日","delivery_time":"午後6時51分"},"ai_note":"詳細メモ"}

ピーク(特定の時間帯のクエスト。条件画面・進捗画面どちらもこの形式。件数と金額は全段の合計を書く):
{"type":"quest","summary":"ピーク 3/28(土) 10:30-15:00 12件 4,000円","structured_data":{"quest_type":"ピーク","quest_period":"3月28日(土) 10:30-15:00","quest_total_trips":12,"quest_total_reward":4000,"quest_progress":"0/12"},"ai_note":"詳細メモ"}

連続稼働クエスト(プロモーション。件数と金額は全段の合計を書く):
{"type":"quest","summary":"連続 4日間 40件 5,000円 本日あと10件","structured_data":{"quest_type":"連続","quest_days":4,"quest_total_trips":40,"quest_total_reward":5000,"quest_remaining_today":10},"ai_note":"詳細メモ"}

雨クエスト(雨の日に発生する特別クエスト。通常ピークと時間帯が違う(17:30-22:00等、通常は10:30-15:00/17:00-21:30)ので判別できる。1回の乗車ごとにボーナス。全12回で3回目以降は同額。summaryは必ず「雨」で始める):
{"type":"quest","summary":"雨 3/30(月) 17:30-22:00 12件 3,000円","structured_data":{"quest_type":"雨","quest_period":"3月30日(月) 17:30-22:00","quest_total_trips":12,"quest_total_reward":3000,"bonus_per_trip":250},"ai_note":"雨クエスト"}
※雨クエストの判別ポイント: (1)通常ピークと時間帯が違う(17:30-22:00等。通常は10:30-15:00/17:00-21:30) (2)1回ごとの金額が個別表示されている (3)「1回の乗車ごとに○円」のボーナス表記がある。これらに該当したら「雨」で始めること。

週前半/週後半クエスト(跨ぎクエスト。月〜木頃なら「週前半」、木〜月頃なら「週後半」。件数と金額は全段の合計を書く):
{"type":"quest","summary":"週前半 3/24(月)-3/27(木) 15/120件 11,780円","structured_data":{"quest_type":"週前半","quest_period":"3/24-3/27","quest_progress":"15/120","quest_total_reward":11780},"ai_note":"詳細メモ"}
{"type":"quest","summary":"週後半 3/27(木)-3/30(日) 15/120件 11,780円","structured_data":{"quest_type":"週後半","quest_period":"3/27-3/30","quest_progress":"15/120","quest_total_reward":11780},"ai_note":"詳細メモ"}

クエスト達成・クエストリザルト・売り上げ状況画面(「○回乗車クエスト」「○件達成」「クエストボーナス」等が見える画面。typeは必ず「quest_result」):
{"type":"quest_result","summary":"クエスト達成 ¥700 3件達成 19:49","structured_data":{"reward":700,"trips_completed":3,"completion_time":"19:49"},"ai_note":"詳細メモ"}
{"type":"quest_result","summary":"クエスト達成 ¥4,000 4件達成","structured_data":{"reward":4000,"trips_completed":4},"ai_note":"ピーク3回乗車クエスト4件全達成"}

注文詳細の場合(summaryは「店舗名 ドロップ先町名 HH:MM ¥金額 時間 距離 件数」の順。HH:MMは配達完了時刻を24時間形式で):
{"type":"order_detail","summary":"鮨よし田天神 天神 18:37 ¥462 15分 3.07km 1件","structured_data":{"store_name":"鮨 よし田 天神","delivery_fee":"462","distance":"3.07 km","duration":"15分57秒","dropoff_area":"天神"},"ai_note":"詳細メモ"}

受諾した案件(稼働ガイド、配達中画面、ピックアップ先や配達先が表示されている画面。住所の市と区は省略して町名だけ):
{"type":"accepted","summary":"ガスト天神サザン通り店 天神 1件","structured_data":{"store_name":"ガスト 天神サザン通り店","dropoff_area":"天神","delivery_count":1},"ai_note":"詳細メモ"}
複数件の配達(ダブル)の場合:
{"type":"accepted","summary":"マクドナルド赤坂店 赤坂/住吉 2件","structured_data":{"store_name":"マクドナルド赤坂店","dropoff_area":"赤坂/住吉","delivery_count":2},"ai_note":"詳細メモ"}

その他:
{"type":"nandemo","summary":"画面の内容を具体的に1行で","structured_data":{},"ai_note":"詳細メモ"}

重要: summaryは具体的な数字を含む短い1行(40文字以内)。structured_dataは5キー以内。ai_noteは10文字以内。JSONのみ、余計な文章は一切不要。`;
    const mimeType = imageBase64.startsWith('/9j/') ? 'image/jpeg' : 'image/png';
    const response = await fetch(
      `https://generativelanguage.googleapis.com/v1beta/models/${GEMINI_MODEL}:generateContent?key=${GEMINI_API_KEY}`,
      { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ contents: [{ parts: [{ text: prompt }, { inline_data: { mime_type: mimeType, data: imageBase64 }}]}], generationConfig: { temperature: 0.1, maxOutputTokens: 1000, responseMimeType: 'application/json', thinkingConfig: { thinkingBudget: 0 } }})
      });
    const result = await response.json();
    console.log('Gemini nandemo response:', JSON.stringify(result).substring(0, 500));
    if (result.error) {
      console.error('Gemini API error:', result.error.message);
      return { type: 'nandemo', summary: 'Gemini error: ' + result.error.message, structured_data: {} };
    }
    let text = result.candidates?.[0]?.content?.parts?.[0]?.text || '';
    text = text.replace(/```json\s*/g, '').replace(/```\s*/g, '').trim();
    // Try parsing as-is first (handles both {} and [])
    try {
      const parsed = JSON.parse(text);
      return Array.isArray(parsed) ? parsed[0] : parsed;
    } catch(e1) {}
    // Try extracting JSON object
    const jsonMatch = text.match(/\{[\s\S]*\}/);
    if (jsonMatch) {
      try { return JSON.parse(jsonMatch[0]); } catch(pe) {
        const fixed = jsonMatch[0].replace(/,\s*([}\]])/g, '$1');
        try { return JSON.parse(fixed); } catch(pe2) {}
      }
    }
    // Fallback: extract type and summary from broken JSON via regex
    const typeMatch = text.match(/"type"\s*:\s*"([^"]+)"/);
    const summaryMatch = text.match(/"summary"\s*:\s*"([^"]+)"/);
    return {
      type: typeMatch ? typeMatch[1] : 'nandemo',
      summary: summaryMatch ? summaryMatch[1] : text.substring(0, 150),
      structured_data: {}
    };
  } catch (e) {
    console.error('analyzeNandemoImage error:', e.message);
    return { type: 'nandemo', summary: 'Error: ' + e.message, structured_data: {} };
  }
}

async function analyzeNandemoText(text) {
  const lowerText = text.toLowerCase();
  let type = 'nandemo';
  if (lowerText.includes('クエスト') || lowerText.includes('quest')) type = 'quest';
  else if (lowerText.includes('売上') || lowerText.includes('result')) type = 'result';
  else if (lowerText.includes('予定') || lowerText.includes('schedule')) type = 'schedule';
  return { type, summary: text.substring(0, 100), structured_data: { raw_text: text } };
}

async function updateCoefficients(updates) {
  if (!updates || Object.keys(updates).length === 0) return;
  const rows = Object.entries(updates).map(([name, value]) => ({
    coefficient_name: name, coefficient_value: parseFloat(value),
    last_updated: BigQuery.timestamp(new Date()), description: 'Auto-updated by nandemoBox'
  }));
  for (const row of rows) {
    const query = `MERGE \`${PROJECT_ID}.${DATASET}.dynamic_coefficients\` T USING (SELECT @name AS coefficient_name, @value AS coefficient_value, CURRENT_TIMESTAMP() AS last_updated, @desc AS description) S ON T.coefficient_name = S.coefficient_name WHEN MATCHED THEN UPDATE SET coefficient_value = S.coefficient_value, last_updated = S.last_updated, description = S.description WHEN NOT MATCHED THEN INSERT (coefficient_name, coefficient_value, last_updated, description) VALUES (S.coefficient_name, S.coefficient_value, S.last_updated, S.description)`;
    await bigquery.query({ query, params: { name: row.coefficient_name, value: row.coefficient_value, desc: row.description } });
  }
}

// --- Auto-sync: delivery result → delivery_history + offer_logs.actual_accepted ---
async function syncDeliveryResult(logId, data) {
  const result = { delivery_inserted: false, offer_matched: false };
  try {
    // Extract fields from structured_data (Gemini output varies)
    const reward = parseFloat(String(data.delivery_fee || data.earnings || data.fare || data.price || '0').replace(/[^0-9.]/g, '')) || 0;
    const distanceStr = String(data.distance || '0');
    const distance = parseFloat(distanceStr.replace(/[^0-9.]/g, '')) || 0;
    const durationStr = String(data.duration || data.pickup_time || data.estimated_time || '0');
    const durMatch = durationStr.match(/(\d+)\s*分/);
    const duration = durMatch ? parseInt(durMatch[1]) : 0;
    const storeName = data.store_name || data.pickup_location || data.pickup_address || '';
    const dropoff = data.dropoff_address || data.dropoff_location || '';
    const hourlyWage = duration > 0 ? Math.round((reward / duration) * 60) : 0;

    // Parse delivery date/time from structured_data
    const dateStr = data.delivery_date || data.date || data.delivery_datetime || '';
    const timeStr = data.delivery_time || data.time || '';
    let deliveryTimestamp = new Date();
    const yearMatch = dateStr.match(/(\d{4})年(\d{1,2})月(\d{1,2})日/);
    if (yearMatch) {
      const [, y, m, d2] = yearMatch;
      let hour = 12, min = 0;
      const fullTimeStr = dateStr + ' ' + timeStr;
      const timeMatch = fullTimeStr.match(/午(前|後)\s*(\d{1,2})時(\d{1,2})分/);
      if (timeMatch) {
        hour = parseInt(timeMatch[2]);
        min = parseInt(timeMatch[3]);
        if (timeMatch[1] === '後' && hour < 12) hour += 12;
        if (timeMatch[1] === '前' && hour === 12) hour = 0;
      }
      deliveryTimestamp = new Date(Date.UTC(parseInt(y), parseInt(m) - 1, parseInt(d2), hour - 9, min));
    }

    const dayOfWeek = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'][deliveryTimestamp.getUTCDay()];
    const hourJST = (deliveryTimestamp.getUTCHours() + 9) % 24;

    // 1. Insert into delivery_history
    if (reward > 0 || storeName) {
      await bigquery.dataset(DATASET).table('delivery_history').insert([{
        delivery_id: logId,
        timestamp: BigQuery.timestamp(deliveryTimestamp),
        area: dropoff,
        lat: 0, lng: 0,
        reward, distance, duration, hourly_wage: hourlyWage,
        store_name: storeName,
        drop_off_address: dropoff,
        day_of_week: dayOfWeek,
        hour_of_day: hourJST
      }]);
      result.delivery_inserted = true;
    }

    // 2. Match with offer_logs: 正規化店名 + 時間近傍 + 報酬近傍
    {
      // 店名の正規化キー(スペース除去、英語ブランド除去)
      const storeNorm = storeName.replace(/\s+(McDonald's|Sukiya|Matsuya|Yoshinoya|Burger King|Burrger King|LOTTERIA|ZETTERIA|Gansoramen).*$/i, '').replace(/[\s　【】「」()（）]+/g, '');
      const storeKey = storeNorm.substring(0, 8);
      const matchQuery = `
        UPDATE \`${PROJECT_ID}.${DATASET}.offer_logs\`
        SET actual_accepted = true,
            actual_payout = @reward,
            actual_duration_minutes = @duration,
            actual_distance_km = @distance
        WHERE log_id = (
          SELECT log_id FROM \`${PROJECT_ID}.${DATASET}.offer_logs\`
          WHERE actual_accepted IS NULL AND store_name != '' AND offer_reward > 0
            AND ABS(TIMESTAMP_DIFF(timestamp, @deliveryTs, HOUR)) < 6
            AND (
              REGEXP_REPLACE(REGEXP_REPLACE(store_name, r'\\s+', ''), r'[　]', '') LIKE CONCAT('%', @storeKey, '%')
              OR (offer_reward BETWEEN @reward * 0.7 AND @reward * 1.3 AND ABS(TIMESTAMP_DIFF(timestamp, @deliveryTs, MINUTE)) < 90)
            )
          ORDER BY
            CASE WHEN REGEXP_REPLACE(store_name, r'\\s+', '') LIKE CONCAT('%', @storeKey, '%') THEN 0 ELSE 1 END,
            ABS(TIMESTAMP_DIFF(timestamp, @deliveryTs, SECOND))
          LIMIT 1
        )
      `;
      try {
        await bigquery.query({
          query: matchQuery,
          params: {
            reward, duration: duration * 1.0, distance,
            storeKey, deliveryTs: BigQuery.timestamp(deliveryTimestamp)
          }
        });
        result.offer_matched = true;
      } catch(matchErr) {
        console.warn('offer match error:', matchErr.message);
      }
    }
    // 3. Auto-recalculate coefficients from accumulated data
    await recalculateCoefficients();
    result.coefficients_updated = true;
  } catch (e) {
    console.warn('syncDeliveryResult error:', e.message);
    result.error = e.message;
  }
  return result;
}

// ============================================================
// PDCA Engine: 係数再計算 + 重み自動最適化
// ============================================================

// 係数再計算: 実績データ(actual_*)優先、なければ推定値(offer_*)にフォールバック
async function recalculateCoefficients() {
  try {
    const query = `
      WITH stats AS (
        SELECT
          ROUND(AVG(COALESCE(actual_payout, offer_reward)), 2) as avg_reward,
          ROUND(AVG(COALESCE(actual_distance_km, offer_distance)), 2) as avg_distance,
          ROUND(AVG(COALESCE(actual_duration_minutes, offer_duration)), 2) as avg_duration,
          ROUND(AVG(CASE WHEN COALESCE(actual_distance_km, offer_distance) > 0
            THEN COALESCE(actual_payout, offer_reward) / COALESCE(actual_distance_km, offer_distance) END), 2) as avg_reward_per_km,
          ROUND(AVG(CASE WHEN COALESCE(actual_duration_minutes, offer_duration) > 0
            THEN (COALESCE(actual_payout, offer_reward) / COALESCE(actual_duration_minutes, offer_duration)) * 60 END), 2) as base_hourly_wage,
          ROUND(AVG(CASE WHEN COALESCE(actual_duration_minutes, offer_duration) > 0 AND COALESCE(actual_distance_km, offer_distance) > 0
            THEN (COALESCE(actual_distance_km, offer_distance) / COALESCE(actual_duration_minutes, offer_duration)) * 60 END), 2) as avg_speed_kmh,
          ROUND(AVG(CASE WHEN hour_of_day >= 11 AND hour_of_day < 14 AND COALESCE(actual_duration_minutes, offer_duration) > 0
            THEN (COALESCE(actual_payout, offer_reward) / COALESCE(actual_duration_minutes, offer_duration)) * 60 END), 2) as avg_hourly_wage_lunch,
          ROUND(AVG(CASE WHEN hour_of_day >= 17 AND hour_of_day < 21 AND COALESCE(actual_duration_minutes, offer_duration) > 0
            THEN (COALESCE(actual_payout, offer_reward) / COALESCE(actual_duration_minutes, offer_duration)) * 60 END), 2) as avg_hourly_wage_dinner,
          ROUND(AVG(CASE WHEN (hour_of_day >= 22 OR hour_of_day < 7) AND COALESCE(actual_duration_minutes, offer_duration) > 0
            THEN (COALESCE(actual_payout, offer_reward) / COALESCE(actual_duration_minutes, offer_duration)) * 60 END), 2) as avg_hourly_wage_late_night,
          ROUND(AVG(CASE WHEN hour_of_day >= 7 AND hour_of_day < 11 AND COALESCE(actual_duration_minutes, offer_duration) > 0
            THEN (COALESCE(actual_payout, offer_reward) / COALESCE(actual_duration_minutes, offer_duration)) * 60 END), 2) as avg_hourly_wage_morning,
          ROUND(AVG(CASE WHEN day_of_week IN ('Sat','Sun') AND COALESCE(actual_duration_minutes, offer_duration) > 0
            THEN (COALESCE(actual_payout, offer_reward) / COALESCE(actual_duration_minutes, offer_duration)) * 60 END), 2) as avg_hourly_wage_weekend,
          ROUND(AVG(CASE WHEN day_of_week NOT IN ('Sat','Sun') AND COALESCE(actual_duration_minutes, offer_duration) > 0
            THEN (COALESCE(actual_payout, offer_reward) / COALESCE(actual_duration_minutes, offer_duration)) * 60 END), 2) as avg_hourly_wage_weekday,
          COUNT(*) as total_offers,
          COUNTIF(actual_payout IS NOT NULL) as actual_data_count
        FROM \`${PROJECT_ID}.${DATASET}.offer_logs_clean\`
        WHERE offer_reward > 0 AND offer_distance > 0 AND offer_duration > 0
          AND timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY)
      )
      SELECT * FROM stats
    `;
    const [rows] = await bigquery.query({ query });
    if (!rows || !rows[0] || !rows[0].base_hourly_wage) return;
    const s = rows[0];
    const updates = {};
    for (const [k, v] of Object.entries(s)) { if (v !== null && v !== undefined) updates[k] = v; }
    updates.last_recalculated = Date.now();
    await updateCoefficients(updates);
    cache.coefficients = { data: null, expiry: 0 };
    console.log('Coefficients recalculated:', Object.keys(updates).length, 'values. Actual data:', s.actual_data_count, '/', s.total_offers);
  } catch (e) {
    console.warn('recalculateCoefficients error:', e.message);
  }
}

// 重み自動最適化: 実績データから最適な重み配分を探索
async function optimizeWeights() {
  try {
    // Step 1: 実績付きオファーを取得（actual_payoutがある＝リザルトが送られた案件）
    const [offers] = await bigquery.query({ query: `
      SELECT offer_reward, offer_distance, offer_duration, estimated_hourly_rate,
        actual_payout, actual_duration_minutes, actual_distance_km,
        gemini_decision, hour_of_day, day_of_week, weather_condition,
        SAFE_CAST(JSON_VALUE(decision_reason_detail, '$.scores.reward_per_km') AS FLOAT64) as s_rpk,
        SAFE_CAST(JSON_VALUE(decision_reason_detail, '$.scores.hourly_rate') AS FLOAT64) as s_hr,
        SAFE_CAST(JSON_VALUE(decision_reason_detail, '$.scores.distance') AS FLOAT64) as s_dist,
        SAFE_CAST(JSON_VALUE(decision_reason_detail, '$.scores.store_reputation') AS FLOAT64) as s_store,
        SAFE_CAST(JSON_VALUE(decision_reason_detail, '$.scores.market') AS FLOAT64) as s_market,
        SAFE_CAST(JSON_VALUE(decision_reason_detail, '$.scores.quest_adjusted') AS FLOAT64) as s_quest,
        SAFE_CAST(JSON_VALUE(decision_reason_detail, '$.scores.opportunity') AS FLOAT64) as s_opp,
        CASE WHEN actual_duration_minutes > 0 THEN (actual_payout / actual_duration_minutes) * 60 ELSE NULL END as actual_hourly
      FROM \`${PROJECT_ID}.${DATASET}.offer_logs\`
      WHERE offer_reward > 0 AND offer_duration >= 5
        AND decision_reason_detail IS NOT NULL
        AND timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY)
      ORDER BY timestamp DESC LIMIT 500
    `});

    if (offers.length < 20) {
      console.log('optimizeWeights: insufficient data (' + offers.length + ' offers). Need 20+.');
      return { optimized: false, reason: 'insufficient_data', count: offers.length };
    }

    // Step 2: 実績時給がある案件で、各サブスコアとの相関を計算
    const withActual = offers.filter(o => o.actual_hourly > 0 && o.s_hr !== null);
    const scoreKeys = ['s_rpk', 's_hr', 's_dist', 's_store', 's_market', 's_quest', 's_opp'];
    const weightKeys = ['weight_reward_per_km', 'weight_hourly_rate', 'weight_distance', 'weight_store_reputation', 'weight_market', 'weight_quest_adjusted', 'weight_opportunity'];

    if (withActual.length < 10) {
      console.log('optimizeWeights: insufficient actual data (' + withActual.length + '). Need 10+.');
      return { optimized: false, reason: 'insufficient_actual', count: withActual.length };
    }

    // Step 3: 各サブスコアと実績時給の相関を計算
    const correlations = {};
    for (const key of scoreKeys) {
      const pairs = withActual.filter(o => o[key] !== null).map(o => [o[key], o.actual_hourly]);
      if (pairs.length < 5) { correlations[key] = 0; continue; }
      const n = pairs.length;
      const sumX = pairs.reduce((a, p) => a + p[0], 0);
      const sumY = pairs.reduce((a, p) => a + p[1], 0);
      const sumXY = pairs.reduce((a, p) => a + p[0] * p[1], 0);
      const sumX2 = pairs.reduce((a, p) => a + p[0] * p[0], 0);
      const sumY2 = pairs.reduce((a, p) => a + p[1] * p[1], 0);
      const denom = Math.sqrt((n * sumX2 - sumX * sumX) * (n * sumY2 - sumY * sumY));
      correlations[key] = denom > 0 ? (n * sumXY - sumX * sumY) / denom : 0;
    }

    // Step 4: 相関の強さに基づいて重みを再配分（正の相関が強い項目に重みを寄せる）
    const absCorr = scoreKeys.map(k => Math.max(0, correlations[k])); // 負の相関は0にクリップ
    const corrSum = absCorr.reduce((a, b) => a + b, 0);
    if (corrSum <= 0) {
      console.log('optimizeWeights: no positive correlations found');
      return { optimized: false, reason: 'no_positive_correlation' };
    }

    // 現在の重みを取得
    const currentCoeffs = await getCoefficients();
    const currentWeights = weightKeys.map(k => currentCoeffs[k] || 0);

    // 新しい重み = 相関ベース70% + 現在の重み30% (急激な変化を防ぐ)
    const newWeights = {};
    const LEARNING_RATE = 0.3; // 30%ずつ更新（保守的）
    for (let i = 0; i < weightKeys.length; i++) {
      const corrWeight = absCorr[i] / corrSum; // 相関ベースの重み（合計1.0）
      const current = currentWeights[i];
      const updated = current * (1 - LEARNING_RATE) + corrWeight * LEARNING_RATE;
      newWeights[weightKeys[i]] = Math.round(updated * 1000) / 1000; // 小数3桁
    }

    // 合計1.0に正規化
    const weightSum = Object.values(newWeights).reduce((a, b) => a + b, 0);
    for (const k of weightKeys) newWeights[k] = Math.round((newWeights[k] / weightSum) * 1000) / 1000;

    // Step 5: 閾値の最適化（実績時給が平均以上になるスコアの境界値を探す）
    const avgActualHourly = withActual.reduce((a, o) => a + o.actual_hourly, 0) / withActual.length;
    // 各オファーのスコアを新しい重みで再計算
    const scored = withActual.map(o => {
      const scores = [o.s_rpk, o.s_hr, o.s_dist, o.s_store, o.s_market, o.s_quest, o.s_opp];
      const newScore = scores.reduce((sum, s, i) => sum + (s || 1.0) * (Object.values(newWeights)[i] || 0), 0);
      return { score: newScore, hourly: o.actual_hourly };
    }).sort((a, b) => a.score - b.score);

    // 閾値を0.5〜1.2の範囲で0.05刻みで探索。閾値以上のオファーの平均時給が最大になる点を見つける
    let bestThreshold = 0.85, bestAvgHourly = 0;
    for (let t = 0.5; t <= 1.2; t += 0.05) {
      const above = scored.filter(s => s.score >= t);
      if (above.length < 3) continue; // 最低3件は受ける
      const avgH = above.reduce((a, s) => a + s.hourly, 0) / above.length;
      if (avgH > bestAvgHourly) { bestAvgHourly = avgH; bestThreshold = Math.round(t * 100) / 100; }
    }
    newWeights.score_threshold = bestThreshold;

    // Step 6: BQに保存
    await updateCoefficients(newWeights);
    cache.coefficients = { data: null, expiry: 0 };

    // 最適化ログをRTDBに保存
    const optimizationLog = {
      timestamp: Date.now(),
      data_count: offers.length,
      actual_count: withActual.length,
      correlations,
      old_weights: Object.fromEntries(weightKeys.map((k, i) => [k, currentWeights[i]])),
      new_weights: newWeights,
      avg_actual_hourly: Math.round(avgActualHourly),
      optimal_threshold: bestThreshold,
      learning_rate: LEARNING_RATE
    };
    const rtdbUrl = FIREBASE_DB_URL + '/pdca.json' + (FIREBASE_DB_SECRET ? '?auth=' + FIREBASE_DB_SECRET : '');
    fetch(rtdbUrl, { method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ last_optimization: optimizationLog })
    }).catch(() => {});

    console.log('Weights optimized:', JSON.stringify(newWeights), 'threshold:', bestThreshold, 'avg_hourly:', Math.round(avgActualHourly));
    return { optimized: true, weights: newWeights, threshold: bestThreshold, data_count: withActual.length, avg_hourly: Math.round(avgActualHourly) };
  } catch (e) {
    console.error('optimizeWeights error:', e);
    return { optimized: false, reason: e.message };
  }
}

console.log('UberEats AI Judge Cloud Functions loaded');
