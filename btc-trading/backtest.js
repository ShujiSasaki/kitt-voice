#!/usr/bin/env node
/**
 * BTC AI Backtest
 * 過去データでAI(Gemini)にトレーダーの判断を再現させてバックテスト
 *
 * 方式: 日足ベース。各日の4H足データ+ツイート履歴→AIが判断→ポジション管理→P&L計算
 */

const fs = require('fs');
const path = require('path');

// === 設定 ===
const GEMINI_API_KEY = process.env.GEMINI_API_KEY || fs.readFileSync(path.join(__dirname, '..', '.env'), 'utf8').match(/GEMINI_API_KEY=(.+)/)?.[1];
const CONCURRENCY = 3;
const DELAY = 1500; // Gemini rate limit対策

// === データ読み込み ===
const klines4h = JSON.parse(fs.readFileSync('/tmp/btc-data/btc_4h_all.json'));
const klinesDaily = JSON.parse(fs.readFileSync('/tmp/btc-data/klines_1d.json'));

function parseKline(k) {
  return {
    time: new Date(k[0]).toISOString(),
    open: parseFloat(k[1]),
    high: parseFloat(k[2]),
    low: parseFloat(k[3]),
    close: parseFloat(k[4]),
    volume: parseFloat(k[5]),
    quoteVolume: parseFloat(k[7]),
    trades: parseInt(k[8]),
    takerBuyVolume: parseFloat(k[9]),
  };
}

const daily = klinesDaily.map(parseKline);
const hourly4 = klines4h.map(parseKline);

// === テクニカル指標計算 ===
function sma(data, period) {
  if (data.length < period) return null;
  return data.slice(-period).reduce((a, b) => a + b, 0) / period;
}

function rsi(closes, period = 14) {
  if (closes.length < period + 1) return null;
  let gains = 0, losses = 0;
  for (let i = closes.length - period; i < closes.length; i++) {
    const diff = closes[i] - closes[i - 1];
    if (diff > 0) gains += diff;
    else losses -= diff;
  }
  if (losses === 0) return 100;
  const rs = (gains / period) / (losses / period);
  return 100 - (100 / (1 + rs));
}

function buildMarketContext(dayIndex) {
  const d = daily[dayIndex];
  const dayTime = new Date(d.time).getTime();

  // 直近の4H足(最大30本 = 5日分)
  const recent4h = hourly4.filter(k => {
    const t = new Date(k.time).getTime();
    return t <= dayTime && t > dayTime - 30 * 4 * 3600000;
  });

  // 日足の過去データ
  const pastDaily = daily.slice(Math.max(0, dayIndex - 90), dayIndex + 1);
  const closes = pastDaily.map(d => d.close);

  // テクニカル
  const sma20 = sma(closes, 20);
  const sma50 = sma(closes, 50);
  const sma200 = closes.length >= 200 ? sma(closes, 200) : null;
  const rsiVal = rsi(closes, 14);

  // ボリュームの変化
  const vol5 = sma(pastDaily.slice(-5).map(d => d.quoteVolume), 5);
  const vol20 = sma(pastDaily.slice(-20).map(d => d.quoteVolume), 20);

  // 価格変化
  const change1d = pastDaily.length >= 2 ? ((d.close - pastDaily[pastDaily.length - 2].close) / pastDaily[pastDaily.length - 2].close * 100) : 0;
  const change7d = pastDaily.length >= 8 ? ((d.close - pastDaily[pastDaily.length - 8].close) / pastDaily[pastDaily.length - 8].close * 100) : 0;
  const change30d = pastDaily.length >= 31 ? ((d.close - pastDaily[pastDaily.length - 31].close) / pastDaily[pastDaily.length - 31].close * 100) : 0;

  // 4Hの直近パターン
  const recent4hSummary = recent4h.slice(-12).map(k => ({
    time: k.time.split('T')[1].substring(0, 5),
    o: Math.round(k.open),
    h: Math.round(k.high),
    l: Math.round(k.low),
    c: Math.round(k.close),
  }));

  return {
    date: d.time.split('T')[0],
    price: d.close,
    open: d.open,
    high: d.high,
    low: d.low,
    volume_usd: Math.round(d.quoteVolume),
    change_1d: +change1d.toFixed(2),
    change_7d: +change7d.toFixed(2),
    change_30d: +change30d.toFixed(2),
    sma20: sma20 ? Math.round(sma20) : null,
    sma50: sma50 ? Math.round(sma50) : null,
    sma200: sma200 ? Math.round(sma200) : null,
    rsi14: rsiVal ? +rsiVal.toFixed(1) : null,
    price_vs_sma20: sma20 ? +((d.close - sma20) / sma20 * 100).toFixed(2) : null,
    price_vs_sma50: sma50 ? +((d.close - sma50) / sma50 * 100).toFixed(2) : null,
    volume_ratio: vol20 ? +(vol5 / vol20).toFixed(2) : null,
    daily_range_pct: +((d.high - d.low) / d.low * 100).toFixed(2),
    recent_4h: recent4hSummary,
    // 直近5日足
    recent_daily: pastDaily.slice(-5).map(d => ({
      date: d.time.split('T')[0],
      o: Math.round(d.open), h: Math.round(d.high),
      l: Math.round(d.low), c: Math.round(d.close),
    })),
  };
}

