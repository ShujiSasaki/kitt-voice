# CLAUDE.md — KITT: Shujiの個人AI執事

## ビジョン

KITTはShujiの個人AI執事。配達判定は最重要機能の一つだが全てではない。
音声で何でも頼め、対応できなければ仕組みを拡張する。システム自体の修正・運用もKITT守備範囲。
**完成形がない「成長し続けるシステム」。**

**最終目標**: KITTに判断を任せた方がShujiの時給単価が上がる世界線。
**優先順位**: レスポンス速度 > 費用 > 構築の速さ

## KITTの在り方

- AirPodsの向こう側にいる相棒。常時音声接続（マイク常時ON）
- 自然な会話ができる（待機中も雑談・助言・音楽再生）
- オファー時は音楽下げて判定解説→音楽復帰
- 「次のトイレここ」「水買っとけ」「今日もう2万行ったぞ」みたいな助言
- 何でもBOXで送った情報は全部KITTの文脈に入る
- 音楽は音声指示で制御（「ヒゲダン流して」等）、手段はKITTが選ぶ
- バックグラウンドでも会話継続（iOS制約との戦い）
- **未解決**: 走行中の風切り音でShujiの声を認識できない問題

## 機能スコープ

```
KITT = Shujiの音声AI執事
  ├─ 配達判定（最重要）
  │   ├─ 特徴量はAIがデータから取捨選択（項目数制限なし、5秒以内レスポンス）
  │   ├─ クエスト最適化（件数こなす vs 高単価厳選）
  │   ├─ 機会コスト推定（蹴る vs 待つ）
  │   ├─ 蓄積データで自己改善（offer × delivery × charging突き合わせ）
  │   └─ 最終目標：KITTに任せた方が時給が上がる
  ├─ 稼働サポート
  │   ├─ トイレ・食事・水分補給のタイミング提案
  │   ├─ 疲労度に応じた切り上げ提案
  │   └─ 稼働状況サマリー（売上、クエスト進捗）
  ├─ 音楽・エンタメ
  │   ├─ 音声指示で再生（手段はKITTが選ぶ）
  │   ├─ 喋る時は音量下げて戻す
  │   └─ バックグラウンド再生
  ├─ 情報収集
  │   ├─ 天気・交通・イベント自動取得
  │   ├─ 何でもBOXの情報を文脈統合
  │   └─ フードデリバリー関連情報の自動収集
  ├─ 何でも対応
  │   ├─ 質問回答・指示実行
  │   └─ システム修正・拡張も守備範囲
  └─ Phase2: 出前館・ロケットナウ・Menu対応（Uber安定後）
```

## 判断モデル（6レイヤー）

Shujiの配達判断は20+項目の複合判断。現在のCFは7項目のみ。

| レイヤー | 要素 | データソース |
|---------|------|-------------|
| 1. オファー単体の質 | 報酬、距離、時間、km単価、時給、店地雷度、ドロップ先 | OCR、BQ蓄積 |
| 2. 次オファーへの連鎖 | ドロップ先エリアの密度、主要エリアへの戻りやすさ | BQ蓄積（将来） |
| 3. クエスト・週間・月間最適化 | 件数vs高単価、週前半/後半クエ、月間目標 | 何でもBOX → context_logs |
| 4. 稼働リソース制約 | Uber稼働可能時間、オフライン残、ピーク残 | 音声、何でもBOX |
| 5. 身体・環境 | 疲労、空腹、トイレ、天気、交通、イベント | 音声（KITTに伝える）、外部API |
| 6. 市場の読み | 繁忙/閑散、拒否後の待機コスト | BQ蓄積、外部情報 |

## アーキテクチャ

```
[判定フロー]
iPhone 17Pro「Uber ai」iOSショートカット
  → スクリーンショット撮影 → OCR → POST /offerJudge
  → Cloud Functions (Node.js 22, asia-northeast1)
    → 並列取得: BQ係数 + 店舗履歴 + 直近トレンド + クエスト情報
    → 重み付けスコアリング判定 (Geminiは画像フォールバックのみ)
    → 並列書込み: [BQ offer_logs + Firebase RTDB /offer_tts]
  → iPhoneへ通知レスポンス (reason + 時給 + 実効時給)

[KITT音声報告フロー]
KITT PWA (GitHub Pages, Safari常駐)
  → Firebase RTDB 3秒ポーリング
  → オファー検知 → YouTube音量ダック
  → Gemini Live Audio WebSocketにコンテキスト注入
  → KITTが音声で判定理由を解説
  → YouTube音量復帰

[運用フロー]
KITT(YouTube視聴中) → UberDriver通知タップ → ショートカット自動実行
→ 判定通知 → KITTに戻る → KITT音声解説 → UberDriverで受諾/拒否

[データ蓄積フロー]
何でもBOX → POST /nandemoBox → context_logs (クエスト、リザルト等)
充電ON/OFF → POST /chargingEvent → charging_logs (GPS+時刻で行動ログ)
```

### 充電ON/OFFの行動ログ

