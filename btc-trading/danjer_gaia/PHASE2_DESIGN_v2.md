# Phase 2 設計書 v2 — Round 22 監査反映版

更新: 2026-06-03 (Round 23 Claude実装案、 GPT+Gemini 監査全反映)

## v1 からの主要変更点 (Round 22 反映)

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
| **R37'** | 取引所間 Liquidation Cascade スプレッド (Gemini) | **各取引所マーク価格を個別 Fast Guard トリガー** (Bybit Mark / HL Mark 別々) |

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

### 取引手数料 (Stage 1から)
| | 月額 |
|---|---|
| Bybit Maker -0.025% / Taker 0.075% × 月10-30トレード | $1-5 |

**Phase 2 月額合計 (v2 現実版): $52-136**
**Phase 1 → Phase 2 移行差分: +$30-100**

Shujiさん予算 $135-400 に収まる。 Phase 3 拡大時で $100-200 想定。

## 6. 実装着手順 (Round 22 反映版)

| 順 | 作業 | 担当 | 推定 | 備考 |
|---|---|---|---|---|
| 1 | Bybit testnet API key取得 | Shujiさん | 30min | サブアカウント+IP制限 |
| 2 | exchange/bybit_client.py (testnet) + Mark Price WebSocket | Claude | 1日 | reduce-only stop |
| 3 | exchange/hl_client.py (read-only副) | Claude | 0.5日 | Bybit/HL Mark価格差監視のみ |
| 4 | paper_trading/simulator.py + slippage保守的 | Claude | 1日 | R40対策 |
| 5 | live/cloud_run_main.py + keep-alive cron | Claude | 1日 | R42対策 |
| 6 | monitoring/slack_daily_approval.py | Claude | 1日 | R41対策 (デイリー承認) |
| 7 | Phase 1 統合 Live Runner (local rehearsal) | Claude | 0.5日 | |
| 8 | 紙トレ Day 21-25 実行 | 自動 | 5日 | |
| 9 | Shadow Model 並走 Day 26-28 | 自動 | 3日 | |
| 10 | Gate A 判定会議 (3者) | 全員 | 1時間 | |
| 11 | Live Stage 0 (Bybit本番、 $15入金、 デイリー承認) | Shuji+Claude | 5日 | |
| 12 | Gate B 判定 + Stage 1 移行 | 全員 | - | |

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
