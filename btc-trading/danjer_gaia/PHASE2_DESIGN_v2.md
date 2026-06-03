# Phase 2 設計書 v3 — Round 30-33 取引所再選定反映

更新: 2026-06-04 (Round 33 3者合意、 戦略Z 改訂版 v4)

## v2 → v3 主要変更点 (Round 30-33 反映)

| # | 旧 (v2、 Bybit前提) | 新 (v3、 Hyperliquid主) | 出典 |
|---|---|---|---|
| 1 | Bybit主軸 + HL副 | **Hyperliquid主 + bitget副 (Phase 3後半から)** | Bybit日本撤退判明 |
| 2 | Day 15 即着手 | **Day 22 着手 (Phase 0 21日準備期追加)** | Wallet準備期 |
| 3 | Bybit testnet API key | **Hyperliquid Wallet (Ledger Nano X物理保管)** | DEX採用 |
| 4 | Bybit手数料 maker -0.025% / taker 0.075% | **Hyperliquid maker -0.001% (rebate) / taker 0.035%** | DEX手数料 |
| 5 | 取引手数料 月$1-5 | **月$0-2 (maker比率70%でリベート優勢)** | コスト節約 |
| 6 | R37-R42 | **+R70-R83 を追加 (Wallet/Bridge/出金遅延)** | DEX固有リスク |
| 7 | Phase 2月額 $52-136 | **Phase 2月額 $30-80 (-$30節約)** | Cobo MPC不採用 |

## 0. Phase 0 準備期 (Day -21 〜 -1、 3週間)

**新規追加 (Round 30-33)**: Hyperliquid Wallet 準備のため Phase 2 着手前に 3週間の準備期を設ける。

### Week 1 (Day -21〜-15、 ハードウェア調達)
- Ledger Nano X 公式ストア注文 ($150、 米国発送3-5日)
- Cryptosteel Capsule シードフレーズ金属保管プレート ($80)
- Wise アカウント開設 (JPY → USDC 国際送金用)

### Week 2 (Day -14〜-8、 Wallet初期化+送金経路)
- Ledger Nano X 初期化 + シードフレーズ金属保管
- Wise → USDC送金経路確立 ($50送金で動作確認)
- Hyperliquid Wallet 作成 + Ledger接続検証

### Week 3 (Day -7〜-1、 接続検証+設計)
- Hyperliquid testnet 接続検証
  - API endpoint: `https://api.hyperliquid-testnet.xyz`
  - WebSocket: `wss://api.hyperliquid-testnet.xyz/ws`
  - HyperEVM RPC: `https://rpc.hyperliquid-testnet.xyz/evm` (Chain ID 998)
  - ⚠️ testnet faucet利用には mainnet入金履歴が必要
- 紙トレ Hyperliquid テスト発注確認
- Tax-Engine USDC/JPY 換算ロジック設計 (取引時レート、 国税庁総平均法準拠)

**Phase 0 一括コスト**: 約35,000円 (Ledger + Cryptosteel)
**Shuji 作業時間**: 計4-5時間 (夜間+休日のみで完結)

### Wallet階層 (Phase 2では2段、 Phase 4+で3段)

```
[Phase 2-3 構成]
Ledger Cold Wallet (Shuji物理保管)
  ↓ 月1回 Hot Wallet 補充 (Shuji 5分作業)
MetaMask Hot Wallet (秘密鍵 GCP Secret Manager保管)
  ↓ Cloud Run から自動アクセス
Hyperliquid 運用残高
```

**Cobo MPC は Phase 4 Cap 1 ($25k) 到達後に検討** (Phase 2-3では月$99コストが運用規模に見合わない)。

## v1 からの主要変更点 (Round 22 反映、 v2時点)

| # | 旧 (v1) | 新 (v2) | 出典 |
|---|---|---|---|
| 1 | Day 31-45 カレンダー固定 | **ゲート式 (条件達成で移行)** | GPT |
| 2 | Cloud Run リクエスト時のみ | **Cloud Run Min Instances=1 + 5分 keep-alive必須** | Gemini |
| 3 | Stage 0 全件承認 | **デイリー承認制 (1日10件まとめて 3択)** | Gemini |
| 4 | Shadow 90日 | **Phase 2は 5-14日 / Phase 3判断は 30日** | GPT+Gemini |
| 5 | R34-R36 | **+R37〜R42 を追加** | GPT+Gemini |
| 6 | コスト $25-75 | **現実 $50-150** | GPT |
| 7 | Context Cache そのまま使う | **ハイブリッド (直近1ヶ月Cache + 過去4年 Vertex Vector Search)** | Gemini |
| 8 | Mark Price 共通 | **取引所毎 Mark Price を Fast Guard に個別配線** | Gemini R37 |