充電ON/OFFはGPS+時刻と組み合わせて行動の推定に使える:
- 充電ON = 待機中 / ピック完了 / ドロップ完了（駐輪場にいる）
- 充電OFF = ピック開始 / ドロップ開始 / 稼働終了（走り出した）
- offer_logsのタイムスタンプと突き合わせで実配達時間・店待ち時間が計算可能

## サービス・リソース一覧

### GCP (project: gen-lang-client-0549297663)

| リソース | 詳細 |
|---------|------|
| Cloud Functions (Gen2) | offerJudge, ytSearch, nandemoBox, chargingEvent |
| Cloud Functions URL | `https://asia-northeast1-gen-lang-client-0549297663.cloudfunctions.net/{name}` |
| BigQuery Dataset | `ubereats_analytics` |
| Gemini APIキー (CF用) | 環境変数 `GEMINI_API_KEY` |
| Gemini APIキー (KITT用) | Default Gemini Project(0549297663)のキー。**旧(0353774050)はWS非対応** |
| Geminiモデル (CF) | gemini-2.0-flash (画像フォールバック用) |

#### Cloud Functions 詳細

| 関数 | Runtime | メモリ | minInstance | maxInstance | Timeout | 備考 |
|------|---------|--------|-------------|-------------|---------|------|
| offerJudge | nodejs22 | 256M | **1** (常時ウォーム) | 100 | 60s | メイン判定。API認証あり |
| nandemoBox | nodejs22 | 256Mi | 0 | 100 | 60s | 何でもBOX。API認証あり |
| chargingEvent | nodejs22 | 128Mi | 0 | 100 | 30s | 充電イベント。API認証あり |
| ytSearch | nodejs22 ✅ | 256M | 0 | 100 | 15s | YouTube検索。認証なし |

全関数Node.js 22に統一済み (2026-03-28)。

#### CF環境変数

| 変数 | 用途 | 設定先 |
|------|------|--------|
| GEMINI_API_KEY | Gemini API (画像解析用) | Cloud Functions環境変数 |
| FIREBASE_DB_SECRET | RTDB認証書き込み用シークレット | Cloud Functions環境変数 |
| CF_API_KEY | CF簡易認証ヘッダ (X-API-Key) | Cloud Functions環境変数 |

### Firebase (project: ubereats-kitt)

| リソース | 詳細 |
|---------|------|
| RTDB URL | `https://ubereats-kitt-default-rtdb.asia-southeast1.firebasedatabase.app` |
| RTDB Path | `/offer_tts` → `{offer:{...}, context:{...}, timestamp}` |
| Rules | 公開読み取り + シークレット認証書き込み (適用済み 2026-03-27) |

### GitHub Pages (KITT PWA)

| 項目 | 詳細 |
|------|------|
| URL | `https://shujisasaki.github.io/kitt-voice/` |
| リポジトリ | `ShujiSasaki/kitt-voice` |
| ファイル | `index.html` (~970行, v2.2) |
| Geminiモデル | `gemini-2.5-flash-native-audio-preview-12-2025` |
| 音声 | Zephyr |

### 端末構成

| 端末 | 用途 |
|------|------|
| iPhone 17Pro + AirPods Pro2 | UberDriver + KITT(常駐・YouTube) + Uber aiショートカット |
| iPhone XR | Google Maps + TVer + radiko + J:COM Stream |
| Googleアカウント | sasakishuji316@gmail.com (全サービス共通) |

## BigQuery テーブル・ビュー一覧

### テーブル (6つ)

#### offer_logs (533行, 2026-03-27時点)
オファー判定ログ。日パーティション(timestamp), クラスタリング(area, hour_of_day)。
```
log_id, timestamp, lat, lng, address, wireless_charging,
gemini_decision, estimated_hourly_rate, decision_reason, confidence,
base_hourly_wage, offer_reward, offer_distance, offer_duration,
weather_condition, traffic_status, quest_progress,
actual_accepted, actual_payout, actual_duration_minutes, actual_distance_km,
response_time_ms, raw_gemini_response, raw_ocr_text,
weather_info, store_name, day_of_week, hour_of_day, decision_reason_detail
```
**注意**: actual_accepted / actual_payout は現在全てNULL。フィードバックループ未実装。

#### delivery_history (22行)
実際の配達履歴。日パーティション(timestamp), クラスタリング(area, hour_of_day)。
```
delivery_id, timestamp, area, lat, lng, reward, distance, duration,
hourly_wage, store_name, drop_off_address, day_of_week, hour_of_day, wireless_charging
```

#### context_logs (142行)
何でもBOXの投入データ。
```
log_id, timestamp, type, summary, structured_data (JSON),
ai_note, raw_gemini_response, image_size_kb, processing_time_sec
```

#### charging_logs (123行)
充電ON/OFFイベント。GPS付き行動ログ。
```
timestamp_utc, timestamp_jst, wireless_charging, lat, lng,
near_parking, is_work_session, cleanup_after
```

#### dynamic_coefficients (23行)
スコアリング係数。CFから10分キャッシュで読み込み。BQ編集だけでCF再デプロイなしに調整可能。
```
coefficient_name, coefficient_value, last_updated, description
```

