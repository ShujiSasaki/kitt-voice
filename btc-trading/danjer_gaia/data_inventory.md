# Data Inventory — Day 3-4 BQ棚卸し結果

実施日: 2026-06-03

## 🔥 重要な訂正

3者会議で「49,667件」と推定していた数は **誤り**。 実態:
- **smile_danjer (= danjer氏 単独): 32,119件**
- **全トレーダー合計 (8アカウント): 213,469件**

Shujiさんの「もっとあったような」が正確でした。

## 既存データ全体図

### A. BigQuery (`gen-lang-client-0549297663:btc_trading`)

| テーブル | 件数 | 期間 | 内容 |
|---|---|---|---|
| `btc_klines` | 10,395 | 2026-05-07〜05-20 (13日) | OHLCV 1d/1h/4h × 各3,465件 |
| `btc_snapshots` | 3,465 | 同 | リッチ: 価格 + OI + Funding + 板深度Top5/20 + 清算USD |
| `btc_orderbook` | 3,465 | 同 | bids/asks JSON |
| `btc_judgments` | 3,301 | - | **既存AI判断履歴** (trader/action/dir/conf/lev/SL/TP/reasoning) |
| `btc_liquidations` | **0** | - | 空 (清算は btc_snapshots に集約) |

期間が 13日 だけ。 長期データなし → Phase 1 後半で過去2年分追加収集が必要。

### B. SQLite (`btc-trading/x_tweets.db`, 131MB)

#### B-1. ツイート系

| テーブル | 件数 | 内容 |
|---|---|---|
| `tweets` | **213,469** | 全アカウント、 8カラム (text/created_at/screen_name/media_json/raw_json 等) |
| `discovered_ids` | 49,739 | 発見済み ID キャッシュ |
| `media_files` | 6,279 | 画像ローカルパスとSHA256 |

**アカウント別件数:**
| screen_name | tweets | 備考 |
|---|---|---|
| `_Checkmatey_` | 49,219 | (オンチェーン分析) |
| `BobLoukas` | 41,646 | (サイクル理論) |
| `PeterLBrandt` | 38,389 | (TA老舗) |
| **`smile_danjer`** | **32,119** | **教科書本人** |
| `LynAldenContact` | 30,996 | (マクロ) |
| `4HpO4Q9Dz3CWkhV` | 17,444 | (別アカ) |
| `CryptoHayes` | 3,656 | |

#### B-2. 価格・市場データ (SQLite既存)

| テーブル | 件数 | 内容 |
|---|---|---|
| `market_btc_1d` | 3,197 | 日足 OHLCV |
| `market_btc_1h` | 76,589 | **1時間足 OHLCV — 多量・長期** |
| `market_btc_4h` | 19,164 | 4時間足 OHLCV |

#### B-3. 突合済み — ⭐ 重要資産

| テーブル | 件数 | 内容 |
|---|---|---|
| **`tweet_market`** | **194,135** | **ツイート × 投稿後リターン (4h/12h/1d/2d/3d/7d/30d/90d) すでに計算済** |

→ Phase 1.1 で v3 DNA outcomes テーブルとしてそのまま流用可能。 GeminiクエリでLLM分類するだけで「投資判断ポストのみ常駐」が即実現。

#### B-4. 既存 danjer 分析 (1件ずつ)

- `danjer_full_analysis`: 全件分析 JSON 1レコード
- `danjer_image_analysis`: 画像分析 JSON 1レコード
- `danjer_method_summary`: 手法サマリー (layer_system/entry_rules/exit_rules/risk_mgmt/timeframes/indicators/cycle_theory/anomalies/chart_patterns 等)

→ Phase 1.2 Slow Brain Context Cache の初期プロンプトに直接投入可能。

## v3用 テーブル設計案 (BQ btc_trading 拡張)

Phase 1 着手時の DDL:

```sql
-- danjer 投稿マスタ (SQLite tweetsをBQ移行)
CREATE TABLE `gen-lang-client-0549297663.btc_trading.danjer_post_master` (
  tweet_id STRING NOT NULL,
  screen_name STRING NOT NULL,
  created_at TIMESTAMP NOT NULL,
  full_text STRING,
  media_json STRING,
  raw_json STRING,
  is_retweet INT64,
  is_quote INT64
)
PARTITION BY DATE(created_at)
CLUSTER BY screen_name;

-- 投資判断分類 (Day 5-6 で LLM分類)
CREATE TABLE `gen-lang-client-0549297663.btc_trading.danjer_post_classification` (
  tweet_id STRING NOT NULL,
  is_trading_decision BOOL,  -- 投資判断関連 yes/no
  category STRING,            -- 'entry_signal'/'exit'/'warning'/'cycle_view'/'macro'/'chat' 等
  confidence FLOAT64,
  classified_by STRING,       -- 'gemini-3.1-pro'
  classified_at TIMESTAMP
);

-- アウトカム (tweet_market から移行)
CREATE TABLE `gen-lang-client-0549297663.btc_trading.danjer_post_outcomes` (
  tweet_id STRING NOT NULL,
  ret_4h FLOAT64, ret_12h FLOAT64, ret_1d FLOAT64,
  ret_2d FLOAT64, ret_3d FLOAT64, ret_7d FLOAT64,
  ret_30d FLOAT64, ret_90d FLOAT64,
  mfe_72h FLOAT64,  -- Max Favorable Excursion (新規計算)
  mae_72h FLOAT64   -- Max Adverse Excursion
);

-- 埋め込み (Day 5-6 で Embedding API実行)
CREATE TABLE `gen-lang-client-0549297663.btc_trading.danjer_post_embeddings` (
  tweet_id STRING NOT NULL,
  text_embedding ARRAY<FLOAT64>,   -- text-embedding-004 (768dim)
  market_context_embedding ARRAY<FLOAT64>,
  combined_embedding ARRAY<FLOAT64>
);

-- クラスタ (Day 7-8 で類似局面検索)
CREATE TABLE `gen-lang-client-0549297663.btc_trading.danjer_clusters` (
  cluster_id INT64,
  representative_tweet_id STRING,
  typical_regime STRING,
  historical_pf FLOAT64,
  historical_calmar FLOAT64,
  member_tweet_ids ARRAY<STRING>,
  notes STRING
);
```

## 不足データ一覧

| 種別 | 期間 | 必要性 |
|---|---|---|
| BTC 1分足 OHLCV | 過去2年 | 高 (Fast Guard用、 ms-1分単位判断) |
| BTC OI/FR/清算 長期 | 過去1年 | 高 (レジーム判定の特徴量) |
| BTC LS比 (Top trader比) | 過去1年 | 中 |
| 取引所毎 板深度履歴 | 過去6ヶ月 | 中 (流動性チェック用) |

→ Phase 1.2 後半 (Day 9-11以降) に追加収集スクリプト着手

## v3 で活用可能な既存資産 (リサイクル)

✅ **`tweet_market` (194,135件)** → DNA outcomes として即流用
✅ **`market_btc_1h` (76,589件)** → 中期レジーム判定の特徴量に流用
✅ **`btc_snapshots` (3,465件、 13日)** → 直近13日の OI/FR/板 を Phase 1.1 検証データに使う
✅ **`btc_judgments` (3,301件)** → 既存AI判断履歴、 v3 でも比較ベンチに使える
✅ **`danjer_full_analysis` / `danjer_method_summary`** → Slow Brain 初期プロンプトに投入

## Day 3-4 完了判定

- [x] gcloud auth / プロジェクト確認 (`gen-lang-client-0549297663` アクティブ)
- [x] BQ `btc_trading` dataset 既存5テーブル スキーマ・件数・期間確認
- [x] SQLite `x_tweets.db` テーブル一覧・件数確認
- [x] danjer単独 / 全アカウント 件数把握 (議事録の49,667を訂正)
- [x] 既存リサイクル可能資産の特定
- [x] v3用テーブル設計 DDL ドラフト
- [x] 不足データ整理

→ **Day 3-4 完了**。 Day 5-6 (LLM分類 + 投資判断ポスト抽出) 着手準備完了。