## 1. Phase 2 ロードマップ (ゲート式)

```
Day 15-30 (準備フェーズ、 連続15日):
├─ Day 15-20: 紙トレ + Shadow 実装 (Cloud Run化含む)
├─ Day 21-25: 紙トレ 5日連続実行
├─ Day 26-28: Shadow Model 並走、 Live rehearsal (実弾0、 注文取消のみ)
└─ Day 29-30: ゲートA判定 (Paper 50判断/20trade/事故0/Order Gate違反0)

Day 31+ (Live移行、 ゲート達成次第):
├─ Live Stage 0 (5日 + ゲートB): 実弾$15、 デイリー承認制
├─ Live Stage 1 (10日 + ゲートC): 最小自動 ($15-50、 レバ2x)
└─ Phase 3 移行 (Day 50頃想定、 ゲートD): Stage 2 自動運用
```

**ゲート条件** (3者合意):

| ゲート | 条件 |
|---|---|
| Gate A (Day 30) | Paper: 最低10稼働日 + 50判断 + 20 paper trade + 重大バグ0 + SL未設置0 + Order Gate違反0 + Shadow が本番より明確に悪くない |
| Gate B (Stage 0→1) | 5稼働日 + 全件Shuji承認 + 全ログ正常 + 通知遅延/誤通知0 + 市場レジーム3パターン (上昇/下降/横ばい) 経験 |
| Gate C (Stage 1→Phase 3) | 10稼働日 + 10実弾 + 自律L0のみ + 1トレ損失0.25%以内 + 日次DD<1.5% + Fast Guard誤作動0 + **Trade-EHR が紙トレ期間 noop加算後もプラス** |

## 2. Cache 自然死問題への対策 (Gemini R42)

**🚨 Gemini指摘**: Gemini Context Cache のデフォルトTTL=5分。 Cloud Run 15分間隔ステートレス呼び出しでは Cache再利用率=0% (毎回コールドスタート、 推論10-15秒+全課金)。

### Cloud Run アーキテクチャ修正

```
[Cloud Run: slow-brain-server]
├─ Min Instances = 1 (常時稼働、 月額 $5-10)
├─ Cron内蔵 (5分毎)
│  └─ keep_alive_ping() → Gemini に軽量ダミークエリ
│      (テキスト10トークン投入で Cache life 延長)
└─ External endpoint: /predict (Cloud Scheduler 15分毎呼び出し)
   └─ Cache再利用率99%維持
```

### Vertex AI Vector Search ハイブリッド (Day 30以降)

| 階層 | データ | 保存方法 | 用途 |
|---|---|---|---|
| Tier 1 (Cache常駐) | 直近1ヶ月の重要アンカーポスト (約500件) | Gemini Context Cache | 即時判断 |
| Tier 2 (Vector検索) | 過去4年の全投稿 + メタデータ (約14,000件) | Vertex AI Vector Search | 類似局面検索 (ms単位) |
| Tier 3 (BQ Storage) | 全投稿 (32,104件) | BQ btc_trading.danjer_post_master | 監査・統計用 |

**コスト**:
- Tier 1: Cache料金 $10-20/月
- Tier 2: Vector Search $20-40/月 (Day 30以降)
- Tier 3: BQ Storage $0-2/月

## 3. デイリー承認制 (Gemini指摘 承認疲れ R41対策)

### 旧 (v1): 1トレード毎承認 → 却下
### 新 (v2): デイリー承認制

```
朝7:00 (JST、 Shuji起床想定): 自動 Slack DM
========================================
📋 本日の発注候補 (10件)

[1] LONG BTCUSDT 0.0001 @ $XX,XXX
    Trade-EHR期待値: +0.005 / 損失上限: $0.04 (Equity 0.25%)
    danjer類似: 2024-03-XX (PF 2.1, win 70%)
    レジーム: storm_up / 危険度: 0.2

[2] WAIT (高ボラ低確信)
... (10件まで)

選択肢:
  ✅ 全部GO
  🎯 上位3件のみGO (Trade-EHR期待値 高順)
  ❌ 全部却下
========================================
```

