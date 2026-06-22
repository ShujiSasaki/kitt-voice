# danjerクローンAI「投資効率最大化ゲーム」設計議論

セッション46 (2026-06-02) Claude × GPT-5.5

## 議題
Shujiさんの新方針:「danjerクローンAIにBTC市場で投資効率最大化ゲームをやらせる」が実現可能か、徹底議論。

---

## 議論経緯

- Round 1: Claudeから論点10個提示 → GPTが論点1-3を深く回答
- Round 2: Claudeが異論4つ+追加論点6つ → GPTがアーキテクチャ全体像と30日MVPを回答
- Round 3: 実装具体・既存資産・90日プランで詰めたかったが、**GPT-5.5 APIクォータ切れで中断**

---

## 合意の核 (Round 1-2 で収束)

### 1. アプローチ再定義

| Shujiさん原案 | GPTの再定義(Claude同意) |
|------------|----------------------|
| 右側予測AI | 不確実性付きシナリオ予測+リスク制約エンジン |
| 角度に応じてレバレッジ調整 | first-passage probability + fractional Kelly + ハードキャップ |
| AIが自ら成長 | 仮説生成・検証・昇格プロセスを自動化 |
| danjerが教科書 | RAG事前知識(weak prior)、正解ラベルではない |

**核心の再定義**: 「成長するAI=本番ポリシーが勝手に変わるAI」ではなく「仮説生成・検証・昇格プロセスを自動化するAI」。これは Shujiさんが嫌うbot化と「成長」のジレンマを解く鍵。

### 2. 全体アーキテクチャ

```
[Data Ingestion(OHLCV+OI+FR+Liq+板+Macro+danjer)]
   ↓
[Feature Store(versioned)]
   ↓
[Scenario Engine: DSL + Particle Filter]   ← Shuji構想の中核
   ↓
[Predictive Models(LightGBM/Quantile/Survival): P(TP before SL), 期待R分布, MAE/MFE]
   ↓
[Risk Engine(fractional Kelly + ハード制約): 最終決定者]
   ↓
[Execution Engine(post-only/IOC/reduce-only/idempotent)]
   ↓
[Monitoring / Replay Harness / Policy Version Log]
                ↑
[LLM Research Agent: 仮説生成・backtest・promotion gate]
```

### 3. Scenario DSL(GPTの強力な提案)

Shujiの「右側を絵として描く」を機械可読に落とす:
```json
{
  "scenario_id": "S1_breakout_continuation",
  "direction": "long",
  "timeframe": "15m",
  "entry_zone": [101200, 101800],
  "invalidation": {
    "price_level": 100650,
    "structure": ["lower_high_after_breakout", "volume_fade_on_push", "failed_reclaim_vwap"],
    "max_bars_without_progress": 6
  },
  "milestones": [
    {"level": 102500, "action": "move_stop_to_breakeven"},
    {"level": 103800, "action": "trail_stop_under_15m_higher_low"}
  ],
  "expected_path": {"max_adverse_excursion": 0.004, "min_progress_per_n_bars": 0.002},
  "initial_weight": 0.32
}
```

**stop ≠ invalidation を分離**: 価格stopに到達してなくても構造破綻で撤退(これがShujiの「思っていた展開と違ったら降りる」の実装)。

### 4. Particle Filter on Scenario Space

複数シナリオを並走させ、観測ごとに尤度を更新:
```
S1: breakout continuation  0.42 → 0.61
S2: bull trap reversal      0.28 → 0.15
S3: range continuation      0.20 → 0.18
S4: liquidation wick        0.10 → 0.06
```
閾値以下になったらサイズ縮小or撤退。

### 5. LLMの役割厳格化

**LLMがやってよい**:
- シナリオ候補の生成(自由文ではなく Scenario DSL JSON 強制)
- danjer風の言語化、reasoning trace
- 過去類似局面の要約、failure clustering
- 自然言語trade log

