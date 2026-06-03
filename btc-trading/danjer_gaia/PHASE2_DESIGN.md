# Phase 2 設計書 (叩き台) — Live連携+Shadow Model+段階的投入

作成: 2026-06-03 / 担当: Claude (実装担当) / 監査予定: GPT (司会) / Gemini (技術)

## 1. Phase 2 の位置づけ

3者会議 Round 10 合意:

```
Phase 1 (Day 1-14): 評価基盤・danjer DNA・レジーム判定・TTL/Stance・検問所・朝サマリー  ← 完了
Phase 2 (Day 15-45): 紙トレ + Live Stage 0-1 (Shujiさん手動承認 → 最小自動)
Phase 3 (Day 46-160): Stage 2 (3xレバ自動解除) + 多通貨データ収集
Phase 4 (Day 161-240): BTC+ETH+SOL マルチアセット運用
Phase 5+ (Day 240+): 完全自律 + OKX追加 + ファンド化 (合法ヘッジ)
```

Phase 2 の目的:
- Phase 1 で作った「動く土台」を **実環境** に繋ぐ
- いきなり実弾ではなく、 **紙トレ → 最小ロット自動** の段階投入
- Shadow Model を並走させて 「腐らない仕組み」 を回す

## 2. Phase 2 ロードマップ (Day 15-45、 31日間)

| Day | 段階 | 内容 | 元手 | レバ | 介入 |
|---|---|---|---|---|---|
| 15-20 | **Phase 2.0 紙トレ実装** | Bybit/Hyperliquid のpaper trading APIに接続、 注文をシミュレート | $0 (virtual) | 〜2x | Claude実装 |
| 21-25 | **Phase 2.1 紙トレ実行** | 5日間連続実行、 朝サマリーで日次レビュー | $0 | 〜2x | Shujiさん観察 |
| 26-28 | **Phase 2.2 Shadow Model** | 本番AIと並走する Shadow を稼働、 日次比較 | $0 | - | 自動 |
| 29-30 | **Phase 2 評価会議** | 紙トレ + Shadow 5日分の結果で Live移行判定 | - | - | 3者会議 |
| 31-35 | **Phase 2.3 Live Stage 0** | 実弾だがShujiさん手動承認のみ (auto禁止) | $15 (0.0001 BTC) | 1x | Shujiさん全件承認 |
| 36-45 | **Phase 2.4 Live Stage 1** | 最小ロット自動、 L0自律/L2は承認 | $15-50 | 2x | L2のみShujiさん承認 |

## 3. コンポーネント設計

### 3.1 取引所API接続層 `exchange/`

```
exchange/
├── base.py              # ExchangeBase abstract class (open_position, close_position, get_balance, get_orderbook)
├── bybit_client.py      # ccxt or pybit (テストネット → 本番)
├── hyperliquid_client.py # Hyperliquid SDK or REST
├── paper_client.py      # 紙トレ用 (現実価格+シミュレート約定)
└── tests/
```

**必須機能**:
- `place_order(symbol, side, size, type, price, sl_price, reduce_only_sl=True)` — エントリー+SL同時発注 (S6必須)
- `close_position(symbol, side, size)` — 部分/全閉
- `get_position()` — 現在ポジション
- `get_balance()` — Equity
- `get_market_data(symbol, depth)` — 板/last/mark/Funding Rate
- `subscribe_websocket(callback)` — 価格急変検知 (Fast Guard用)

**reduce-only stop の重要性 (R30対策)**:
- Bybit `orderType=Market`, `triggerBy=LastPrice`, `reduceOnly=True`
- Hyperliquid `is_trigger=True`, `is_market=True`, `reduce_only=True`
- → SLが効かないでロスカット連鎖を防ぐ

### 3.2 Shadow Model `shadow/`

3者会議 GPT Round 5 提案:
> 「本番AIは安定版 / Shadow AIが毎日学習 / 合格した候補だけ昇格」