- 1日1回の承認で済む
- 流れ作業承認も防ぐ (各候補に損失上限赤字表示)
- 承認画面短く、 ✅/🎯/❌ の3択のみ
- 却下も学習データとして利用 (Shadow Model がShujiさんの拒否パターンを学習)
- 緊急時 (L3/L4) のみ即時通知 (デイリーの外側)

### Stage 1 自律時の取り扱い
- L0 (Equity 0.25%以下、 レバ2x以下) → デイリー承認なしで自動実行
- L2 (Equity 0.5%以上 or レバ3x以上) → デイリー承認 (1日1回まとめて)
- L3/L4 → 即時通知 + 自動停止

## 4. R37-R42 追加 (Round 22 監査結果)

### Phase 2 必須対策

| # | リスク | 対策 |
|---|---|---|
| **R37** | APIキー漏洩・権限過大 | 出金権限なし / IP制限 / サブアカウント / Secret Manager / ローカル.envに本番キー禁止 / 90日定期ローテーション |
| **R38** | Cloud Run / GCP障害 | 異常時新規注文停止 / **取引所側SL必須 (Cloud死んでもSL残る設計)** / 緊急手動決済手順 |
| **R39** | 通知遅延・未達 | Slack+iPhone Push+メール 3系統並列 / L2承認通知確認ログ必須 / 通知未達なら自律停止 |
| **R40** | Paper過剰最適化 | paper約定保守的に / **paper約定価格は実Markより 0.05% 不利に設定** / Live rehearsalを Day 26-28 に挿入 |
| **R41** | 承認疲れ | デイリー承認制 (上記) / 高品質候補だけ通知 / 承認画面短く / 却下も学習データ |
| **R42** | Cache 自然死 (Gemini指摘) | Cloud Run Min Instances=1 / 5分 keep-alive ダミークエリ |
| **R37'** | 取引所間 Liquidation Cascade スプレッド (Gemini) | **各取引所マーク価格を個別 Fast Guard トリガー** (Hyperliquid Mark / bitget Mark 別々、 Phase 3後半から) |
| **R70** | Wallet秘密鍵管理ヒューマンエラー | Ledger Nano X + Cryptosteel 金属保管 + シードフレーズ複製禁止 |
| **R71** | Bitget FSA完全撤退リスク | 月次規制監視ジョブ + 撤退発表時 90日避難計画 |
| **R72** | Hyperliquid 流動性集中リスク | 板厚監視閾値 ($30M下回り → bitget自動切替) |
| **R75** | Hot Wallet サービス障害 | Cobo MPC は Phase 4以降のみ、 Phase 2-3 は Ledger単体 |
| **R76** | Hyperliquid 規制リスク (将来) | Phase 4+ bitget併用で規制リスク分散 |
| **R78** | Bridge ハック (累計$2B+) | Wise/Revolut直接USDC送金 (Bridge回避) |
| **R79** | Hyperliquid 出金 24-48h遅延 | Wallet残高上限 (Cap 2まで) + Cold保管主軸 |
| **R80** | USDC depeg (SVB事案で0.87下落例) | Phase 5+ で USDT併用検討 |
| **R81** | Phase 0 21日準備期延長 | 各ステップ3日バッファ、 28日まで許容 |
| **R82** | Hyperliquid 規約変更 | 月次規約監視ジョブ |
| **R83** | Service Account 秘密鍵 漏洩 | IAM制御 + IP制限 + 出金禁止権限分離 + Cloud Run専用 |

## 5. コスト見積もり v2 (現実版)

### 固定費 (常時稼働)
| サービス | 月額 |
|---|---|
| Cloud Run (slow-brain, Min Instance=1) | $5-10 |
| Cloud Run (fast-guard常駐 WebSocket) | $5-10 |
| Cloud Scheduler | $0 (5ジョブ無料) |
| Cloud Logging | $1-3 |
| Secret Manager | $0.06/secret/月 × 6 = $0.5 |
| BigQuery Storage | $2-5 |
| **固定費合計** | **$13-28** |

### 変動費
| サービス | 月額 |
|---|---|
| Gemini 3.1 Pro Context Cache | $10-20 |
| Gemini クエリ (15分毎) | $5-30 |
| Vertex AI Vector Search (Day 30+) | $20-40 |
| BigQuery query | $2-10 |
| Slack/通知 | $0 |
| Egress | $1-3 |
| **変動費合計** | **$38-103** |

### 取引手数料 (Stage 1から、 v3 Hyperliquid前提)
| | 月額 |
|---|---|
| Hyperliquid Maker -0.001% (rebate) / Taker 0.035% × 月10-30トレード | **$0-2 (maker比率70%でリベート優勢)** |