主要係数 (2026-03-12更新):
| 係数 | 値 | 説明 |
|------|-----|------|
| base_hourly_wage | 1993.44 | 直近90日の平均時給 |
| avg_reward | 688.89 | 平均報酬額 |
| avg_distance | 3.21 | 平均配達距離km |
| avg_duration | 20.52 | 平均配達時間(分) |
| avg_reward_per_km | 223.81 | 平均km単価 |
| avg_speed_kmh | 9.37 | 平均配達速度 |
| avg_hourly_wage_lunch | 2110.90 | ランチ帯(11-14時) |
| avg_hourly_wage_dinner | 2186.10 | ディナー帯(17-21時) |
| avg_hourly_wage_weekend | 2142.63 | 週末平均 |
| avg_hourly_wage_weekday | 2099.27 | 平日平均 |
| avg_hourly_wage_late_night | 1886.67 | 深夜帯(22-6時) |
| next_offer_interval_sec | 300 | 次オファー待機推定(秒) |
| score_threshold | 0.85 | accept/reject閾値 |
| weight_hourly_rate | 0.30 | スコア重み: 時給 |
| weight_reward_per_km | 0.20 | スコア重み: km単価 |
| weight_market | 0.15 | スコア重み: 市場比較 |
| weight_distance | 0.10 | スコア重み: 距離 |
| weight_store_reputation | 0.10 | スコア重み: 店舗評価 |
| weight_opportunity | 0.10 | スコア重み: 機会コスト |
| weight_quest_adjusted | 0.05 | スコア重み: クエスト |

#### external_research (82行)
外部情報収集。日パーティション(timestamp)。
```
id, timestamp, source, title, url, description, published_at, search_query
```

### ビュー (6つ)

| ビュー | 用途 |
|--------|------|
| offer_logs_clean | 壊れたデータ除外（Make変数未展開、null報酬、null判定を除外） |
| dashboard_summary | 日別×時間帯別のオファー集計（Looker Studio用） |
| dashboard_daily_trend | 日別トレンド（承諾率、平均報酬、日次収益） |
| dashboard_integrity | 全テーブル横断のデータ品質チェック |
| store_performance | 店舗別パフォーマンス集計（オファー数、承諾率、平均時給、km単価） |
| charging_logs_view | 充電ログ + 駐輪場判定 + 勤務セッション判定 |

## 現在のスコアリングシステム

Cloud Functions `offerJudge` の重み付けスコアリング (7項目):
- reward_per_km (20%): km単価 / 平均km単価(223.81)
- hourly_rate (30%): 推定時給 / 時間帯別平均時給
- distance (10%): 平均距離(3.21) / 実距離 (近いほど高得点、上限2.0)
- store_reputation (10%): 過去3回以上データがある店は受諾率ベース (0.8〜1.2)
- market (15%): 報酬 / 直近2時間の平均報酬
- quest_adjusted (5%): クエストボーナス加算後
- opportunity (10%): 報酬 / (配達時間+待機時間) × 待機コスト単価

**Threshold: 0.85** → これ以上ならaccept

通知形式: `受ける ¥2,200/h(実効¥1,650/h)` → 実効時給 = reward / (durationMin + waitMin) × 60

## KITT設計方針 (確定済み)

| 方針 | 内容 |
|------|------|
| オーバーレイ | **全くいらない** (Shuji明言) |
| KITT接続 | **常にON** → ページ読込1.5秒後に自動接続 |
| 音声会話 | 自然な会話（簡潔すぎない） |
| 通知形式 | 受け/パス + 時給 + 実効時給 |
| バックグラウンド復帰 | visibilitychange → 自動再接続 |
| YouTube統合 | IFrame Player API、オファー時にダック→復帰 |

## 絶対に忘れてはいけないこと

### iOS OCR ¥記号問題
iOS OCRは`¥`記号を中点`·`に変換する。報酬パーサーは `/[·•]\s*([0-9,]+)/` パターンが**必須**。`/[¥￥]/` だけでは報酬0円になる。

### iOSショートカット技術制約
- JSON送信が`{"":{"actual_data"}}`と空キーでネストされる → CF側で`if(body[""]&&typeof body[""]===object) body=body[""]`で対応済み
- OCR改行がJSON送信時にリテラル`\n`(2文字)になる → `text.split(/\\n|\n/)`で両パターン対応 **⚠️ 現在のCFコードは`split('\n')`のみ。バグあり。**
- OCRテキストにノイズ多数 (地図数字、時刻、バッテリー%) → 位置ベースパース必須

## 失敗済みアプローチ (二度と提案しない)

### 音声出力系
- ✗ iOS TTS (Safari speechSynthesis / ショートカット読み上げ) → 不採用、何度も潰し済み
- ✗ AirPods「通知の読み上げ」→ YouTube再生中は抑制で不可
- ✗ iOSスピーカーで通知を読み上げ → 初回のみ、連続通知は抑制

