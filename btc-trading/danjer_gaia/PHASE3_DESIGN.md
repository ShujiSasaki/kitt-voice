# Phase 3 設計書 (叩き台) — Stage 2 自動運用+多通貨拡張+PBT+QR-DQN

作成: 2026-06-03 / 担当: Claude (実装担当) / 監査予定: GPT (司会) / Gemini (技術)

## 1. Phase 3 の位置づけ

3者会議 Round 10 合意:

```
Phase 1 (Day 1-14): 評価基盤・danjer DNA・レジーム・TTL/Stance ✅
Phase 2 (Day 15-45): 紙トレ + Live Stage 0-1 ($15-50、 2x)
Phase 3 (Day 46-160): Stage 2 自動運用 (3xレバ) + 多通貨データ収集 ← 今回
Phase 4 (Day 161-240): BTC+ETH+SOL マルチアセット
Phase 5+ (Day 240+): 完全自律 + OKX追加 + ファンド化
```

Phase 3 の目的:
- Phase 2 Live Stage 1 で 「動く土台が実環境で稼ぐ」 を確認した後の **拡大フェーズ**
- レバ上限を 2x → 3x に解除 (自律で)
- 資金 $15-50 → $250-2,250 (15倍前後)
- AI個体を 1体 → 20-30体 (PBT) に並走
- ETH/SOL のデータ収集開始 (Phase 4 への準備)
- リスク見積もりを QR-DQN で精緻化

## 2. Phase 3 ロードマップ (Day 46-160、 115日間)

| Day | 段階 | 内容 | 元手 | レバ |
|---|---|---|---|---|
| 46-60 | **Phase 3.1 Stage 2 移行** | レバ 2x → 3x 自動解除 (Gate D 達成後) | $150-300 | 〜3x |
| 61-75 | **Phase 3.2 ETH/SOL データ収集** | Bybit/Binance/Coinglass API で OHLCV/OI/FR/清算 1分足 過去2年分 | 同 | 同 |
| 76-90 | **Phase 3.3 PBT 多個体並走** | AI個体を 1 → 20-30体に拡大、 月次淘汰+クロスオーバー | $500-1,500 | 〜3x |
| 91-120 | **Phase 3.4 QR-DQN リスク見積もり** | リスク予測を点予測→分位回帰 (QR) で確率分布化 | $1,000-2,000 | 〜3x |
| 121-160 | **Phase 3.5 マルチアセット準備** | ETH/SOL の paper運用、 BTC/ETH/SOL相関監視、 Phase 4移行ゲート | $1,500-2,250 | 〜3x |

## 3. Stage 2 移行条件 (Gate D)

3者会議 Round 22 GPT合意の Phase 3移行条件:
```
Paper: 10稼働日 + 50判断 + 20 paper trade + 重大バグ0 + SL未設置0 + Order Gate違反0
Live Stage 0: 5稼働日 + 全件Shuji承認 + 全ログ正常 + 通知遅延/誤通知0
Live Stage 1: 10稼働日 + 10実弾 + 自律L0のみ + 1トレ損失0.25%以内 +
             日次DD<1.5% + Fast Guard誤作動0 + Trade-EHR noop加算後もプラス
```

Phase 3 開始 = Gate D 達成後の自動移行。 Shujiさん承認1回のみ (詳細は実装データで判断)。

## 4. コンポーネント設計

### 4.1 multi_asset/ (Phase 3.2 ETH/SOL データ収集)

```
multi_asset/
├── data_collectors/
│   ├── binance_ohlcv.py        # ETH/SOL 1分足 過去2年 (Binance Public API)
│   ├── bybit_oi_fr.py          # OI / FR / 清算
│   └── coinglass_liquidation.py # 集約清算データ
├── normalizer.py                # 銘柄別正規化 (BTC比較用)
└── tests/
```

**新規 BQ テーブル**:
```sql
CREATE TABLE btc_trading.eth_klines (...) PARTITION BY DATE(timestamp);
CREATE TABLE btc_trading.eth_snapshots (...);
CREATE TABLE btc_trading.sol_klines (...);
CREATE TABLE btc_trading.sol_snapshots (...);
CREATE TABLE btc_trading.cross_asset_correlation (BTC/ETH/SOL 相関 daily);
```

**コスト**: BQ追加 $5-10/月、 データ収集APIは無料 (Binance Public)

### 4.2 pbt/ (Phase 3.3 Population Based Training)

```
pbt/
├── individual.py                # 個体 (config + state)
├── population_manager.py        # N体管理、 月次淘汰+クロスオーバー
├── evaluation.py                # 個体評価 (Trade-EHR + CPCV)
├── mutation.py                  # ハイパラ突然変異
└── tests/
```

**仕様** (3者会議 Round 5 GPT提案):
- 初期: 3-4体 (Phase 1 個体 + 派生3体)
- Day 76: 20体に拡大
- Day 121: 30体に拡大 (Phase 4で100体予定)
- 月次淘汰 (Trade-EHR下位 1/3を捨てて、 上位個体のクロスオーバー+変異で補充)
- 各個体は paper環境で独立に走る

**異なるハイパラ**:
- Slow Brain TTL (5分/15分/30分)
- レバ上限 (2x/3x/5x)
- Half-Kelly 係数 (0.3/0.5/0.7)
- レジーム判定 ATR period (10/14/20)
- ガードペナルティ重み

### 4.3 qr_dqn/ (Phase 3.4 リスク見積もり)

```
qr_dqn/
├── network.py                   # PyTorch QR-DQN モデル
├── replay_buffer.py             # Experience replay
├── trainer.py                   # 訓練ループ
├── inference.py                 # 推論 (Slow Brain にリスク分布を提供)
└── tests/
```