### Wallet関連 (Phase 2)
| | 月額 |
|---|---|
| Ledger Nano X | $0 (Phase 0で一括購入 $150、 月割なし) |
| Cobo MPC Lite | $0 (Phase 4 Cap 1以降のみ、 Phase 2では不採用) |

**Phase 2 月額合計 (v3 現実版): $30-80** (-$30 節約、 v2比)
**Phase 1 → Phase 2 移行差分: +$15-65**

Shujiさん予算 $135-400 に十分収まる。 Phase 3 拡大時で $50-120 想定。

## 6. 実装着手順 (Round 30-33 反映版、 v3)

### Phase 0 (Day -21 〜 -1、 Shuji準備期、 3週間)
| 順 | 作業 | 担当 | 推定 | 備考 |
|---|---|---|---|---|
| 0-1 | Ledger Nano X 購入 ($150) + Cryptosteel ($80) | Shujiさん | 5日 (発送) | 公式ストアから |
| 0-2 | Wise アカウント開設 + JPY→USDC送金経路 | Shujiさん | 2日 | $50で動作確認 |
| 0-3 | Hyperliquid Wallet 作成 + Ledger接続検証 | Shujiさん | 1日 | 夜間作業可能 |
| 0-4 | Hyperliquid testnet 接続検証 | Claude | 1日 | API endpoint動作確認 |
| 0-5 | Tax-Engine USDC/JPY 換算設計 | Claude | 0.5日 | 国税庁準拠 |

### Phase 2 (Day 22-52、 紙トレ→Live Stage 0/1)
| 順 | 作業 | 担当 | 推定 | 備考 |
|---|---|---|---|---|
| 1 | exchange/hyperliquid_client.py (公式SDK経由) + Mark Price WebSocket | Claude | 5-7日 | reduce-only stop |
| 2 | exchange/bitget_client.py (Phase 3副準備、 read-only) | Claude | 1日 | Phase 3後半に本格 |
| 3 | paper_trading/simulator.py + slippage保守的 + Hyperliquid手数料モデル | Claude | 1日 | R40対策、 maker rebate反映 |
| 4 | live/cloud_run_main.py + keep-alive cron | Claude | 1日 | R42対策 (実装済、 v3で取引所引数変更) |
| 5 | monitoring/slack_daily_approval.py | Claude | 1日 | R41対策 (実装済) |
| 6 | Phase 1 統合 Live Runner (local rehearsal) | Claude | 0.5日 | (実装済) |
| 7 | 紙トレ Day 22-32 実行 | 自動 | 10日 | |
| 8 | Shadow Model 並走 Day 33-35 | 自動 | 3日 | |
| 9 | Gate A 判定会議 (3者) | 全員 | 1時間 | |
| 10 | Live Stage 0 (Hyperliquid本番、 $15入金、 デイリー承認) | Shuji+Claude | 5日 | Ledger→MetaMask Hot補充 |
| 11 | Gate B 判定 + Stage 1 移行 | 全員 | - | |

### Phase 0 Shuji作業時間試算
- Ledger 注文〜受け取り: **配達中の待ち時間で発注、 受け取りは在宅時** (実作業 30分)
- Ledger 初期化 + Cryptosteel刻印: **夜間2時間** (1回)
- Wise + Hyperliquid Wallet 設定: **夜間1.5時間** (2回に分割可)
- 動作確認テスト送金: **夜間30分** (Claude併走サポート)
- **合計 Shuji作業時間: 4-5時間** (3週間の中で分散可能)

## 7. Round 23 Claude結論

GPT+Gemini の監査を全面採用。 v2 で重要修正:
- ゲート式移行 (カレンダー固定撤回)
- Cloud Run 常時起動 + keep-alive必須 (Cache自然死防止)
- デイリー承認制 (Shujiさん精神保護)
- R37-R42 全部設計に組み込み
- コスト現実 $52-136/月

**実装着手 GO 判定**:
- ✅ ゲート条件明確
- ✅ Cache再利用率99%維持の設計
- ✅ Shujiさん承認疲れ対策
- ✅ R37-R42 防衛策

Round 24 で GPT/Gemini に最終承認求めるか、 Shujiさんに直接 v2 を見せて 実装着手判定もらうか、 のどちらか。

Claude推奨: **Shujiさんに v2 を見せて GO判定 → 即実装着手**。