### 通知・オートメーション系
- ✗ iOSサウンド認識でUberDriver通知音検知 → AirPods接続中は本体マイクに音が来ず不可
- ✗ LINE Notify → 2025年3月終了済
- ✗ LINE Messaging API → 月200通で不足
- ✗ iOS「App Notification」オートメーショントリガー → iOS18に存在しない
- ✗ Pushcut execute (/execute) → Automation Server常駐必須＋Pushcut有料最前面待機が必要

### ブラウザ・技術系
- ✗ ブラウザ変更でバックグラウンド問題解決 → iOSは全ブラウザWebKit強制で同じ
- ✗ Browser Use CLIでGCP操作 → コンテナからGCPにアクセス不可
- ✗ Pythonの`code.replace()`で日本語含むJS → **Unicode文字が消える、絶対禁止**

## コーディング規約

### KITT PWA (index.html)
- 単一HTMLファイル (CSS + JS inline)
- フォント: Orbitron (Google Fonts)
- カラー: CSS変数 (`--red`, `--green`, `--amber`, `--text`, `--text-dim`)
- UIテーマ: ナイトライダー風ダークUI
- 状態管理: グローバル`state`オブジェクト、`config`オブジェクト
- 設定永続化: localStorage (`kitt-yt-config`, `kitt-yt-history`)
- ログ: `log()`関数 → `#log-bar`に表示 + console.log
- AudioContext: 再生用24kHz、マイク用16kHz (別インスタンス)

### Cloud Functions (index.js)
- `@google-cloud/functions-framework` でHTTPエントリポイント
- Firebase RTDB: REST API (SDK不使用)
- BigQuery: `@google-cloud/bigquery`
- 並列処理: `Promise.all()` で読み取り・書き込みを並列化
- エラー処理: try-catch + fallback値 (3層構造)
- Gemini: 画像フォールバックのみ (メイン判定はスコアリング)
- キャッシュ: インメモリ (coefficients 10分, trends 2分, store 5分)

### デプロイ方法
- **GitHub Pages**: ファイル編集 → コミット → 自動デプロイ
- **GCP Cloud Functions**: `gcloud functions deploy` (ローカルcf-offerjudge/から)
- **致命的教訓**: GitHub CM6エディタでCmd+Aが効く、追記 → ファイル二重化・三重化が複数回発生。コミット前に必ず末尾確認 (`</html>`が1つだけ)

## ユーザーコミュニケーション要件

- 非エンジニア、専門用語は噛み砕いて説明する
- 説明は「今こういう状態→こういう問題がある→だからこうする」の順番
- 「Claudeが自分で全部やる」ことに価値を感じている。手順書を渡して終わりにしない、コード取得・編集・デプロイまで可能な限り自分で実行する
- 不要な確認質問は望まない。自分で判断して実行する。「考えなくていい、やっとけ」のShujiのスタンス
- 本音ベースで話す

## リポジトリ構成

### ShujiSasaki/kitt-voice (GitHub Pages)
```
index.html        # KITT PWA本体 (~970行, v2.2)
manifest.json     # PWA manifest
CLAUDE.md         # このファイル
README.md
cf-offerjudge/    # Cloud Functions ソース
  index.js        # メインソース (offerJudge, nandemoBox, chargingEvent)
  package.json    # Node.js 22, 依存: functions-framework, bigquery
```

## 完了済みタスク

### チャット25 (2026-03-28) — ビジョン擦り合わせ + システム全面改善 + KITT UI/UX改善

#### ビジョン・設計
- ✅ KITTビジョン確定: 配達判定ツール→個人AI執事に再定義
- ✅ 判断モデル整理: 6レイヤー・20+項目の複合判断を言語化
- ✅ システム全体監査: BQ/CF実態とCLAUDE.mdの乖離を特定
- ✅ CLAUDE.md全面改訂: 文字化け修正 + ビジョン反映 + 実態反映
- ✅ メモリ保存: ビジョン・プロフィール・監査結果・フィードバック

#### CF改善
- ✅ OCR改行バグ修正: `split('\n')` → `split(/\\n|\n/)`
- ✅ CFフォールバック値をBQ実データに更新 (全箇所)
- ✅ getTimeSlotAvgに深夜帯(22-6時)追加
- ✅ store_reputation計算に地雷度反映 (低時給/遠距離ペナルティ)
- ✅ 天気API (Open-Meteo) をofferJudgeに追加 (雨ボーナス/ペナルティ)
- ✅ Geminiモデル更新: gemini-2.0-flash → gemini-2.5-flash (旧モデル廃止対応)
- ✅ nandemoBoxのGeminiプロンプト大幅改善 (日本語+具体例+responseMimeType=JSON)
- ✅ nandemoBoxにFIREBASE_DB_SECRET環境変数追加 (RTDB書き込み修正)
- ✅ dynamic_coefficients自動再計算: リザルト送信時にoffer_logs_cleanから係数自動更新
- ✅ dashboardFeed CFエンドポイント新規作成 (BQから直接ログ取得)

