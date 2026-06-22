#!/usr/bin/env node
/**
 * 全画像付きツイートの画像分析
 * チャート画像をGemini Visionで読み取り、テクニカル分析の詳細を抽出
 * 500件ずつチャンクで処理、各チャンクの結果を中間保存
 */

const fs = require('fs');
const path = require('path');

const GEMINI_API_KEY = process.env.GEMINI_API_KEY;
const CHUNK_SIZE = 20; // 画像付きは重いので小さいチャンク
const DELAY = 1500;

async function imageToBase64(url) {
  try {
    const res = await fetch(url, { signal: AbortSignal.timeout(15000) });
    if (!res.ok) return null;
    const buf = await res.arrayBuffer();
    return Buffer.from(buf).toString('base64');
  } catch { return null; }
}

async function analyzeImage(tweet, imageBase64) {
  const parts = [];

  const prompt = `BTCトレーダーが投稿したチャート画像とツイートテキストです。

ツイート: ${tweet.text.substring(0, 300)}
投稿日: ${tweet.created_at || tweet.date || '不明'}

この画像から以下を全て抽出してください:

1. 時間足(1分/5分/15分/30分/1H/4H/8H/日足/週足/月足)
2. 描画されているライン(トレンドライン、水平線、チャネル、フィボナッチ等)とその価格帯
3. 表示されているインジケーター(MA/EMA/MACD/RSI/ボリンジャー/GMMA/一目/VRVP/OI等)とその設定値・パラメータ
4. チャートパターン(三角/ウェッジ/フラッグ/ダブルトップ/インサイドバー等)
5. エントリーポイントや利確/損切りラインが描かれていればその価格
6. OI/FR/清算データが表示されていればその内容
7. 画像がチャートではない場合(損益画面、板情報、ニュース等)はその内容

JSON形式で回答:
{
  "image_type": "chart"|"pnl"|"orderbook"|"liquidation_map"|"oi_data"|"news"|"other",
  "timeframe": "時間足",
  "indicators": [{"name": "名前", "params": "設定値", "value": "現在値"}],
  "lines": [{"type": "種類", "price": 価格, "direction": "方向"}],
  "patterns": ["パターン名"],
  "entry_exit": {"entry": 価格, "sl": 価格, "tp": 価格},
  "oi_fr_data": {"oi_trend": "増減", "fr": "値"},
  "key_prices": [{"price": 価格, "significance": "意味"}],
  "summary": "50文字以内の要約"
}`;

  parts.push({ text: prompt });

  const mimeType = tweet.media?.photos?.[0]?.url?.includes('.png') ? 'image/png' : 'image/jpeg';
  parts.push({
    inline_data: {
      mime_type: mimeType,
      data: imageBase64
    }
  });

  // 2枚目以降の画像も追加(最大3枚)
  if (tweet.media?.photos?.length > 1) {
    for (let i = 1; i < Math.min(tweet.media.photos.length, 3); i++) {
      const img2 = await imageToBase64(tweet.media.photos[i].url);
      if (img2) {
        parts.push({
          inline_data: {
            mime_type: tweet.media.photos[i].url.includes('.png') ? 'image/png' : 'image/jpeg',
            data: img2
          }
        });
      }
    }
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
  console.log(`=== Image Analysis: ${trader} ===\n`);

  const tweetsData = JSON.parse(fs.readFileSync(`/tmp/${trader}_tweets.json`));

  // 画像付きツイートのみ
  const mediaTweets = tweetsData.tweets.filter(t => t.media?.photos?.length > 0);
  console.log(`Total tweets with images: ${mediaTweets.length}`);

  // 既存結果の読み込み(再開対応)
  const outFile = path.join(__dirname, `image_analysis_${trader}.json`);
  let existing = {};
  if (fs.existsSync(outFile)) {
    try {
      const data = JSON.parse(fs.readFileSync(outFile));
      for (const r of (data.results || [])) {
        existing[r.status_id] = r;
      }
      console.log(`Resuming: ${Object.keys(existing).length} already analyzed`);
    } catch {}
  }

  const toAnalyze = mediaTweets.filter(t => !existing[t.status_id]);
  console.log(`To analyze: ${toAnalyze.length}\n`);

  let ok = 0, fail = 0, skip = 0;

  for (let i = 0; i < toAnalyze.length; i++) {
    const tweet = toAnalyze[i];

    // 画像取得
    const imageBase64 = await imageToBase64(tweet.media.photos[0].url);
    if (!imageBase64) {
      skip++;
      if ((ok + fail + skip) % 50 === 0) process.stdout.write(`\r  Progress: ${ok + fail + skip}/${toAnalyze.length} (ok:${ok} fail:${fail} skip:${skip})`);
      continue;
    }

    // 分析
    const analysis = await analyzeImage(tweet, imageBase64);

    existing[tweet.status_id] = {
      status_id: tweet.status_id,
      date: tweet.created_at || tweet.date || null,
      text: tweet.text.substring(0, 200),
      image_count: tweet.media.photos.length,
      analysis
    };

    if (analysis.error) fail++;
    else ok++;

    if ((ok + fail + skip) % 50 === 0) {
      process.stdout.write(`\r  Progress: ${ok + fail + skip}/${toAnalyze.length} (ok:${ok} fail:${fail} skip:${skip})`);
      // 中間保存
      const results = Object.values(existing);
      fs.writeFileSync(outFile, JSON.stringify({ trader, total: results.length, results }, null, 2));
    }

    await new Promise(r => setTimeout(r, DELAY));
  }

  // 最終保存
  const results = Object.values(existing);
  fs.writeFileSync(outFile, JSON.stringify({ trader, total: results.length, results }, null, 2));

  console.log(`\n\nDone: ${ok} ok, ${fail} fail, ${skip} skip`);
  console.log(`Total analyzed: ${results.length}`);
  console.log(`Saved to: ${outFile}`);

  // 統計
  const charts = results.filter(r => r.analysis?.image_type === 'chart');
  const pnl = results.filter(r => r.analysis?.image_type === 'pnl');
  const liq = results.filter(r => r.analysis?.image_type === 'liquidation_map');
  const oi = results.filter(r => r.analysis?.image_type === 'oi_data');
  console.log(`\nImage types: chart:${charts.length} pnl:${pnl.length} liq:${liq.length} oi:${oi.length} other:${results.length - charts.length - pnl.length - liq.length - oi.length}`);
}

main().catch(console.error);
