# Project danjer-GAIA

3者会議 v3 (Round 0-28、 logs/round_table_v3.md) で確定した BTC自動売買 AI システム。

> **コードネーム**: Project danjer-GAIA
> **副題**: danjerを初期師匠にした弟子AI
> **ゴール**: 投資効率 (時間軸に対して利益が大きいこと) 最大化

## 全体俯瞰

```
┌────────────────────────────────────────────────────────────────────┐
│ Slow Brain (Gemini 3.1 Pro Context Cache、 15分間隔)              │
│   ↓ Stance JSON (9項目: direction/confidence/risk/TTL/lev/SL/...) │
├────────────────────────────────────────────────────────────────────┤
│ Fast Guard (ルールベース、 ms単位)                                │
│   ├─ ブレーキのみ独自判断 (アクセル禁止)                          │
│   └─ Slow Brain許可外でも止める: SL未/清算距離/DD/急変/API異常   │
├────────────────────────────────────────────────────────────────────┤
│ Risk Engine (静的検問所)                                          │
│   ├─ Trade-EHR / MaxDD / NoStop / Slippage / OverLeverage 減算   │
│   └─ noop機会損失 (条件付き発動、 強制エントリーbug防止)         │
├────────────────────────────────────────────────────────────────────┤
│ Order Gate (発注前 6ステップ検問)                                 │
│   1. Trade Intent  2. Risk  3. Exchange  4. Cost  5. Pattern     │
│   6. Explainability → APPROVE/REJECT                              │
├────────────────────────────────────────────────────────────────────┤
│ Exchange (Hyperliquid主 / bitget副 / GMOコイン Tax / paper)       │
│   └─ reduce_only stop 同時発注 + Mark Price 取引所別配線         │
└────────────────────────────────────────────────────────────────────┘

danjer DNA Vector Search (32,104件、 99.2%読解済):
  ├─ GPT-4.1-mini 読解 (17,636件、 Session 36-45)
  ├─ Claude Haiku 4.5 読解 (17,636件、 Session 45)
  ├─ Anthropic Batch 新規読解 (14,200件、 Session今回)
  └─ Embedding 18,437件 × 3072次元 (gemini-embedding-001)
```

## モジュール構成

```
btc-trading/danjer_gaia/
├── schemas.py           # Trade/TradingPeriod/GuardConfig/NoopConfig dataclass
├── metrics.py           # Trade-EHR/MA30/noop_penalty/period_summary
├── guards.py            # 6種減算ペナルティ (Liquidation/MaxDD/NoStop/Slippage/OverLev/Overtrade)
├── rewards.py           # episode_reward (Trade-EHR + noop + Σguard)
├── regime.py            # レジーム判定 (ATR×Slope 2x2、 動的閾値)
├── stance.py            # Slow Brain Stance JSON (9項目)+decay
├── ttl_manager.py       # TTL 15分+5分grace+halt (R33 R42対策)
├── fast_guard.py        # 衝突マトリクス (R30 ブレーキのみ)
├── order_gate.py        # 6ステップ検問
├── morning_summary.py   # 朝サマリー雛形 (Markdown+JSON)
│
├── exchange/
│   ├── base.py             # ExchangeBase 抽象 (Hyperliquid/bitget/GMO/paper共通IF)
│   ├── paper_client.py     # シミュレータ (R40 保守的slippage、 Hyperliquid手数料モデル)
│   ├── hyperliquid_client.py  # Phase 2 主取引所 (公式Python SDK、 Round 30-33で選定)
│   ├── bitget_client.py    # Phase 3後半-副取引所 (CCXT経由、 障害退避+板厚補完)
│   ├── gmocoin_client.py   # Phase 5+ Tax-Engine連携 (確定申告CSV)
│   └── exchange_router.py  # Phase 4 動的切替 (板厚・障害ステータスベース)
│
├── paper_trading/
│   ├── slippage_model.py
│   └── simulator.py     # Phase 1全モジュール統合 Live Runner
│
├── monitoring/
│   └── slack_daily_approval.py  # デイリー承認制 3択 (R41対策)
│
├── live/
│   ├── keep_alive.py    # R42対策 (Cache自然死防止)
│   ├── cloud_run_main.py
│   ├── Dockerfile
│   └── requirements.txt
│
├── data_pipeline.py     # 既存読解+SQLite+市場context+リターン 統合
├── embed_posts.py       # Gemini Embedding (gemini-embedding-001)
├── similar_search.py    # cosine top-K + 集計 (PF/win_rate)
│
└── batch_unread_submit_anthropic.py  # Anthropic Batch API 投入
```