**仕様**:
- 入力: 市場状態 + Stance + 候補 action
- 出力: 各 action のリターン分位点 (P10, P25, P50, P75, P90)
- リスク評価で「最悪シナリオ」 (CVaR_95) を Order Gate に渡す
- 訓練データ: 過去 paper + Stage 0/1 実弾結果

**機材**:
- A100 Spot 1h/週 ($6/月) で訓練
- 推論は Cloud Run + CPU で十分 (軽量モデル)

### 4.4 cross_asset_monitor/ (Phase 3.5 マルチアセット監視)

```
cross_asset_monitor/
├── correlation_tracker.py       # BTC/ETH/SOL 30日相関
├── pair_trading_signals.py      # BTC/ETH 比率の RSI 等
├── alt_regime.py                # ETH/SOL 別レジーム判定
└── tests/
```

## 5. リスク追加 R43-R50 (Phase 3 想定)

| # | リスク | 対策 |
|---|---|---|
| R43 | レバ 3x 解除直後の過剰自信 | Stage 2 移行直後7日は **2.5x 上限**、 段階的に 3.0 へ |
| R44 | ETH/SOL データ品質 (古い時期欠損) | Binance + Bybit + Coinglass 3ソース突き合わせ |
| R45 | PBT 全個体相関同期 | 個体毎に乱数seedを変える、 学習データの window を変える |
| R46 | QR-DQN 過学習 | CPCV + Deflated Sharpe で個体採用判断 |
| R47 | マルチアセット同時清算 (R37 拡張) | 各アセット個別 Mark Price + 連動清算検知 → 全閉 |
| R48 | 資金規模拡大時の流動性影響 | 1注文サイズ上限を「板厚 × 5%以下」 |
| R49 | PBT 個体爆発による計算コスト | 個体並走は最大30体、 古い個体は paper のみ |
| R50 | Phase 3 で Shuji が忙しい時の手動介入失敗 | 完全自律モード時の Slack 5分以内応答必須 (応答なし→halt) |

## 6. コスト見積もり (Phase 3 月次)

### 固定費
| サービス | Phase 2 → Phase 3 |
|---|---|
| Cloud Run (slow-brain Min=1) | $5-10 → $10-15 (PBT で増加) |
| Cloud Run (fast-guard 常駐) | $5-10 → $10-20 |
| Cloud Storage | $2-5 → $5-15 (ETH/SOL データ) |
| BigQuery Storage | $2-5 → $10-25 (3アセット) |

### 変動費
| サービス | Phase 2 → Phase 3 |
|---|---|
| Gemini クエリ (PBT 30体 × 15分間隔) | $5-30 → $30-80 |
| Vertex AI Vector Search | $20-40 → $30-60 |
| BigQuery query | $2-10 → $10-30 |
| GPU Spot (QR-DQN週次訓練) | $6-15 → $15-30 |
| 取引手数料 (Stage 2 多取引) | $1-5 → $20-80 |

**Phase 3 月額合計: $148-378**

3者会議 Round 10 合意 Phase 3 月コスト = $195 はやや楽観。 現実 $150-380 で見るべき。
Shujiさん予算 $135-400 内ではあるが、 上限に近い。

## 7. Phase 4 移行ゲート (Day 161 想定)

Phase 4 (BTC+ETH+SOL マルチアセット運用) 移行条件:
- Phase 3 で 60稼働日達成
- 累計 Trade-EHR が paper基準より +10% 以上
- 重大事故0 (取引所障害除く)
- ETH/SOL の paper環境で安定動作 (Trade-EHR プラス)
- 月コスト $200以内に収まる (実測)
- PBT 30体中 5体以上が継続的に勝ち越し

## 8. 3者会議で議論したい論点 (Round 24+ で投げる)

1. **Stage 2 への自動移行**: Gate D 達成後 Shuji承認 1回必要か、 完全自動か
2. **PBT 個体数**: 20-30体は Phase 3 で多すぎないか? 5-10体から始めるべきか
3. **QR-DQN の代替**: PPO の分位回帰版 (IQN) の方がBTC向けか
4. **ETH/SOL データソース**: Binance Public 無料 vs Bybit 有料の信頼性
5. **PBT vs アンサンブル**: 個体並走でなく モデルアンサンブル (LightGBM + TimesFM + LLM) の重み学習だけでも十分か
6. **Phase 3 完了の経済的判定**: 月利 +5% を超えなければ Phase 4 移行を断念するか

## 9. 実装着手順 (Phase 3)

| 順 | 作業 | 推定 |
|---|---|---|
| 1 | 3者会議 Round 24+ で本気監査 | 30min |
| 2 | Phase 3 v2 確定 (Round 22同様の修正反映) | 1h |
| 3 | Day 46-60: Stage 2 移行+3xレバ解除自動化 | 3日 |
| 4 | Day 61-75: ETH/SOL データ収集スクリプト | 5日 |
| 5 | Day 76-90: PBT 個体並走基盤 | 7日 |
| 6 | Day 91-120: QR-DQN 訓練+推論 | 14日 |
| 7 | Day 121-160: マルチアセット paper運用 | 28日 |

## 10. 次のアクション

- **A**: 3者会議 (Round 24+) に投げて Phase 3 設計を本気監査
- **B**: Shujiさんに先にレビュー → 修正 → 3者
- **C**: 直接実装開始 (Stage 2 自動移行ロジックから)

Claude推奨: **A** (前回 Round 22 で Cache 自然死問題等の重要指摘を3者から取れた)
