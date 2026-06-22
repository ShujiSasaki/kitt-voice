#!/usr/bin/env node
/**
 * 深掘り分析: ツイート(テキスト+画像) × 投稿時の市場データ を統合分析
 * Gemini Vision APIでチャート画像を読み、市場データと照合して判断パターンを抽出
 */

const fs = require('fs');
const path = require('path');

const GEMINI_API_KEY = process.env.GEMINI_API_KEY;
const CONCURRENCY = 2;
const DELAY = 2000;

// ツイートの日付をパース
function parseDate(dateStr) {
  if (!dateStr) return null;
  // ISO format
  if (dateStr.includes('T')) return new Date(dateStr);
  // "May 1, 2026" format
  const d = new Date(dateStr);
  if (!isNaN(d.getTime())) return d;
  return null;
}

// Binance APIで特定時刻の市場データ(価格+OI+FR)を取得
async function getMarketDataAt(timestamp) {
  const ms = timestamp.getTime();
  try {
    const [klineRes, oiRes, frRes] = await Promise.all([
      fetch(`https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=4h&startTime=${ms - 4*3600000}&endTime=${ms + 4*3600000}&limit=3`, { signal: AbortSignal.timeout(10000) }),
      fetch(`https://fapi.binance.com/futures/data/openInterestHist?symbol=BTCUSDT&period=4h&startTime=${ms - 8*3600000}&endTime=${ms + 4*3600000}&limit=3`, { signal: AbortSignal.timeout(10000) }),
      fetch(`https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT&startTime=${ms - 24*3600000}&endTime=${ms + 3600000}&limit=3`, { signal: AbortSignal.timeout(10000) }),
    ]);

    const klines = await klineRes.json();
    const oiData = await oiRes.json();
    const frData = await frRes.json();

    if (!klines || klines.length === 0) return null;

    const closest = klines.reduce((best, k) => {
      const diff = Math.abs(k[0] - ms);
      return diff < Math.abs(best[0] - ms) ? k : best;
    });

    // OIの変化率
    let oiValue = null, oiChange = null;
    if (oiData && oiData.length >= 2) {
      oiValue = parseFloat(oiData[oiData.length - 1].sumOpenInterest);
      const prev = parseFloat(oiData[oiData.length - 2].sumOpenInterest);
      oiChange = ((oiValue - prev) / prev * 100);
    } else if (oiData && oiData.length === 1) {
      oiValue = parseFloat(oiData[0].sumOpenInterest);
    }

    // FR
    let fundingRate = null;
    if (frData && frData.length > 0) {
      fundingRate = parseFloat(frData[frData.length - 1].fundingRate);
    }

    return {
      open: parseFloat(closest[1]),
      high: parseFloat(closest[2]),
      low: parseFloat(closest[3]),
      close: parseFloat(closest[4]),
      volume: parseFloat(closest[5]),
      taker_buy_ratio: parseFloat(closest[9]) / parseFloat(closest[5]), // taker buy / total
      open_interest: oiValue,
      oi_change_pct: oiChange ? +oiChange.toFixed(2) : null,
      funding_rate: fundingRate,
    };
  } catch { return null; }
}

// 画像URLをbase64に変換
async function imageToBase64(url) {
  try {
    const res = await fetch(url, { signal: AbortSignal.timeout(15000) });
    if (!res.ok) return null;
    const buf = await res.arrayBuffer();
    return Buffer.from(buf).toString('base64');
  } catch { return null; }
}