#### BQ改善
- ✅ BQビュー3つ作成: offer_delivery_match, judgment_accuracy, store_risk_score
- ✅ context_logs → delivery_history自動転記: 既存116件バックフィル
- ✅ actual_accepted自動判定: syncDeliveryResult (店名部分一致でoffer_logs更新)
- ✅ nandemoBox投入時にdelivery_history自動転記 + 係数自動再計算

#### KITT PWA改善
- ✅ LOGタブ → オファー/何でもBOXの2タブに分離、文字サイズ2倍
- ✅ ダッシュボードをBQ直接取得に変更 (RTDBの上書き問題解消)
- ✅ 何でもBOXのジャンルタグ日本語化 (クエスト/リザルト/その他)
- ✅ クエスト表記整理: ピーク/連続/週前半/週後半 (タイトルからクエスト文字削除)
- ✅ 設定画面に声の選択ドロップダウン追加 (30種類のGemini声)
- ✅ KITTシステムプロンプト: 胡蝶しのぶキャラ設定 (修治さん呼び)
- ✅ 時刻・場所をシステムプロンプトに動的注入
- ✅ 声質一貫性指示 (再接続時も初対面にならない)
- ✅ 永続記憶: localStorageに会話記録保存、再接続時にプロンプト注入
- ✅ ws.onclose自動再接続 (2秒後) + 5分keepalive再接続
- ✅ 重複ログ防止: lastOfferTimestampをlocalStorageに永続化
- ✅ v2.3系としてGitHub Pagesデプロイ

#### iOSショートカット修正
- ✅ 何でもBOXの送信先URL: Make.com → Cloud Functions nandemoBoxに変更
- ✅ 本文形式: ファイル → JSONに変更

#### 音楽再生 (function calling)
- ✅ Gemini function calling (tools) でplay_music/stop_musicを定義
- ✅ toolCallを検知してYouTube検索結果をYouTubeタブに表示
- ✅ ユーザーがYouTubeタブから選んで再生する方式に落ち着いた

#### 失敗・教訓 (次回以降の注意)
- ✗ `responseModalities: ['AUDIO', 'TEXT']` → Native Audioモデルで接続不可。**絶対にAUDIOのみ**
- ✗ toolsのfunctionDeclarationsに`behavior: 'NON_BLOCKING'`を入れるとsetup失敗
- ✗ toolResponseに`id`フィールドを入れるとWS切断→再起動ループ。**nameとresponseのみ**
- ✗ iOS SafariではユーザージェスチャーなしにYouTube autoplayが効かない
- ✗ iOSショートカットの「本文を要求：ファイル」はmultipart送信になりCFがJSONパースできない。**JSONを選ぶ**
- ⚠️ nandemoBoxとofferJudgeでGemini APIキーが異なっていた→統一必要
- ⚠️ Geminiが長いstructured_dataを返すとmaxOutputTokensで途切れる→JSONパース失敗のフォールバック必須
- ⚠️ RTDBのバリデーションルールで新しいパスへの書き込みがブロックされる→offer_ttsパスを共用

#### Shujiの要望メモ (次セッション引き継ぎ)
- 声質をもっと胡蝶しのぶに寄せたい (現在の30種類の声は全部低いと感じている)
- キャラ設定は試行錯誤中。しのぶ以外も試すかも
- 音楽は「KITTに声で指示→YouTubeタブに検索結果→自分でタップ再生」でOK
- 会話記憶は永続化済みだが、記憶の質と量の調整が必要
- KITTの時間感覚ズレ→接続時にJST時刻注入で対応済み
- 声質・話し方のブレ→プロンプトで一貫性指示済みだが改善余地あり
- 権限設定: bypassPermissions + rm系のみask/deny
- バイク走行中の音声認識→AirPods適応型オーディオを左寄り(ノイキャン強め)で対応中
- KITTがバックグラウンド→フォアグラウンド復帰時にYouTube自動再開(loadVideoById実装済み)
- iOSショートカット「何でもBOX」の送信先をMake.com→CF nandemoBoxに変更済み
- 通知の「実効」表記を「AI」に変更済み
- OCR報酬パーサー修正: ¥9配達UIラベルをスキップ、3桁以上のみ報酬として認識

#### 次セッションでやるべきこと (何でもBOXタブ大改善)
1. **ピーク条件→ピークに統一**: Geminiプロンプトの「ピーク条件」「ピーク時間クエストの条件画面」を削除、全部「ピーク」にする
2. **件数と金額は全段合計**: 個別段の金額(¥400, +¥500)ではなく合計(6件 900円)で表示
3. **ジャンル別ソート機能**: タブ内にフィルターボタン(全部/クエスト/リザルト/受諾/その他)
4. **画像を2週間保存**: context_logsにimage_base64を保存するか、GCSに画像保存してURLを記録
5. **フォントサイズ75%**: 現在の22px→16px等に縮小
6. **タップで画像表示**: 各エントリをタップするとスクショ画像をモーダル表示(閉じるバツボタン付き)
7. **2週間分スクロール**: dashboardFeedのsinceを14日前にし、LIMIT増やす