**LLMがやってはいけない**:
- 直接の発注判断
- レバレッジ決定の最終権限
- 未検証シナリオの即時採用

**役割分担**: `LLM = scenario proposer / 数値モデル = likelihood updater / risk engine = final decision maker`

### 6. Vision-LLM の使い方

**ライブ主判断は反対**(再現性なし、バックテスト不能、数値精度弱い)。

**使ってよい用途**:
- danjer画像の構造化(timeframe/水平線/波動カウント/invalidation level抽出)
- 弱教師ラベル作成
- 人間レビュー補助(RAG表示)
- 数値特徴量化したセカンドオピニオン(15分/1時間ごと、固定JSON出力、リスク側のmonotone制約のみ)

### 7. 報酬設計

```
maximize: expected log wealth growth
subject to(ハード制約):
  max DD <= D_max
  daily loss <= L_day
  per-trade loss <= L_trade
  liquidation probability <= ε
  leverage <= L_max(0.25 Kelly以下)
  position concentration <= C_max
  CVaR_95/99 制約
```

**「投資効率=利益/時間」の罠**: 単純最大化は高頻度・高レバ・薄edge連打に寄る。
**正しい指標**: CAGR/MaxDD, log wealth growth, 破産確率, CVaR を併用。Funding-adjusted return 必須。

### 8. 特徴量の段階導入

```
Phase 1: OHLCV multi-TF + perp固有(OI/FR/Basis/Liq/CVD) + calendar
Phase 2: macro/cross-asset(rolling correlation)
Phase 3: on-chain(レジーム制御用、直接シグナルではない)
Phase 4: danjer/X sentiment(scenario tag生成)
Phase 5: chart vision(最後)
```

**オンライン特徴選択は初期NG**(短期偶然相関に飛びつく)。代わりに shadow mode → 一定期間勝てば昇格。

### 9. RL は本番直結NG

- Online RL fine-tune は反対
- やるなら Offline RL(IQL/CQL/Decision Transformer)
- Decision Transformer の condition は「目標時給」ではなく「target_vol/max_dd/max_turnover」
- 行動空間は連続レバ自由ではなく離散化(side ∈ {long, short, flat}, risk_per_trade ∈ {0.25%, 0.5%, 1%}, stop ∈ {1ATR, 1.5ATR, 2ATR}, target ∈ {1R, 1.5R, 2R, 3R}, max_holding ∈ {4h, 1d, 3d})

### 10. 失敗安全装置 (Circuit Breaker 完全リスト)

- PnL系: 日次/週次/月次/連続損失/maxDD超過で停止
- ポジション系: 最大notional/leverage/数, liquidation距離不足で強制縮小
- 注文系: duplicate/orphan/cancel失敗/conditional未設置で停止
- データ系: stale data/WS切断/REST-WS乖離/異常スパイクで停止
- 市場異常系: Nσ変動/spread急拡大/板厚急減/funding急変/Liq cascade/major event window で禁止
- システム系: rate limit接近/latency悪化/clock sync異常で停止
- 人間系: 手動kill switch、復帰は人間承認
- **取引所側に必ず stop order を残す**(ローカルbotが落ちても防御注文)

### 11. 取引所選定

- 第一候補: **Bybit or OKX**(API/流動性/UIバランス良)
- 第二候補: **Hyperliquid**(DEXだがbridge/validator/oracle risk あり)
- 研究用データ: Binance も参照
- 日本居住者は法務・規制要確認
- API keyは出金不可+IP制限+サブアカウント+bot専用口座

### 12. Sim2Real Gap 対策

- shadow trading 3ヶ月以上、最低 trade数 100-300件
- 約定モデル悲観化(spread+fee+slippage+latency+partial fill)
- 実板データ蓄積(L2 book replay 用)
- 小額本番で約定誤差測定 → sim を補正

### 13. 「成長するAI」と再現性の両立