```
shadow/
├── shadow_runner.py     # 本番と同じデータを受けて Shadow Stance を生成
├── compare_logger.py    # 本番 vs Shadow の判断差分をBQに記録
└── promotion_gate.py    # CPCV/walk-forward/paper trade で合格→昇格
```

**Promotion 基準**:
- 90日 walk-forward で Shadow が 本番より Trade-EHR +10% 以上
- ガード違反 (Liquidation/MaxDD/NoStop) が同等以下
- 説明可能性 (R15) 維持

### 3.3 紙トレ環境 `paper_trading/`

```
paper_trading/
├── simulator.py         # 注文→シミュレート約定 (現実のbid/ask/spread考慮)
├── slippage_model.py    # 板から実際の約定コスト推定
└── runner.py            # Phase 1 のすべてを統合実行
```

**シミュレーション仕様**:
- 板情報を実時間で取得 → 注文サイズに応じた約定価格を計算
- Maker/Taker 手数料を実コスト反映 (Bybit -0.025% / +0.075%)
- スリッページ = top5板厚 vs 注文サイズ で算出

### 3.4 Live Runner (Cloud Run) `live/`

3者会議 Round 5 GPT: 「Cloud Run でステートレス Live実行」

```
live/
├── main.py              # Cloud Run エントリポイント (Flask/FastAPI)
├── scheduler.py         # Cloud Scheduler から15分毎に triggered
├── execute.py           # Slow Brain → Stance → Order Gate → Exchange
└── Dockerfile
```

**実行フロー**:
1. Cloud Scheduler (15分毎) → Cloud Run main.py
2. 市場データ取得 (Bybit/Hyperliquid REST)
3. Slow Brain呼び出し (Gemini Pro Context Cache)
4. Stance → TTLManager → FastGuard → Order Gate
5. APPROVE なら exchange.place_order()
6. 結果を BQ btc_judgments に記録

**Fast Guard は別経路**:
- Cloud Run は 15分毎の Slow Brain
- Fast Guard は **WebSocket 常時接続** で価格急変監視 → 別 Cloud Run (常時稼働) or local

### 3.5 監視・アラート `monitoring/`

```
monitoring/
├── dashboard_feed.py    # 朝サマリー生成 (Cloud Function) → KITT PWA表示
├── slack_alert.py       # Slack通知 (L2承認待ち、 L3/L4 緊急)
└── healthcheck.py       # TTL Manager状態、 API応答、 Balance
```

**通知レベル別出口**:
- L1 (注意): Slack #danjer-gaia-info に投稿
- L2 (承認): Slack #danjer-gaia-approve + メンション → Shujiさんがリアクションで承認/拒否
- L3 (強制停止): Slack #danjer-gaia-alert メンション + 全閉実行ログ
- L4 (BlackSwan): 全チャネル + iPhone push

## 4. 段階的本番投入の安全装置

### 4.1 Stage 0 (Day 31-35) — Shujiさん全件承認

- AIは Stance を出すが、 **自動発注しない**
- Slack に「次の発注候補: LONG 0.0001 BTC @ $X」を投稿
- Shujiさんが ✅ リアクションで承認 → exchange.place_order()
- ❌ で却下、 30秒タイムアウトで自動却下

### 4.2 Stage 1 (Day 36-45) — 最小ロット自動

- L0 自律 (Equity 0.25% 以下のリスク、 レバ 2x以下): 自動発注
- L2 承認待ち (Equity 0.5% 超 or レバ 3x超 or danjer DNA逆張り): Stage 0 と同じ承認フロー
- L3/L4: 自動全閉

### 4.3 緊急停止 (Kill Switch)
- Slack コマンド `/danjer halt` → 全 Cloud Run 停止 + 全ポジ閉鎖
- iPhone push notification にも対応

## 5. データフロー (BigQuery 設計)

```
新規テーブル (Phase 2):
- btc_trading.live_orders          (発注ログ、 decision_trace_id付き)
- btc_trading.live_positions       (ポジション履歴、 タイムシリーズ)
- btc_trading.shadow_vs_prod       (Shadow判断 vs 本番判断、 day別)
- btc_trading.fast_guard_events    (Fast Guardが介入したイベント)
- btc_trading.approval_requests    (L2承認待ち、 Shujiさん応答)
```