// === AI判断 ===
async function getAIJudgment(trader, traderProfile, tweetsSummary, marketContext) {
  const prompt = `あなたは${trader}というBTCトレーダーの思考を完全に再現するAIです。

=== ${trader}のトレードスタイル ===
${traderProfile}

=== ${trader}の過去の投稿から抽出した判断パターン ===
${tweetsSummary}

=== 現在の相場データ (${marketContext.date}) ===
${JSON.stringify(marketContext, null, 2)}

=== 指示 ===
${trader}として、この相場状況で下す判断を回答してください。
${trader}が実際にツイートで示してきた判断基準を忠実に再現すること。
「なんとなく」ではなく、具体的にどの条件がどう当てはまるか明示すること。

JSON形式で:
{
  "action": "LONG"|"SHORT"|"CLOSE_LONG"|"CLOSE_SHORT"|"HOLD"|"WAIT",
  "confidence": 0-100,
  "leverage": 数値(1-20),
  "position_size_pct": 0-100,
  "stop_loss_pct": 損切りライン(現在価格からの%),
  "take_profit_pct": 利確ライン(現在価格からの%),
  "reasoning": "100文字以内の判断理由"
}`;

  try {
    const res = await fetch(
      `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=${GEMINI_API_KEY}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          contents: [{ parts: [{ text: prompt }] }],
          generationConfig: { responseMimeType: 'application/json', maxOutputTokens: 512, thinkingConfig: { thinkingBudget: 0 } },
        }),
        signal: AbortSignal.timeout(30000),
      }
    );
    const data = await res.json();
    const text = data.candidates?.[0]?.content?.parts?.[0]?.text || '{}';
    return JSON.parse(text.replace(/```json\n?/g, '').replace(/```/g, '').trim());
  } catch (e) {
    return { action: 'HOLD', confidence: 0, reasoning: `Error: ${e.message}` };
  }
}

// === ポジション管理 & P&L計算 ===
function runBacktest(judgments, prices) {
  let capital = 10000; // 初期資金 $10,000
  let position = null; // { direction, entry_price, size_usd, leverage, stop_loss, take_profit }
  const trades = [];
  const equityCurve = [];
  let maxEquity = capital;
  let maxDrawdown = 0;

  for (let i = 0; i < judgments.length; i++) {
    const j = judgments[i];
    const price = prices[i];
    const date = j.date;

    // ポジションチェック (SL/TP)
    if (position) {
      const pnlPct = position.direction === 'LONG'
        ? (price.high - position.entry_price) / position.entry_price
        : (position.entry_price - price.low) / position.entry_price;

      const lossPct = position.direction === 'LONG'
        ? (position.entry_price - price.low) / position.entry_price
        : (price.high - position.entry_price) / position.entry_price;

      // ストップロス
      if (position.stop_loss_pct && lossPct * 100 >= position.stop_loss_pct) {
        const pnl = -position.stop_loss_pct / 100 * position.size_usd * position.leverage;
        capital += pnl;
        trades.push({
          date, type: 'SL', direction: position.direction,
          entry: position.entry_price, exit: position.direction === 'LONG' ? position.entry_price * (1 - position.stop_loss_pct / 100) : position.entry_price * (1 + position.stop_loss_pct / 100),
          pnl, leverage: position.leverage,
        });
        position = null;
      }
      // テイクプロフィット
      else if (position.take_profit_pct && pnlPct * 100 >= position.take_profit_pct) {
        const pnl = position.take_profit_pct / 100 * position.size_usd * position.leverage;
        capital += pnl;
        trades.push({
          date, type: 'TP', direction: position.direction,
          entry: position.entry_price, exit: position.direction === 'LONG' ? position.entry_price * (1 + position.take_profit_pct / 100) : position.entry_price * (1 - position.take_profit_pct / 100),
          pnl, leverage: position.leverage,
        });
        position = null;
      }
    }

    // AI判断を実行
    if (j.judgment) {
      const action = j.judgment.action;
      const confidence = j.judgment.confidence || 0;

      // CLOSE系
      if (position && (action === 'CLOSE_LONG' || action === 'CLOSE_SHORT' || action === 'CLOSE')) {
        const exitPrice = price.close;
        const pnlPct = position.direction === 'LONG'
          ? (exitPrice - position.entry_price) / position.entry_price
          : (position.entry_price - exitPrice) / position.entry_price;
        const pnl = pnlPct * position.size_usd * position.leverage;
        capital += pnl;
        trades.push({
          date, type: 'CLOSE', direction: position.direction,
          entry: position.entry_price, exit: exitPrice,
          pnl, leverage: position.leverage,
        });
        position = null;
      }

      // エントリー (confidence > 50 のみ)
      if (!position && (action === 'LONG' || action === 'SHORT') && confidence > 50) {
        const sizePct = Math.min(j.judgment.position_size_pct || 30, 100);
        const leverage = Math.min(j.judgment.leverage || 5, 20);
        position = {
          direction: action,
          entry_price: price.close,
          size_usd: capital * sizePct / 100,
          leverage,
          stop_loss_pct: j.judgment.stop_loss_pct || 3,
          take_profit_pct: j.judgment.take_profit_pct || 6,
        };
      }
    }

    equityCurve.push({ date, capital: Math.round(capital * 100) / 100, position: position?.direction || 'FLAT' });
    if (capital > maxEquity) maxEquity = capital;
    const dd = (maxEquity - capital) / maxEquity * 100;
    if (dd > maxDrawdown) maxDrawdown = dd;
  }

  // 最終ポジションを強制クローズ
  if (position) {
    const lastPrice = prices[prices.length - 1].close;
    const pnlPct = position.direction === 'LONG'
      ? (lastPrice - position.entry_price) / position.entry_price
      : (position.entry_price - lastPrice) / position.entry_price;
    const pnl = pnlPct * position.size_usd * position.leverage;
    capital += pnl;
    trades.push({
      date: judgments[judgments.length - 1].date, type: 'FINAL_CLOSE', direction: position.direction,
      entry: position.entry_price, exit: lastPrice, pnl, leverage: position.leverage,
    });
  }

  return {
    initial_capital: 10000,
    final_capital: Math.round(capital * 100) / 100,
    total_return_pct: +((capital - 10000) / 10000 * 100).toFixed(2),
    max_drawdown_pct: +maxDrawdown.toFixed(2),
    total_trades: trades.length,
    winning_trades: trades.filter(t => t.pnl > 0).length,
    losing_trades: trades.filter(t => t.pnl <= 0).length,
    win_rate: trades.length > 0 ? +(trades.filter(t => t.pnl > 0).length / trades.length * 100).toFixed(1) : 0,
    avg_win: trades.filter(t => t.pnl > 0).length > 0 ? Math.round(trades.filter(t => t.pnl > 0).reduce((s, t) => s + t.pnl, 0) / trades.filter(t => t.pnl > 0).length) : 0,
    avg_loss: trades.filter(t => t.pnl <= 0).length > 0 ? Math.round(trades.filter(t => t.pnl <= 0).reduce((s, t) => s + t.pnl, 0) / trades.filter(t => t.pnl <= 0).length) : 0,
    profit_factor: trades.filter(t => t.pnl <= 0).reduce((s, t) => s + Math.abs(t.pnl), 0) > 0
      ? +(trades.filter(t => t.pnl > 0).reduce((s, t) => s + t.pnl, 0) / trades.filter(t => t.pnl <= 0).reduce((s, t) => s + Math.abs(t.pnl), 0)).toFixed(2) : Infinity,
    trades: trades.slice(-20), // 直近20トレード
    equity_monthly: equityCurve.filter((_, i) => i % 30 === 0), // 月次
  };
}

// === メイン ===
async function main() {
  const trader = process.argv[2] || 'smile_danjer';
  const startDay = parseInt(process.argv[3]) || 60; // 60日目から(テクニカルデータが必要)
  const step = parseInt(process.argv[4]) || 3;       // 3日ごとに判断(API呼び出し削減)

  console.log(`=== BTC AI Backtest: ${trader} ===`);
  console.log(`Period: ${daily[startDay].time.split('T')[0]} to ${daily[daily.length - 1].time.split('T')[0]}`);
  console.log(`Step: every ${step} days (${Math.ceil((daily.length - startDay) / step)} judgments)`);

  // トレーダーのツイートサマリー読み込み
  const analysisFile = path.join(__dirname, '..', 'btc-research',
    trader === 'smile_danjer' ? 'danjer_deep_analysis.md' : 'ronpochi_deep_analysis.md');
  let traderProfile = '', tweetsSummary = '';
  if (fs.existsSync(analysisFile)) {
    const content = fs.readFileSync(analysisFile, 'utf8');
    // 最初の3000文字をプロフィール、次の3000文字をサマリーに
    traderProfile = content.substring(0, 3000);
    tweetsSummary = content.substring(3000, 6000);
  }

  // 各日のAI判断を取得
  const judgments = [];
  const prices = [];
  let completed = 0;
  const totalJudgments = Math.ceil((daily.length - startDay) / step);

  for (let i = startDay; i < daily.length; i += step) {
    const marketContext = buildMarketContext(i);
    const judgment = await getAIJudgment(trader, traderProfile, tweetsSummary, marketContext);
    judgments.push({ date: marketContext.date, judgment });
    prices.push({ open: daily[i].open, high: daily[i].high, low: daily[i].low, close: daily[i].close });
    completed++;
    if (completed % 10 === 0) {
      process.stdout.write(`\r  AI Judgments: ${completed}/${totalJudgments}`);
    }
    await new Promise(r => setTimeout(r, DELAY));
  }

  console.log(`\n  All judgments complete.`);

  // バックテスト実行
  const result = runBacktest(judgments, prices);

  console.log(`\n=== Results: ${trader} ===`);
  console.log(`Initial: $${result.initial_capital}`);
  console.log(`Final:   $${result.final_capital}`);
  console.log(`Return:  ${result.total_return_pct}%`);
  console.log(`Max DD:  ${result.max_drawdown_pct}%`);
  console.log(`Trades:  ${result.total_trades} (Win: ${result.winning_trades}, Lose: ${result.losing_trades})`);
  console.log(`Win Rate: ${result.win_rate}%`);
  console.log(`Avg Win: $${result.avg_win}, Avg Loss: $${result.avg_loss}`);
  console.log(`Profit Factor: ${result.profit_factor}`);

  // 結果保存
  const outFile = path.join(__dirname, `backtest_${trader}_${new Date().toISOString().split('T')[0]}.json`);
  fs.writeFileSync(outFile, JSON.stringify({ trader, ...result, all_judgments: judgments }, null, 2));
  console.log(`\nSaved to: ${outFile}`);
}

main().catch(console.error);
