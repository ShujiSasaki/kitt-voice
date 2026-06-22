#!/usr/bin/env node
/**
 * 全ツイート分析: 500件ずつチャンクに分割して全件をGeminiに渡す
 * トレード関連だけでなく全投稿を対象に、意図・背景・哲学を抽出
 */

const fs = require('fs');
const path = require('path');

const GEMINI_API_KEY = process.env.GEMINI_API_KEY;
const CHUNK_SIZE = 500;
const DELAY = 3000;

async function analyzeChunk(trader, tweets, chunkIndex, totalChunks) {
  const tweetText = tweets.map((t, i) => {
    const date = t.created_at || t.date || '?';
    const media = t.media?.photos?.length ? `[画像${t.media.photos.length}枚]` : '';
    return `[${date}] ${t.text} ${media}`;
  }).join('\n---\n');

  const prompt = `あなたはBTCトレーダーの思考分析の専門家です。
以下は@${trader}の投稿${CHUNK_SIZE}件(チャンク${chunkIndex + 1}/${totalChunks})です。

重要: 全ての投稿に意図・理由・背景があります。トレード関連の投稿だけでなく、日常ツイート、愚痴、感情表現、他者へのリプ、休む宣言なども全て分析対象です。1つも軽視しないでください。

=== 投稿 ===
${tweetText}

=== 抽出すべき項目 ===

1. **レバレッジの考え方と使い分け**
   - どの場面で何倍を使うか、その理由
   - ハイレバとローレバの切り替え基準
   - レバレッジに対する哲学的な考え

2. **ポジションサイズの決め方**
   - 資金の何%を投入するか
   - 分割エントリーの具体的な方法
   - ナンピンのルール(する/しない、間隔、上限)
   - 確信度とポジサイズの関係

3. **資金管理のルール**
   - 出金タイミング
   - DD(ドローダウン)した時の対応
   - 1日/1週/1月の損失上限
   - 口座リセットの判断基準

4. **メンタル管理**
   - 負けた後の行動パターン
   - 連勝/連敗時の心理変化
   - トレードを休む判断基準
   - 感情的になった時の自己認識

5. **トレードしない判断(ノートレ)**
   - どういう相場でやらないか
   - 何が見えたら手を出さないか
   - 休む基準(時間帯、曜日、体調、メンタル)

6. **他者への助言(=自分のルール)**
   - 初心者向けアドバイスの内容
   - 「これはするな」という警告
   - 推奨するツール・設定

7. **失敗から学んだこと**
   - 具体的な失敗事例とその振り返り
   - 「もうしない」と誓ったこと
   - 手法の修正・進化のきっかけ

8. **取引所・ツールの使い分け**
   - どの取引所をどの場面で使うか
   - MT4/MT5の設定・使い方
   - TradingView, coinglass等のツール活用法

9. **時間に関する判断**
   - 取引する時間帯の傾向
   - 寝る前のポジション管理
   - 指標発表・イベント前後の対応

10. **見落としがちな微細なルール**
    - 本人が明示的にルールとは言っていないが、行動パターンから読み取れる暗黙のルール
    - 繰り返し出現する判断パターン
    - 言い回しや表現の癖から推測できる思考の優先順位

全て具体的な投稿を引用して説明すること。引用は [日付] テキストの冒頭50文字 の形式で。`;

  try {
    const res = await fetch(
      `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=${GEMINI_API_KEY}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          contents: [{ parts: [{ text: prompt }] }],
          generationConfig: { maxOutputTokens: 65536 },
        }),
        signal: AbortSignal.timeout(300000),
      }
    );
    const data = await res.json();
    return data.candidates?.[0]?.content?.parts?.map(p => p.text).join('') || 'ERROR: ' + JSON.stringify(data).substring(0, 300);
  } catch (e) {
    return `ERROR: ${e.message}`;
  }
}

async function synthesize(trader, chunkResults) {
  const combined = chunkResults.map((r, i) => `=== チャンク${i + 1}の分析結果 ===\n${r}`).join('\n\n');

  const prompt = `あなたはBTCトレーダー分析の最終レポート作成者です。

以下は@${trader}の全投稿を${chunkResults.length}チャンクに分けて分析した結果です。

${combined}

=== 指示 ===
上記の全チャンク分析を統合し、このトレーダーの**完全な意思決定マニュアル**を作成してください。

このマニュアルを読めば、このトレーダーと同じ判断ができるようになるレベルの詳細さが必要です。

以下の構成で:

1. レバレッジ戦略（場面別の倍率、切り替え基準、哲学）
2. ポジションサイジング（確信度別の投入率、分割ルール、ナンピンルール）
3. 資金管理（出金、DD対応、口座リセット、月次目標）
4. エントリー判断（全パターン、優先順位、複合条件）
5. イグジット判断（利確基準、損切り基準、建値ストップ、トレイリング）
6. ノートレ判断（やらない条件、休む基準）
7. メンタル管理（負け後、連勝後、感情制御）
8. 時間管理（取引時間帯、寝る前、イベント前後）
9. ツール活用（取引所、MT4/5、TradingView、清算マップ、OI）
10. 暗黙のルール（言語化されていないが行動から読み取れるルール）

各項目に必ず具体的な投稿の引用を含めること。
矛盾する言動がある場合は、最新の投稿を優先しつつ、変遷も記述すること。`;

  try {
    const res = await fetch(
      `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=${GEMINI_API_KEY}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          contents: [{ parts: [{ text: prompt }] }],
          generationConfig: { maxOutputTokens: 65536 },
        }),
        signal: AbortSignal.timeout(300000),
      }
    );
    const data = await res.json();
    return data.candidates?.[0]?.content?.parts?.map(p => p.text).join('') || 'ERROR';
  } catch (e) {
    return `ERROR: ${e.message}`;
  }
}

async function main() {
  const trader = process.argv[2] || 'smile_danjer';
  console.log(`=== Full Analysis: ${trader} ===\n`);

  const tweetsData = JSON.parse(fs.readFileSync(`/tmp/${trader}_tweets.json`));
  const tweets = tweetsData.tweets;
  console.log(`Total tweets: ${tweets.length}`);

  // チャンク分割
  const chunks = [];
  for (let i = 0; i < tweets.length; i += CHUNK_SIZE) {
    chunks.push(tweets.slice(i, i + CHUNK_SIZE));
  }
  console.log(`Chunks: ${chunks.length} (${CHUNK_SIZE} tweets each)\n`);

  // 各チャンク分析
  const chunkResults = [];
  for (let i = 0; i < chunks.length; i++) {
    console.log(`Analyzing chunk ${i + 1}/${chunks.length} (${chunks[i].length} tweets)...`);
    const result = await analyzeChunk(trader, chunks[i], i, chunks.length);
    chunkResults.push(result);
    console.log(`  Done: ${result.length} chars`);

    // 中間保存
    fs.writeFileSync(
      path.join(__dirname, `full_analysis_${trader}_chunks.json`),
      JSON.stringify(chunkResults, null, 2)
    );

    if (i < chunks.length - 1) await new Promise(r => setTimeout(r, DELAY));
  }

  console.log(`\nAll chunks analyzed. Synthesizing...`);

  // 統合レポート生成
  const finalReport = await synthesize(trader, chunkResults);

  const outFile = path.join(__dirname, '..', 'btc-research', `${trader}_complete_manual.md`);
  fs.writeFileSync(outFile, finalReport);
  console.log(`\nFinal report: ${finalReport.length} chars`);
  console.log(`Saved to: ${outFile}`);
}

main().catch(console.error);