## 設計書

| Phase | 文書 | 概要 |
|---|---|---|
| Phase 1 | (議事録 Round 0-20) | 評価基盤+DNA移植 (Day 1-14) ✅実装143テスト |
| **Phase 2 v2** | [PHASE2_DESIGN_v2.md](./PHASE2_DESIGN_v2.md) | Stage 0/1 BTC \$15-50、 2x ✅174テスト |
| **Phase 3 v2** | [PHASE3_DESIGN_v2.md](./PHASE3_DESIGN_v2.md) | BTC単体再現性検証 (Day 46-160) |
| **Phase 4 v2** | [PHASE4_DESIGN_v2.md](./PHASE4_DESIGN_v2.md) | マルチアセット 3レーン制 (Day 161-240) |
| **Phase 5+ v2** | [PHASE5_DESIGN_v2.md](./PHASE5_DESIGN_v2.md) | 守りの永続 (Day 240+) |

議事録: [round_table_v3.md](../../logs/round_table_v3.md) — **Round 0-33、 約4,000行**

### 取引所構成 (Round 30-37 確定、 戦略Z 改訂版 v7)

| 役割 | 取引所 | レバ | Phase | 取引コスト |
|---|---|---|---|---|
| **主** | **Hyperliquid (DEX)** | 50x可、 Phase 2で2x / Phase 3で3x | Phase 2 から全期間 | maker -0.001% rebate |
| **副並走** | **Exness MT5 + taritari** | 400x (3xのみ使用) | Phase 4 Cap 1から | スプ-CB 45.75% |
| **副障害退避** | **bitget** | 125x可 | Phase 3後半 (Day 100前後) から | maker 0.02% / taker 0.06% |
| Tax用 | GMOコイン | 2x | Phase 5+ Cap 2 (確定申告連携) | - |
| Vacation用 | bitFlyer Lightning | 2x | Phase 5+ (緊急退避) | - |
| **新興DEX 検証** | **Lighter (zkSync)** | (未確認) | Phase 5+ Cap 3 paper先行 12ヶ月 → Cap 5 Live並走候補 | retail fee zero |

**選定理由**: Bybit日本撤退判明 → 3者会議Round 30-37 で **30+候補網羅評価** → DEX (規制リスクゼロ + 倒産リスクゼロ + maker rebate) + 既登録Exness のtaritari CB (年$22k Cap 5想定)。 Phase 0 (21日準備期) で Ledger Nano X + Wise USDC送金経路確立。 FXGT は管理コスト視点で不採用 (Shuji判断、 Round 37)。

## 動作確認 (Day 7-8 類似検索)

```bash
$ python3 btc-trading/danjer_gaia/similar_search.py "BTC急騰OI急増FR高い過熱感" 5

[1] sim=0.835 | OI激増! これは流石に怖いやつw
    reasoning: 「OI激増」に注目。 BTC約121,500ドル横ばい...
    ret_4h=+21.7% ret_1d=-7.3% ret_7d=-11.1%

Aggregate: {win_rate_1d: 0.50, PF: 0.71, mean_ret_4h: +55%}
→ 「過熱感クエリ」 では danjer 警戒姿勢、 慎重対応推奨
```

## テスト

```bash
cd btc-trading
python3 -m unittest discover -s danjer_gaia
# Ran 174 tests in 0.030s — OK
```

## データ統合状況

| | 件数 | カバー率 |
|---|---|---|
| smile_danjer 全投稿 (SQLite) | 32,104件 | 100% |
| 読解済 (GPT+Claude+Anthropic) | 31,836件 | **99.2%** |
| Embedding (投資判断のみ) | 18,437件 | 投資判断ポストのみ |