// Gemini Vision APIでチャート画像+テキスト+市場データを分析
async function analyzeTradeWithVision(tweet, marketData, imageBase64) {
  const parts = [];

  // テキスト部分
  let prompt = `以下はBTCトレーダーのツイートと、投稿時の市場データです。

=== ツイート ===
${tweet.text}

=== 投稿時の市場データ ===
BTC価格: $${marketData?.close || '不明'}
高値: $${marketData?.high || '不明'}
安値: $${marketData?.low || '不明'}
出来高: ${marketData?.volume ? Math.round(marketData.volume).toLocaleString() : '不明'} BTC
OI(未決済建玉): ${marketData?.open_interest ? '$' + Math.round(marketData.open_interest).toLocaleString() : '不明'}
OI変化率(4H): ${marketData?.oi_change_pct != null ? marketData.oi_change_pct + '%' : '不明'}
ファンディングレート: ${marketData?.funding_rate != null ? (marketData.funding_rate * 100).toFixed(4) + '%' : '不明'}
テイカー買い比率: ${marketData?.taker_buy_ratio != null ? (marketData.taker_buy_ratio * 100).toFixed(1) + '%' : '不明'}
`;

  if (imageBase64) {
    prompt += `\n=== 添付チャート画像 ===
この画像はトレーダーが投稿したチャートスクリーンショットです。

以下を分析してください:
1. チャートに描かれているテクニカル分析(ライン、パターン、インジケーター)
2. トレーダーが何を根拠にこの判断をしたか
3. エントリー/イグジットの具体的な価格帯
4. 使用している時間足
5. テクニカルインジケーターの設定値(MA期間、フィボレベル等)
`;

    parts.push({ text: prompt });
    parts.push({
      inline_data: {
        mime_type: 'image/jpeg',
        data: imageBase64
      }
    });
  } else {
    prompt += `\n画像なし。テキストのみから分析してください:
1. トレーダーが何を根拠にこの判断をしたか
2. 言及されている価格帯
3. 使用している分析手法
`;
    parts.push({ text: prompt });
  }

  prompt += `\nJSON形式で回答:
{
  "action": "LONG"|"SHORT"|"CLOSE"|"OTHER",
  "entry_price": 数値またはnull,
  "stop_loss": 数値またはnull,
  "take_profit": 数値またはnull,
  "timeframe": "時間足",
  "indicators_used": ["使用インジケーター"],
  "chart_patterns": ["チャートパターン"],
  "confidence_factors": ["判断の根拠"],
  "market_context": "相場環境の認識",
  "reasoning": "判断理由の詳細"
}`;

  // 画像なしの場合はテキストのみ
  if (!imageBase64) {
    parts[0].text = prompt;
  }

  try {
    const res = await fetch(
      `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=${GEMINI_API_KEY}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          contents: [{ parts }],
          generationConfig: {
            responseMimeType: 'application/json',
            maxOutputTokens: 1024,
            thinkingConfig: { thinkingBudget: 0 },
          },
        }),
        signal: AbortSignal.timeout(30000),
      }
    );
    const data = await res.json();
    const text = data.candidates?.[0]?.content?.parts?.[0]?.text || '{}';
    return JSON.parse(text.replace(/```json\n?/g, '').replace(/```/g, '').trim());
  } catch (e) {
    return { error: e.message };
  }
}

async function main() {
  const trader = process.argv[2] || 'smile_danjer';
  const maxTweets = parseInt(process.argv[3]) || 100; // 分析するツイート数

  console.log(`=== Deep Analysis: ${trader} (max ${maxTweets} tweets) ===\n`);

  // ツイートデータ読み込み
  const tweetsData = JSON.parse(fs.readFileSync(`/tmp/${trader}_tweets.json`));
  const tweets = tweetsData.tweets;

  // トレードアクションを含むツイートをフィルタ
  const actionPatterns = [
    /ロング|long(?:ed|した)/i,
    /ショート|short(?:ed|した)/i,
    /利確|利食|TP|テイクプロフィット/i,
    /損切|LC|SL|ロスカ|カット/i,
    /エントリー|entry|イン(?:した|！)/i,
    /買い(?:増し|ました)|追加ロング/i,
    /売り(?:増し|ました)|追加ショート/i,
  ];

  const tradeTweets = tweets.filter(t => {
    const hasAction = actionPatterns.some(p => p.test(t.text));
    const hasImage = t.media?.photos?.length > 0;
    const date = parseDate(t.created_at || t.date);
    // 2019年10月以降(Binance先物データが存在)
    return hasAction && date && date >= new Date('2019-10-01');
  });

  console.log(`Trade tweets (2024+): ${tradeTweets.length}`);
  console.log(`With images: ${tradeTweets.filter(t => t.media?.photos?.length > 0).length}`);

  // 画像付きを優先、最新から
  const sorted = tradeTweets.sort((a, b) => {
    const hasImgA = (a.media?.photos?.length || 0) > 0 ? 1 : 0;
    const hasImgB = (b.media?.photos?.length || 0) > 0 ? 1 : 0;
    if (hasImgA !== hasImgB) return hasImgB - hasImgA;
    return (b.status_id || '').localeCompare(a.status_id || '');
  });

  const selected = sorted.slice(0, maxTweets);
  console.log(`Analyzing: ${selected.length} tweets\n`);

  const results = [];
  let ok = 0, fail = 0;

  for (let i = 0; i < selected.length; i++) {
    const tweet = selected[i];
    const date = parseDate(tweet.created_at || tweet.date);

    // 市場データ取得
    const marketData = date ? await getMarketDataAt(date) : null;

    // 画像取得(最初の1枚)
    let imageBase64 = null;
    if (tweet.media?.photos?.[0]?.url) {
      imageBase64 = await imageToBase64(tweet.media.photos[0].url);
    }

    // AI分析
    const analysis = await analyzeTradeWithVision(tweet, marketData, imageBase64);

    results.push({
      status_id: tweet.status_id,
      date: date?.toISOString() || null,
      text: tweet.text.substring(0, 300),
      has_image: !!imageBase64,
      image_count: tweet.media?.photos?.length || 0,
      market_price: marketData?.close || null,
      analysis,
    });

    ok++;
    if (ok % 5 === 0) {
      process.stdout.write(`\r  Progress: ${ok}/${selected.length}`);
    }
    await new Promise(r => setTimeout(r, DELAY));
  }

  console.log(`\n\nAnalysis complete: ${ok} ok, ${fail} fail`);

  // === 結果を集約 ===
  const actions = {};
  const indicators = {};
  const patterns = {};
  const timeframes = {};

  for (const r of results) {
    const a = r.analysis;
    if (!a || a.error) continue;

    // アクション集計
    actions[a.action] = (actions[a.action] || 0) + 1;

    // インジケーター集計
    for (const ind of (a.indicators_used || [])) {
      indicators[ind] = (indicators[ind] || 0) + 1;
    }

    // パターン集計
    for (const pat of (a.chart_patterns || [])) {
      patterns[pat] = (patterns[pat] || 0) + 1;
    }

    // 時間足集計
    if (a.timeframe) timeframes[a.timeframe] = (timeframes[a.timeframe] || 0) + 1;
  }

  // ソートして表示
  const sortObj = obj => Object.entries(obj).sort((a, b) => b[1] - a[1]);

  console.log('\n=== 集約結果 ===');
  console.log('\nActions:', JSON.stringify(sortObj(actions)));
  console.log('\nTop Indicators:', JSON.stringify(sortObj(indicators).slice(0, 15)));
  console.log('\nTop Patterns:', JSON.stringify(sortObj(patterns).slice(0, 15)));
  console.log('\nTimeframes:', JSON.stringify(sortObj(timeframes)));

  // レポート生成
  const report = {
    trader,
    analyzed_count: results.length,
    with_images: results.filter(r => r.has_image).length,
    date_range: {
      from: results.filter(r => r.date).map(r => r.date).sort()[0],
      to: results.filter(r => r.date).map(r => r.date).sort().pop(),
    },
    summary: {
      actions: sortObj(actions),
      top_indicators: sortObj(indicators).slice(0, 20),
      top_patterns: sortObj(patterns).slice(0, 20),
      timeframes: sortObj(timeframes),
    },
    individual_analyses: results,
  };

  const outFile = path.join(__dirname, `deep_analysis_${trader}_${new Date().toISOString().split('T')[0]}.json`);
  fs.writeFileSync(outFile, JSON.stringify(report, null, 2));
  console.log(`\nSaved to: ${outFile}`);

  // マークダウンレポートも生成
  let md = `# ${trader} 深掘りトレード分析\n\n`;
  md += `分析期間: ${report.date_range.from?.split('T')[0]} 〜 ${report.date_range.to?.split('T')[0]}\n`;
  md += `分析ツイート数: ${report.analyzed_count} (画像付き: ${report.with_images})\n\n`;

  md += `## アクション分布\n`;
  for (const [k, v] of sortObj(actions)) md += `- ${k}: ${v}回\n`;

  md += `\n## 使用インジケーター (頻度順)\n`;
  for (const [k, v] of sortObj(indicators).slice(0, 20)) md += `- ${k}: ${v}回\n`;

  md += `\n## チャートパターン (頻度順)\n`;
  for (const [k, v] of sortObj(patterns).slice(0, 20)) md += `- ${k}: ${v}回\n`;

  md += `\n## 時間足\n`;
  for (const [k, v] of sortObj(timeframes)) md += `- ${k}: ${v}回\n`;

  md += `\n## 個別トレード分析 (抜粋)\n\n`;
  for (const r of results.slice(0, 30)) {
    if (!r.analysis || r.analysis.error) continue;
    md += `### ${r.date?.split('T')[0] || '不明'} | BTC $${r.market_price || '?'} | ${r.analysis.action || '?'}\n`;
    md += `> ${r.text.substring(0, 150)}\n\n`;
    md += `- 根拠: ${(r.analysis.confidence_factors || []).join(', ')}\n`;
    md += `- インジケーター: ${(r.analysis.indicators_used || []).join(', ')}\n`;
    md += `- パターン: ${(r.analysis.chart_patterns || []).join(', ')}\n`;
    if (r.analysis.entry_price) md += `- エントリー: $${r.analysis.entry_price}`;
    if (r.analysis.stop_loss) md += ` SL: $${r.analysis.stop_loss}`;
    if (r.analysis.take_profit) md += ` TP: $${r.analysis.take_profit}`;
    md += `\n- 判断理由: ${r.analysis.reasoning || ''}\n\n`;
  }

  const mdFile = path.join(__dirname, '..', 'btc-research', `${trader}_trade_analysis.md`);
  fs.writeFileSync(mdFile, md);
  console.log(`Report saved to: ${mdFile}`);
}

main().catch(console.error);