#### 画像保存の設計メモ
- BQにbase64保存は非効率(1枚50-100KB)。GCS(Cloud Storage)に保存してURLをBQに記録が最適
- context_logsにimage_urlカラム追加が必要
- nandemoBox CFで画像をGCSにアップ→URLをcontext_logsに保存
- dashboardFeedでimage_urlも返す→KITTでタップ時にfetch→表示
- 14日後に自動削除: GCSのLifecycleルールで設定

### チャット24 (2026-03-27) — 係数BQ完全移行 + Puppeteer検証 + autoモード
- ✅ 係数BQ完全移行: calculateScore()のweights 7項目 + threshold をBQ dynamic_coefficientsから動的読込に変更
- ✅ cf-offerjudge/package.json 作成 (ローカルからgcloud functions deploy可能に)
- ✅ Puppeteer MCP検証: 全7ツール動作確認済み
- ✅ permissions.defaultMode を "auto" に設定

### チャット23 (2026-03-27) — RTDBルール制限 + CF認証ヘッダ + gcloud CLI
- ✅ Firebase RTDBセキュリティルール適用 (認証なし書き込みブロック、公開読み取りOK)
- ✅ CF環境変数 FIREBASE_DB_SECRET 設定 + コード修正 + デプロイ
- ✅ gcloud CLI インストール + gcloud auth login
- ✅ CF簡易認証ヘッダ追加 (X-API-Key) → 全CFデプロイ完了
- ✅ iOSショートカット「Uber ai」にX-API-Keyヘッダ追加完了
- ✅ Node.js 22アップグレード → offerJudge, nandemoBox, chargingEvent デプロイ完了