## 投資効率指標: Trade-EHR

```
Trade-EHR = NetProfit / (max(AvgEquity, ε) × max(ElapsedHours, ε))
```
- 待機時間込み (前トレード終了→今回終了の全経過時間)
- 分母ガード (R42 Cache自然死 と別、 数学的なゼロ除算防止)
- 集計: 直近30トレードの移動平均 (MA30)
- ガード減算 (Liquidation/MaxDD/NoStop/Slippage/OverLeverage)
- 加算ベース (Gemini Round 6 指摘の掛け算回避、 学習安定化)

## 段階的投入 (Phase 2 v2)

| Stage | 期間 | 元手 | レバ | 介入 |
|---|---|---|---|---|
| 紙トレ | Day 15-30 | $0 | 〜2x | 観察 |
| Live Stage 0 | Day 31-35 | $15 | 1x | Shujiさん全件承認 |
| Live Stage 1 | Day 36-45 | $15-50 | 2x | L2のみ承認 |
| Live Stage 2 | Day 46+ | $150-2,250 | 3x | デイリー承認 |

## 主要リスク (R1-R69、 全69件は議事録 Round 10 参照)

カテゴリ別:
- **データ品質**: R11/R12/R44
- **過学習**: R2/R46/R57
- **取引所事故**: R4/R37/R47/R55/R64
- **Black Swan**: R5/R32
- **法規制**: R6/R17/R62
- **Sycophancy**: R7/R52
- **説明可能性**: R8/R15/R53
- **API/Cache**: R21/R22/R42/R59/R69
- **承認疲れ**: R36/R41
- **マルチアセット**: R47/R55/R61

## 月コスト見積もり (Round 30-33 v3 反映、 -$20-50/月 節約)

| Phase | 月額 v2 (Bybit前提) | 月額 v3 (Hyperliquid前提) | 差分 |
|---|---|---|---|
| Phase 1 (Day 1-14) | $0-7 | $0-7 | 0 |
| **Phase 2 v3 (Day 22-52)** | $52-136 | **$30-80** | -$30 |
| **Phase 3 v3 (Day 53-167)** | $71-170 | **$50-120** | -$30 |
| **Phase 4 v3 (Day 168-247)** | $180-350 | **$150-300** | -$50 |
| **Phase 5+ v3 (Day 247+)** | $155-400 | **$140-380 固定上限** | -$20 |

**節約効果**: maker rebate + Cobo MPC不採用 (Phase 2-3) で年 $240-600 (約3-9万円) 節約。

## ハードウェア・サービス購入物 (Phase 0、 Round 30-33 反映)

| 項目 | 価格 | 用途 | 購入タイミング |
|---|---|---|---|
| Ledger Nano X | 約23,000円 | Cold Wallet (秘密鍵物理保管) | Phase 0 Day -21 |
| Cryptosteel Capsule | 約12,000円 | シードフレーズ金属保管 | Phase 0 Day -21 |
| Wise アカウント | 無料 (送金時0.5%) | JPY→USDC直接送金 | Phase 0 Day -21 |
| Cobo MPC Lite | $99/月 | Hot Wallet MPC管理 | **Phase 4 Cap 1到達後** |

**Phase 2 着手前 一括コスト: 約35,000円**

## 3者会議の貢献

- **GPT (司会+整合性監査)**: Sycophancy検出、 数値定義保持、 「投資効率最大化」原文軸維持、 Phase 5+ 哲学転換 「拡大ではなく壊れずに続ける」
- **Gemini (技術深掘り)**: Cache自然死問題 (R42)、 Lost in the Middle、 GAIA-Triad、 1脳25肉体、 IQN+DRQN、 Tax-Engine、 Bandit出金
- **Claude (発言+実装+議事録保存)**: Trade-EHR定義、 デッドロック解決 (TTL+階層化)、 paper_client、 PaperSimulator、 174テスト

## ライセンス・免責

個人運用・内部利用前提。 公開資料・再配布禁止 (R17 SNSデータ権利)。
投資は自己責任、 過去のパフォーマンスは将来の利益を保証しない。