GPT追加提案:
1. **Champion-Challenger Pattern**(現役+候補並走)
2. **Policy Versioning**(全判断に model_hash, feature_version, prompt_version, risk_config_version, data_snapshot_id)
3. **Immutable Decision Log**(append-only、エントリーしなかった理由も保存)
4. **Replay Harness**(過去任意時点で同じ判断を完全再現可能)
5. **Canary Deployment**(shadow→1%→5%→20%→昇格)
6. **Natural Language Log は単独で監査証跡にしない**(数値とセット)

---

## 30日MVP (GPT提示、Claude同意)

1. **取引対象を BTCUSDT perp 1つに絞る**(複数銘柄やらない)
2. **データ収集基盤**(OHLCV+funding+OI+trades+板, SQLiteで開始)
3. **簡易バックテスター**(fee/slippage/funding/latency入り)
4. **TP/SL first-passage label 生成**(各時点で先にTP到達したかSL到達したか)
5. **ベースラインモデル**(LightGBM, P(TP before SL) + expected R + MAE/MFE quantile)
6. **Risk Engine v0**(max loss/leverage/Kelly cap, モデルが強気でも拒否できる構造)
7. **Scenario DSL v0**(LLM以前にJSONでシナリオ表現できる土台)
8. **Shadow trading logger**(実注文なし、判断理由付き)
9. **danjer corpus 構造化開始**(scenario/invalidation/target/tag/outcome)
10. **毎日レビュー用レポート**(シグナル/期待値/実現/校正ズレ/失敗パターン/breaker発動)

---

## GPTの最後の本音(Round 2 締め)

> Shujiさんが今やるべきなのは、いきなり"danjerの脳を再現したAIトレーダー"を作ることではない。
>
> 最初に作るべきは:
> 1. データを正しく集める
> 2. 過去検証できる
> 3. シナリオを構造化できる
> 4. 期待値を出せる
> 5. リスクで止められる
> 6. 判断ログを残せる
>
> この土台。その上で danjer RAG / VLMセカンドオピニオン / Scenario Particle Filter / MoE / LLM Strategy Proposer / RL を順番に足す。
>
> 逆に、最初からLLM/VLM/RLを主役にすると、ほぼ確実に「説明は上手いが金は減るAI」になる。

---

## Round 3 で未消化の論点(GPTクォータ切れ)

1. Scenario DSL の semantic grounding(述語辞書 vs LLM都度判定 vs Hybrid)
2. Particle Filter の尤度計算具体実装(ルールベース/学習ベース/LLM-as-Likelihood)
3. LLM Research Agent の具体実装(Claude Code Sub-Agents活用)
4. danjer corpus 5万件の Vision-LLM 構造化のコストとアプローチ
5. 既存資産との接続(BQ/ccxt MCP/sqlite-btc-market/x tweets DB/tradingview MCP)
6. 90日プラン詳細添削
7. 残論点8-10(成長AI再現性・レバレッジ管理・danjer前検証)の最終回答
8. 「3年後にどこまで行けるかの正直予測」

---

## 結論

**Shujiさんの「投資効率最大化ゲーム」アプローチは、技術的に実現可能。ただし、原案そのままではなく以下の翻訳が必要**:

1. 「右側予測」→ Scenario DSL + Particle Filter
2. 「角度でレバ」→ first-passage probability + fractional Kelly + ハードキャップ
3. 「成長するAI」→ 仮説生成・検証・昇格プロセスの自動化(ポリシーが勝手に変わるAIではない)
4. 「danjerを教科書」→ RAG事前知識(weak prior)、正解ラベルではない
5. 「全特徴量投入」→ 段階導入(OHLCV+perp固有から)
6. 「Vision-LLMで右側読む」→ セカンドオピニオン+danjer画像構造化のみ

最大の警告: 最初からLLM/VLM/RLを主役にすると「説明は上手いが金は減るAI」になる。土台(データ・backtest・scenario・期待値・risk・log)を先に作る。