### チャット22 (2026-03-27) — マイク解決 + 常時ON + v2.2
- ✅ マイク入力デバッグ → 音声会話成立確認
- ✅ AudioContext resume() 追加 (iOS Safari対策)
- ✅ 常時ON化 (Gemini接続後マイク自動ON、タイムアウト時再接続、フォアグラウンド復帰時マイク再起動)
- ✅ v2.2 mainマージ・デプロイ完了 (PR #1, sha 6f75022)

### チャット21 (2026-03-24) — v2.0/v2.1
- ✅ KITT 3重複修正 → 803行にクリーンアップ → コミット
- ✅ CF通知に実効時給追加 → GCPデプロイ完了
- ✅ KITT 3文プロンプト短縮
- ✅ マイク入力実装 (getUserMedia → ScriptProcessor → PCM16 → realtimeInput) → v2.1コミット (943行)

### チャット20 — Gemini音声確認
- ✅ KITT Gemini Native Audio動作確認 (デスクトップ)
- ✅ 11件のバグ修正 (APIキー、Blob応答、AudioContext等)

### チャット18 — 設計確定
- ✅ KITT設計方針確定 (オーバーレイ不要、常時ON等)
- ✅ YouTube統合アーキテクチャ確定

### チャット17 — OCR根本解決
- ✅ OCR bodyアンラップ次落修正
- ✅ 中点パターン追加 (iOS OCR ¥→·変換対応)
- ✅ 店名パーサー改善 (「合計」行の次行)
- ✅ BQ raw_ocr_text保存

### それ以前
- ✅ Cloud Functions offerJudge スコアリング判定
- ✅ Firebase RTDB連携
- ✅ YouTube検索 (innertube API, viewCount, continuation)
- ✅ YouTube再生 (IFrame Player API)
- ✅ 視聴履歴 (YouTube公式風UI)
- ✅ Looker Studio ダッシュボード
- ✅ iOSショートカット「Uber ai」

## 未解決タスク

| # | タスク | 状態 |
|---|--------|------|
| 1 | リアルオファーでのKITT音声報告テスト | 未確認 |
| 2 | リザルト突き合わせ (offer × delivery × charging) | ✅ 完了 (2026-03-28) |
| 3 | CFスコアリング特徴量拡張 (7項目→AI選択) | 未実装 |
| 4 | OCR改行バグ修正 | ✅ 完了 (2026-03-28) |
| 5 | ytSearch Node.js 22 | ✅ 完了 (2026-03-28) |
| 6 | 走行中の音声認識改善 | 未着手 |
| 7 | バックグラウンド音声継続 (iOS制約) | 未着手 |
| 8 | KITTの声質改善 (しのぶっぽい高い声) | Gemini30種全部低い。カスタム音声不可 |
| 9 | 音楽の完全自動再生 (iOS autoplay制限) | 現状は検索→手動タップ再生で妥協 |
| 10 | Gemini function calling安定化 (toolResponseでWS切断問題) | idフィールド除去で一部改善、要検証 |

### Puppeteer MCP (2026-03-27 検証済み)
settings.json にPuppeteer MCPサーバーを登録済み (`~/.claude/settings.json` → `mcpServers.puppeteer`)。
全7ツール動作確認済み: navigate, screenshot, click, fill, select, hover, evaluate。

### チャット26 (2026-03-28〜04-03) — 過去最長セッション: ダッシュボード大改善 + PDCA自動学習 + Pixel移行設計

#### Shujiの意思決定
- **Pixel 10 Pro移行を検討中**: 4社(Uber/出前館/ロケットナウ/menu)完全自動化が目標
- **段階的ではなく理想を最初から追う**: 「小さく始める」は求めていない。理想が叶わないなら投資する意味がない
- **撤退ラインは明確**: 1ヶ月で撤退時の実損失5-6万。Pixel中古買取で回収
- **収益最大化が全ての目的**: AIに判断を委ねて時給向上。データ蓄積でAIが成長し続ける
- **マルチモーダル(カメラ)にも関心**: KITTの目と耳。Phase 2として検討

#### KITT PWA ダッシュボード改善
- ✅ 何でもBOXタブ大改善: フィルター(全部/クエスト/リザルト/受諾/その他)、フォントサイズ75%、日付グループ
- ✅ リザルト表示3行化: 1行目=店名+町名+配達完了時刻、2行目=/件(太字)、3行目=合計(薄字)
- ✅ SS順/オファー順ソート切替
- ✅ 画像モーダル: タップで表示、同一案件複数枚スワイプ対応
- ✅ BQタブ新設: データ蓄積状況、オファーvs実績ズレ、時間帯別、店舗ランキング、係数一覧
- ✅ 天気表示: 現在天気+6時間降水予報
- ✅ PDCA自動学習セクション: 重み変更履歴、相関グラフ
- ✅ システム状態表示: 自己診断結果、自動修復ログ
- ✅ クエスト認知表示: 未終了のみ、開始時間順、type=nandemoのJSON埋め込みも抽出
- ✅ 外部情報収集表示: X投稿(シアン)、配達員投稿(緑)、ニュース(アンバー)、交通(赤)
- ✅ タブ反応しない問題修正: touchendイベント追加 + nandemo-log-panelのCSS優先度修正

#### スクショ2週間保存 (GCS)
- ✅ GCSバケット `kitt-screenshots-0549297663` (14日ライフサイクル、公開読取)
- ✅ nandemoBox: スクショをGCS保存→URLをBQに記録
- ✅ offerJudge: スクショをGCS保存→RTDB offer_imagesに記録
- ✅ offerScreenshot CFエンドポイント新規作成
- ✅ iOSショートカット「Uber ai」の最後にBase64エンコード+offerScreenshotへPOST追加
- ✅ dashboardFeed CF側でRTDB offer_imagesからimage_url補完(ストリーミングバッファ回避)

#### OCRパーサー根本改善
- ✅ 報酬: 合計行の上3行を最優先→中点パターン→¥パターンの3段階フォールバック
- ✅ 報酬: 0始まり(地図番号)スキップ、100-9999円範囲制限、+·追加オファー対応
- ✅ 報酬: ロケットナウ形式「XXX円」(¥マークなし)対応
- ✅ 時間: 「合計XX分」最優先、「約XX分」対応。バッテリー%誤検知防止
- ✅ 距離: 「配達距離X.Xkm」(ロケットナウ形式)対応
- ✅ 店名: 日本語バリデーション、「店屋亭堂」含む行優先、ゴミ除外強化
- ✅ 店名: ロケットナウ形式=報酬行(XXX円)の上の行から取得

#### PDCA自動学習エンジン
- ✅ recalculateCoefficients: 推定値(OCR)→実績値(actual_*)優先に修正
- ✅ 重み自動最適化: 各スコア要素と実績時給の相関→相関が強い要素に重みを寄せる
- ✅ 閾値自動最適化: 時給最大化される受諾スコアラインを探索
- ✅ Cloud Scheduler: 毎朝4:30にpdcaCycle自動実行
- ✅ AI突き合わせ: GeminiでofferとdeliveryをAI判定で紐付け(ルールベース→AI)
- ✅ 次オファー待機予測: オファー毎に直近1h中央値で更新(300秒固定→48秒に)
- ✅ waiting_expectation_value: 実データから自動計算(1000固定→1815)
- ✅ 天気ブースト係数: 雨vs晴の実績時給差から自動計算(0.10→0.30/0.15→0.40)

#### 自己診断・自己修復システム
- ✅ systemHealth CF: 10分毎に自動実行
- ✅ チェック項目: OCR報酬0円、時間0分、ゴミ店名、実績マッチ率、係数鮮度、天気鮮度、異常時給
- ✅ データ整合性クロスチェック: delivery件数 vs offer_logs紐付け件数
- ✅ 重み正規化: 合計1.0からずれたら自動修復
- ✅ 未マッチdelivery自動再突き合わせ

#### データ突き合わせ精度改善
- ✅ 17件→124件→172件→277件(AI突き合わせ含む)
- ✅ 3月実データ45/46件マッチ(98%)
- ✅ syncDeliveryResult: 正規化+報酬近傍マッチに改善
- ✅ store_master: 店舗名正規化テーブル(英語除去+スペース除去)
- ✅ 店舗待機時間: 充電OFF→ON(停車→発進)で正確計測。受諾SSの後の最初の停車=ピック到着

#### P1バグ5件修正
- ✅ questBonus誤抽出: `([0-9]+)`→`([0-9,]{3,})円`(日付の3/28の3を拾ってた)
- ✅ scores[key]||1.0: 0が1.0に化ける→`!= null`チェックに変更
- ✅ RTDB+BQ Promise.all: RTDB失敗でBQ insertも死ぬ→分離してfire-and-forget
- ✅ 約XX分未対応: durationパーサーにパターン追加
- ✅ quest_result→result誤変換: quest_resultのまま保存するように修正

#### 外部情報収集
- ✅ externalResearch CF: 10分毎(リアルタイム)+日次4:04(全国)
- ✅ weatherCheck: 10分毎→RTDB+BQタブ表示
- ✅ Cloud Scheduler: 5ジョブ稼働(天気/リサーチ10分毎/日次/PDCA/ヘルスチェック)
- ✅ X(Twitter)キーワード検索: uber/出前館/ロケット+福岡をGoogle News RSS経由
- ✅ X個人アカウント18件登録: 福岡配達員。現在はXのOGPブロックで自動取得不可→Pixel移行後にNotificationListenerで対応

#### Gemini関連
- ✅ nandemoBox高速化: GCSをBGに移動+thinkingBudget:0
- ✅ 通知表示崩れ修正: summary改行除去+80文字切詰
- ✅ 雨クエスト対応: 通常ピークと時間帯の違いで判別
- ✅ 受諾SS改善: 緑アイコン=店舗/赤アイコン=顧客の判別ルール+PD順序

#### ロケットナウ対応開始
- ✅ OCRパーサー: 「XXX円」報酬、「配達距離X.Xkm」、報酬行の上の行が店名
- ⚠️ duration(所要時間)はロケットナウのオファー画面に表示されないため取得不可

#### Pixel 10 Pro 移行設計 (設計書作成済み)
- ✅ 設計書: https://shujisasaki.github.io/kitt-voice/design.html
- **機材**: Pixel 10 Pro(15万) + ピンマイク(1.5万) + AirPods Pro 2(所持済)
- **月額**: Gemini API ¥500-3,000
- **開発工数**: Claude 24h + Shuji 5-8h
- **期待効果**: 月+¥53,500〜125,500(保守的〜楽観的)、投資回収3ヶ月
- **4社完全自動化**: NotificationListener+AccessibilityServiceで全社の受諾/拒否/稼働ON-OFFを自動化
- **AI直接判定**: 係数方式をやめ、Geminiにオファー+全蓄積データを渡して判断(10-15秒、タイムアウト内)
- **マルチモーダル**: Gemini 3.1 Flash Live対応。カメラ映像をリアルタイムでKITTに共有(Phase 2)
- **走行中音声**: ピンマイク(ヘルメット内チークパッド裏+ファーウインドジャマー)が最適解
- **スロートマイク**: 風切り音最強だが夏暑い。代替案としてピンマイク推奨
- **撤退ライン**: 1ヶ月で5-6万の損失(Pixel中古買取で回収)

#### 失敗・教訓
- ✗ Gemini 2.5 flashのthinkingBudgetがmaxOutputTokensを消費して`{}`返答→thinkingBudget:0で解決
- ✗ gemini-2.0-flash廃止→gemini-2.5-flashに移行(API変更リスクは常にある)
- ✗ offerScreenshotにFIREBASE_DB_SECRET環境変数が未設定→RTDB書き込み失敗
- ✗ GEMINI_API_KEYがCF間で異なっていた(nandemoBox vs pdcaCycle)
- ✗ JSテンプレートリテラル内の`\d`がJSエスケープで`d`になりBQのREGEXPがマッチしない→`\\d`に修正
- ✗ getMonth()が0ベース(3月=2)でクエスト日付フィルタがずれた
- ✗ 124件突き合わせ済みなのにBQタブのズレ分析が45件→offer_logs.actual_*から直接計算に変更すべきだった
- ✗ X個人アカウントの投稿はサーバーからは自動取得不可(OGPブロック+API有料+Nitter死亡)

#### Claudeへのフィードバック (次セッション必読)
- **網羅的な提案をする**: 機材変更含め理想から逆算して全選択肢を最初から出す
- **変更後のアウトプットを必ず検証**: 「動いた」と「正しい」は別。件数・妥当性を毎回確認
- **自分で確認してから報告**: Shujiに確認させる前に3回自分でテスト
- **段階的に小さく始めるを安易に提案しない**: Shujiの目的は理想の実現。妥協案は求めてない
- **本音で話す**: リスクもコストも正直に出す。お気持ち表明ではなく論理的な判断材料

#### 次セッションでやるべきこと
1. **Pixel 10 Pro購入判断**: Shuji検討中。設計書ベースで議論の続き
2. **ロケットナウのduration問題**: オファー画面に所要時間が出るか確認
3. **何でもBOXタブの表示崩れ**: ロケットナウのスクショが正しく表示されるか
4. **X配達員アカウントの投稿取得**: Pixel移行後のNotificationListener設計
5. **PDCA精度向上**: AI突き合わせのデータが増えれば精度が上がる。リザルトSSをもっと送る