## 6. コスト見積もり (Phase 2 月次)

### 固定費
- Cloud Run (Slow Brain 15分毎、 数百ms実行): ほぼ free tier
- Cloud Run (Fast Guard 常時稼働、 e2-micro): $5-10/月
- Cloud Scheduler: 5ジョブまで無料
- Cloud Storage (BQ既存): $2-5

### 変動費
- Gemini 3.1 Pro Context Cache (24/7常駐): $10-20
- Gemini 3.1 Pro クエリ (15分間隔): $5-30
- Bybit/Hyperliquid API (読み取り): 無料
- WebSocket connection: 無料 (API)
- Slack API: 無料

### 取引手数料 (Stage 1から発生)
- Bybit Maker -0.025% / Taker 0.075%
- 月10-30トレード想定で $1-5

**Phase 2 月額合計: $25-75**

## 7. リスク対策 (Phase 1 R1-R33 全て継承 + Phase 2固有)

### Phase 2 固有 R34-R36

- **R34**: 紙トレと Live でスリッページが乖離
  - 対策: 紙トレslippage_model は楽観的に見積もる (実際にはより厳しい想定)、 Stage 0で実コスト計測

- **R35**: WebSocket切断によるFast Guard盲点
  - 対策: 2系統 WebSocket並列 (Bybit + Hyperliquid) + heartbeat 監視 → 1分切断で自動全閉

- **R36**: Stage移行時に「Shujiさんが間違って ✅押す」リスク
  - 対策: 大型判断 (Equity 1%超) は 30秒間 「本当に発注しますか?」確認 + 2回タップ要求

## 8. 必要な作業リスト (Phase 2 着手順)

| 順 | 作業 | 担当 | 推定 | コスト |
|---|---|---|---|---|
| 1 | Bybit testnet API key取得 | Shujiさん | 30min | $0 |
| 2 | exchange/bybit_client.py 実装 (testnet) | Claude | 1日 | $0 |
| 3 | paper_trading/simulator.py | Claude | 1日 | $0 |
| 4 | Phase 1 統合 Live Runner (local先行) | Claude | 1日 | $0 |
| 5 | 紙トレ 5日連続実行 | 自動 | 5日 | $0-2 |
| 6 | Shadow Model 並走 | Claude | 0.5日 | $0 |
| 7 | Phase 2 評価会議 (3者) | 全員 | 1時間 | $0 |
| 8 | Bybit本番API key + 0.0001 BTC 入金 ($15) | Shujiさん | 1時間 | $15 |
| 9 | Stage 0 Live実行 (手動承認) | Claude+Shuji | 5日 | $0.1 |
| 10 | Stage 1 移行 (最小ロット自動) | Claude | 0.5日 | $0 |

## 9. 3者会議で議論したい論点

1. **Cloud Run vs Local Python** 実行環境 (Phase 2は local簡易でもOK?)
2. **Fast Guard の常時稼働コスト** (Cloud Run e2-micro $5 vs Local無料 安全性は?)
3. **Stage 1 自動判断の閾値** (Equity 0.25% / レバ 2x で十分か)
4. **Shadow Model の昇格基準** (90日 walk-forward が長すぎないか、 30日でも可?)
5. **取引所選定**: Bybit主+Hyperliquid副 でいいか、 逆や別案あるか
6. **Phase 2 → Phase 3 移行条件** (Stage 1で何日何件のトレードを見れば移行GOか)

## 10. 次のアクション

- **A**: この設計叩き台を 3者会議 (Round 22+) に投げて本気監査+独自案
- **B**: Shujiさんに先にレビュー → 「ここを変えて」「これいらない」 を反映してから3者
- **C**: 直接実装開始 (Bybit testnet client から)

Claude推奨: **A** (3者の独自案を取り入れた方が結局速い、 前回も Gemini/GPT から重要な指摘が入った)
