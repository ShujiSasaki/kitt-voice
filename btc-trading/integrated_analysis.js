#!/usr/bin/env node
/**
 * 統合分析: テキスト全件分析 + 画像分析 + 市場データ を統合して多角的に分析
 *
 * 分析軸:
 * 1. テキスト×画像×市場データの統合(投稿時に何を見てどう判断したか)
 * 2. 時系列での判断の変遷(年ごとの手法進化)
 * 3. 成功vs失敗トレードの比較
 * 4. 市場環境別(ブル/ベア/レンジ)の戦略差
 * 5. インジケーター設定値の具体的抽出
 */

const fs = require('fs');
const path = require('path');

const GEMINI_API_KEY = process.env.GEMINI_API_KEY;

async function gemini(prompt, maxTokens = 65536) {
  const res = await fetch(
    `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=${GEMINI_API_KEY}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        contents: [{ parts: [{ text: prompt }] }],
        generationConfig: { maxOutputTokens: maxTokens },
      }),
      signal: AbortSignal.timeout(300000),
    }
  );
  const data = await res.json();
  return data.candidates?.[0]?.content?.parts?.map(p => p.text).join('') || 'ERROR';
}

async function main() {
  const trader = process.argv[2] || '4HpO4Q9Dz3CWkhV';
  const traderName = trader === 'smile_danjer' ? 'danjer' : 'ronpochi';
  console.log(`=== Integrated Analysis: ${traderName} (${trader}) ===\n`);

  // データ読み込み
  const tweetsData = JSON.parse(fs.readFileSync(`/tmp/${trader}_tweets.json`));
  const imageData = JSON.parse(fs.readFileSync(path.join(__dirname, `image_analysis_${trader}.json`)));
  const textManual = fs.readFileSync(path.join(__dirname, '..', 'btc-research', `${trader}_complete_manual.md`), 'utf8');

  // 画像分析結果をstatus_idでインデックス化
  const imageIndex = {};
  for (const r of imageData.results) {
    imageIndex[r.status_id] = r.analysis;
  }

  // チャート画像の分析結果からインジケーター設定値を集約
  const chartResults = imageData.results.filter(r => r.analysis?.image_type === 'chart');
  console.log(`Chart images: ${chartResults.length}`);

  // ===== 分析1: インジケーター設定値の具体的抽出 =====
  console.log('\n[1/5] インジケーター設定値の抽出...');
  const indicatorData = chartResults
    .filter(r => r.analysis?.indicators?.length > 0)
    .map(r => `[${r.date?.substring(0, 10) || '?'}] ${JSON.stringify(r.analysis.indicators)}`)
    .join('\n');

  const indicatorAnalysis = await gemini(`以下はBTCトレーダー${traderName}のチャート画像から抽出したインジケーターデータです。

${indicatorData.substring(0, 30000)}

全データを通読し、以下をまとめてください:
1. 使用している全インジケーターのリスト(名前、パラメータ/期間、用途)
2. 時間足ごとのインジケーター使い分け
3. インジケーターの組み合わせパターン(何と何をセットで使うか)
4. 年ごとの変化(追加/廃止されたインジケーター)
5. 最も依存度が高いインジケーターTOP5とその根拠

具体的な数値(MA期間、フィボレベル等)を必ず明記すること。`);
  console.log(`  Done: ${indicatorAnalysis.length} chars`);

  // ===== 分析2: 時系列での判断の変遷 =====
  console.log('\n[2/5] 時系列での判断の変遷...');
  // 年ごとにツイートをサンプリング
  const byYear = {};
  for (const t of tweetsData.tweets) {
    const date = t.created_at || t.date || '';
    let year = 'unknown';
    const m = date.match(/(20\d{2})/);
    if (m) year = m[1];
    if (!byYear[year]) byYear[year] = [];
    byYear[year].push(t);
  }
  const yearSummary = Object.entries(byYear)
    .filter(([y]) => y !== 'unknown')
    .sort()
    .map(([year, tweets]) => {
      // 各年からトレード関連を50件サンプリング
      const trade = tweets.filter(t => /ロング|ショート|エントリー|利確|損切|レバ|ポジ|サイクル|フラクタル|OI|FR/i.test(t.text));
      const sample = trade.slice(0, 50).map(t => t.text.substring(0, 150)).join('\n');
      return `=== ${year}年 (全${tweets.length}件, トレード関連${trade.length}件) ===\n${sample}`;
    }).join('\n\n');

  const timeEvolution = await gemini(`以下はBTCトレーダー${traderName}の年ごとのツイートサンプルです。

${yearSummary.substring(0, 30000)}

年ごとの手法の進化を分析してください:
1. 各年の主要な手法・考え方
2. 追加された分析手法やツール
3. 廃止・修正された手法とその理由
4. レバレッジやリスク管理の変化
5. メンタル管理の成熟度の変化
6. 全体を通しての成長ストーリー

具体的なツイートの引用を含めること。`);
  console.log(`  Done: ${timeEvolution.length} chars`);

  // ===== 分析3: 成功vs失敗トレード =====
  console.log('\n[3/5] 成功vs失敗トレードの比較...');
  const winTweets = tweetsData.tweets.filter(t => /利確|勝ち|プラス|\+\d+万|\+\d+マソ|爆益|日当ゲット/i.test(t.text));
  const lossTweets = tweetsData.tweets.filter(t => /損切|負け|マイナス|-\d+万|-\d+マソ|0カット|ロスカ|爆損|全損/i.test(t.text));

  const winSample = winTweets.slice(-40).map(t => {
    const img = imageIndex[t.status_id];
    const imgInfo = img ? ` [画像:${img.image_type || '?'}, TF:${img.timeframe || '?'}]` : '';
    return `[${(t.created_at || t.date || '?').substring(0, 10)}] ${t.text.substring(0, 200)}${imgInfo}`;
  }).join('\n---\n');

  const lossSample = lossTweets.slice(-40).map(t => {
    const img = imageIndex[t.status_id];
    const imgInfo = img ? ` [画像:${img.image_type || '?'}, TF:${img.timeframe || '?'}]` : '';
    return `[${(t.created_at || t.date || '?').substring(0, 10)}] ${t.text.substring(0, 200)}${imgInfo}`;
  }).join('\n---\n');

  const winLossAnalysis = await gemini(`以下はBTCトレーダー${traderName}の成功トレードと失敗トレードのツイートです。

=== 成功トレード (${winTweets.length}件中40件) ===
${winSample}

=== 失敗トレード (${lossTweets.length}件中40件) ===
${lossSample}

多角的に比較分析してください:
1. 成功トレードに共通する条件(時間足、パターン、インジケーター、相場環境)
2. 失敗トレードに共通する条件
3. 成功と失敗を分ける決定的な要因は何か
4. 失敗後の具体的な学び(ツイートから読み取れるもの)
5. 勝ちパターンの再現性(同じ条件で繰り返し勝っているか)
6. 負けパターンの改善(同じ失敗を繰り返しているか、改善しているか)
7. リスクリワード比の実態(勝ち幅vs負け幅)

具体的な金額・価格を引用すること。`);
  console.log(`  Done: ${winLossAnalysis.length} chars`);

  // ===== 分析4: 市場環境別の戦略差 =====
  console.log('\n[4/5] 市場環境別の戦略分析...');
  const bullTweets = tweetsData.tweets.filter(t => /上昇トレンド|ブル|強気|爆上げ|ATH|最高値|買い場/i.test(t.text)).slice(-30);
  const bearTweets = tweetsData.tweets.filter(t => /下降トレンド|ベア|弱気|暴落|大暴落|底|セリクラ/i.test(t.text)).slice(-30);
  const rangeTweets = tweetsData.tweets.filter(t => /レンジ|ヨコヨコ|煮詰まり|方向感|ノーポジ|待ち|わからん/i.test(t.text)).slice(-30);

  const envSample = (label, tweets) => tweets.map(t => `[${(t.created_at || t.date || '?').substring(0, 10)}] ${t.text.substring(0, 150)}`).join('\n');

  const marketEnvAnalysis = await gemini(`以下はBTCトレーダー${traderName}の相場環境別ツイートです。

=== ブル相場(上昇トレンド)時 ===
${envSample('bull', bullTweets)}

=== ベア相場(下降トレンド)時 ===
${envSample('bear', bearTweets)}

=== レンジ相場時 ===
${envSample('range', rangeTweets)}

各市場環境での戦略の違いを分析してください:
1. ブル相場での戦略(レバ、ポジサイズ、エントリー基準、利確基準)
2. ベア相場での戦略
3. レンジ相場での戦略
4. 環境の切り替えをどう判断しているか(何を見て「今はブルだ/ベアだ/レンジだ」と判断するか)
5. 最も得意な環境と苦手な環境
6. 環境を読み間違えた時のリカバリー方法

具体的なツイートを引用すること。`);
  console.log(`  Done: ${marketEnvAnalysis.length} chars`);

  // ===== 分析5: 画像から読み取れる具体的なライン・価格帯 =====
  console.log('\n[5/5] チャート画像からの具体的ライン・価格帯...');
  const lineData = chartResults
    .filter(r => r.analysis?.lines?.length > 0 || r.analysis?.key_prices?.length > 0 || r.analysis?.entry_exit)
    .slice(-100)
    .map(r => {
      const a = r.analysis;
      return `[${r.date?.substring(0, 10) || '?'}] Lines:${JSON.stringify(a.lines || []).substring(0, 200)} Prices:${JSON.stringify(a.key_prices || []).substring(0, 200)} Entry:${JSON.stringify(a.entry_exit || {})}`;
    }).join('\n');

  const lineAnalysis = await gemini(`以下はBTCトレーダー${traderName}のチャート画像から抽出したライン・価格帯データです。

${lineData.substring(0, 30000)}

分析してください:
1. 最も多く引かれるラインの種類とその使い方
2. サポート/レジスタンスの設定方法(何を基準に引くか)
3. フィボナッチの使用レベル(0.382, 0.5, 0.618, 0.786, 1.272等の頻度)
4. エントリー価格と損切り価格の距離(リスク幅)の傾向
5. 利確目標の設定方法
6. 複数のラインが重なる「コンフルエンスゾーン」の活用パターン`);
  console.log(`  Done: ${lineAnalysis.length} chars`);

  // ===== 統合レポート生成 =====
  console.log('\n[統合] 全分析結果を統合...');
  const finalReport = await gemini(`あなたはBTCトレード手法の研究者です。以下は${traderName}の5つの分析結果です。

=== テキスト全件分析(意思決定マニュアル、要約) ===
${textManual.substring(0, 5000)}

=== 分析1: インジケーター設定値 ===
${indicatorAnalysis.substring(0, 5000)}

=== 分析2: 時系列での変遷 ===
${timeEvolution.substring(0, 5000)}

=== 分析3: 成功vs失敗 ===
${winLossAnalysis.substring(0, 5000)}

=== 分析4: 市場環境別戦略 ===
${marketEnvAnalysis.substring(0, 5000)}

=== 分析5: ライン・価格帯 ===
${lineAnalysis.substring(0, 5000)}

全ての分析を統合し、${traderName}の**完全なトレード意思決定マニュアル**を作成してください。

このマニュアルを読んだAIが、${traderName}と同じ判断を下せるレベルの具体性が必要です。

構成:
1. トレーダープロフィール(スタイル、強み、弱み、成長の軌跡)
2. 相場環境の認識方法(何を見てブル/ベア/レンジを判断するか)
3. エントリー判断フロー(具体的なステップと条件、フローチャート形式)
4. ポジションサイジング(確信度×環境×レバの具体的な組み合わせ表)
5. イグジット判断(利確/損切り/建値ストップの具体的基準)
6. リスク管理(資金管理、DD対応、出金ルール)
7. メンタル管理(やらない判断、休む基準、感情制御)
8. 使用ツールとインジケーター(名前、パラメータ、用途の完全リスト)
9. 成功パターンTOP10(具体的条件と再現方法)
10. 失敗パターンTOP5(原因と回避方法)
11. 時間管理(取引時間帯、アノマリー、イベント対応)
12. 暗黙のルール(行動から読み取れる未言語化のルール)

全項目に具体的な数値・価格・引用を含めること。`);
  console.log(`  Done: ${finalReport.length} chars`);

  // 保存
  const outDir = path.join(__dirname, '..', 'btc-research');

  // 個別分析も保存
  fs.writeFileSync(path.join(outDir, `${trader}_indicator_analysis.md`), indicatorAnalysis);
  fs.writeFileSync(path.join(outDir, `${trader}_time_evolution.md`), timeEvolution);
  fs.writeFileSync(path.join(outDir, `${trader}_win_loss_analysis.md`), winLossAnalysis);
  fs.writeFileSync(path.join(outDir, `${trader}_market_env_analysis.md`), marketEnvAnalysis);
  fs.writeFileSync(path.join(outDir, `${trader}_line_analysis.md`), lineAnalysis);
  fs.writeFileSync(path.join(outDir, `${trader}_integrated_manual.md`), finalReport);

  console.log(`\nAll saved to btc-research/`);
  console.log(`Final manual: ${finalReport.length} chars`);
}

main().catch(console.error);
