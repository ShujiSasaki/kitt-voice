# Phase 3 設計 v2 — Round 24 監査反映+Shujiさん指示 (A路線)

更新: 2026-06-03 (Round 25 Claude実装案)

## Shujiさん指示 (verbatim)
> Phase 3 を **「BTC単体で Stage 2 少額Live の投資効率と安全性を確認するフェーズ」** と位置づける。 ETH/SOL・PBT・QR-DQN は補助実験として段階導入。

## v1 → v2 主要変更 (Round 24 反映)

| # | 旧 (v1) | 新 (v2) | 出典 |
|---|---|---|---|
| 1 | レバ 2x→3x 自動解除 | **Shujiさん承認1回必須** | GPT |
| 2 | PBT 20-30体並走 | **PBT Lite 5体 (POC)** | GPT |
| 3 | QR-DQN本格実装 | **QR-DQN POC のみ (リスク見積もり実験)** | GPT |
| 4 | ETH/SOL 取引対象 | **データ収集のみ、 取引対象外 (Phase 4以降)** | GPT+Shuji |
| 5 | マルチアセット運用 (Phase 3.5) | **Phase 4 へ持ち越し** | GPT+Shuji |
| 6 | 月利+5%未達でPhase 4断念 | **撤回。 多軸判定** (Trade-EHR/DD/事故0/監督負荷) | GPT |
| 7 | Context Cache 32K件常駐 | **Vector Search 移行 + Cache は概念ルール群+24h ローカル** | Gemini |
| 8 | R43-R50 | **+R51-R53 追加** (スコープクリープ/KPIハック/説明不能化) | GPT |

## 1. Phase 3 v2 ロードマップ (Day 46-160、 主目的: BTC単体 Stage 2 再現性検証)

```
Day 46-60 (Phase 3.1 Stage 2 移行):
├─ Live Stage 1 達成ゲート確認 (Phase 2 v2 Gate C)
├─ レバ 2x→3x への解除 (Shujiさん承認1回)
└─ 最初の7日は 2.5x 上限で安全運転、 段階的に 3.0x

Day 61-90 (Phase 3.2 BTC再現性検証):
├─ Stage 2 で連続30日運用
├─ Trade-EHR / DD / 事故率 / 監督負荷 を多軸で記録
└─ 異なる相場レジーム (上昇/下降/横ばい/急変) 全て経験

Day 91-120 (Phase 3.3 補助実験):
├─ シンプルアンサンブル (LightGBM + TimesFM + LLM) の重み学習
├─ PBT Lite 5体 (既存判断器のハイパラ変異だけ)
└─ QR-DQN POC (リスク見積もり実験、 本番未投入)

Day 121-150 (Phase 3.4 補助データ収集、 取引なし):
├─ ETH/SOL OHLCV/OI/FR をBQに収集
├─ BTC との相関監視 (paper 専用、 売買禁止)
└─ Phase 4 マルチアセット用ベースデータ蓄積

Day 151-160 (Phase 3.5 Phase 4 ゲート判定):
├─ 60稼働日分の Trade-EHR/DD/事故/監督負荷 集計
├─ 3者会議でPhase 4 GO/NO-GO判断
└─ Shujiさん最終承認
```

## 2. Stage 2 移行ゲート (GPT Round 24 案を厳格採用)

```
Phase 2 v2 Gate C (Stage 2 移行) — 必須条件:
- Live Stage 1 最低 20稼働日 (v1の10日から増加)
- 最低 20実弾トレード (v1の10件から増加)
- SL未設置 0件
- Order Gate違反 0件
- Fast Guard不作動 0件
- 日次DD 1.5% 超え 0回
- 最大連敗後のレバ縮小 が正常動作
- Trade-EHRが paper baseline から大きく劣化なし
- **Shujiさん承認1回必須** (完全自動 NO-GO)
```

## 3. コンポーネント変更 (v1からスリム化)

### 残す
- `multi_asset/data_collectors/` — ETH/SOL OHLCV/OI/FR 収集のみ (取引対象外)
- `cross_asset_monitor/correlation_tracker.py` — paper追跡のみ

### POC化 (Phase 3 では本格実装しない)
- `pbt/` — Lite 5体 (Slow Brain は1つ、 数理パラメータだけ変える)
- `qr_dqn/` — リスク見積もり実験のみ、 本番Order Gateには **未投入**

### Phase 4 に持ち越し
- マルチアセット運用ロジック
- ETH/SOL 個別 DNA (Hayes/Solana大口) 構築
- PBT 20-30体並走
- IQN+DRQN 高度化

## 4. R43-R53 リスク (v2 統合版)

| # | リスク | 対策 |
|---|---|---|
| R43 | レバ3x過剰自信 | 最初7日は 2.5x 上限、 段階的解除 |
| R44 | ETH/SOL データ品質 | 3ソース突合 (Binance+Bybit+Coinglass) |
| R45 | PBT Lite 5体相関同期 | 個体毎に乱数seed/学習windowを変える |
| R46 | QR-DQN POC過学習 | CPCV + DSR で実機投入判断 |
| R47 | マルチアセット同時清算 | **Phase 4まで取引対象外なので Phase 3 ではpaper追跡のみ** |
| R48 | 資金規模拡大時の流動性影響 | 1注文サイズ上限「板厚 × 5%以下」 |
| R49 | PBT計算コスト爆発 | **5体限定、 Slow Brain 1つ共有** (Gemini指摘の "1脳"部分採用) |
| R50 | 自律時 Shuji応答失敗 | 完全自律モードでもL2は朝デイリー承認、 L3/L4は5分以内応答必須 |
| **R51** | **Phase 3 スコープクリープ** | **主目的を「BTC単体再現性検証」に絞る、 補助実験は明示的に格下げ** |
| **R52** | **KPIハック** | Trade-EHR単独評価禁止、 DD/事故/説明不能/監督負荷をゲート、 月利+5%を断念条件にしない |
| **R53** | **モデル複雑化 説明不能** | 全注文に「どの判断器/danjer類似/レジーム/リスク見積/レバ理由/SL-TP理由」を必須記録 |

## 5. コスト見積もり v2 (慎重構成、 GPT試算採用)

### 固定費 (Phase 2v2 + 増分)
| サービス | 月額 |
|---|---|
| Cloud Run slow-brain (Min=1) | $10-15 |
| Cloud Run fast-guard | $5-10 |
| Cloud Storage (ETH/SOL paper追跡) | $5-10 |
| BigQuery Storage | $5-15 |
| **固定費合計** | **$25-50** |

### 変動費
| サービス | 月額 |
|---|---|
| Gemini クエリ (15分毎、 1脳共有) | $10-30 |
| Vertex AI Vector Search | $20-40 |
| BigQuery query | $5-15 |
| GPU Spot (QR-DQN POC週次訓練) | $6-15 |
| 取引手数料 (Stage 2 BTC) | $5-20 |
| **変動費合計** | **$46-120** |

**Phase 3 v2 月額合計: $71-170**

3者会議 Round 10 合意 ($195) より低く、 Shujiさん予算 $135-400 に **大幅余裕**。

## 6. Phase 4 移行ゲート (Day 161、 GPT案採用)

| 条件 | GO基準 |
|---|---|
| Live Stage 2 稼働日数 | 最低 30日 |
| 最低実弾トレード | 30件 |
| Trade-EHR | baseline (Phase 2平均) 超え |
| 最大DD | 許容内 (例: 累計15%以内) |
| SL未設置 | 0 件 |
| Order Gate違反 | 0 件 |
| Fast Guard重大事故 | 0 件 |
| レジーム別致命的弱点 | なし |
| Shujiさん朝サマリーで判断追える | yes |

**断念条件** (Phase 3 で打ち切る判断):
- Trade-EHR が継続的に baseline未満
- 最大DD超過
- 事故/誤発注 (重大)
- 説明不能判断の増加
- Shujiさんの承認/監督負荷が高すぎる

月利+5%は **目標値**、 断念条件ではない。

## 7. Geminiの提案 (Phase 4以降に持ち越し)

Round 24 Gemini指摘で Phase 3 v2 に **反映しなかった** 提案 (Phase 4以降で再検討):

- **「1脳+25肉体」 PBT**: Phase 3 では Slow Brain 1つ + 数理 5肉体 に縮小。 Phase 4 で 25肉体に拡張可
- **IQN+DRQN 格上げ**: Phase 3 は QR-DQN POC、 Phase 4 で IQN+DRQN 検討
- **ETH/SOL 別 DNA (Hayes等)**: Phase 4 で マルチアセット運用開始時に CryptoHayes / BobLoukas / Solana 大口クジラの DNA構築

これらは **Phase 4設計書** で正式議論。

## 8. Vertex AI Vector Search 移行 (Gemini指摘採用、 Phase 2.5 と統合)

Phase 2.5 で keep_alive が確立済。 Phase 3 では:
- danjer DNA 全32,000件 (Anthropic Batch+既存17,650件 統合済) → Vertex AI Vector Search に**完全移行**
- Context Cache は「danjer 思考の普遍的コア (50パターン抽出)」+「直近24h ローカル市場context」 のみ (約10万tokens)
- Cache サイズを 70-80万 → 10万tokens に **88% 削減**
- 月コスト Gemini Cache: $20-40 → **$5-15**

## 9. 3者会議で確認したい点 (Round 26 用、 任意)

GPT/Gemini で 1点だけ意見が割れて未解決:

> **PBT 設計**: GPT「Phase 3 は **シンプルアンサンブル優先** 、 PBT Lite 5体は実験のみ」 vs Gemini「**1脳+5肉体** の PBT (数理多様化) で開始してもいい」

Claudeとしては GPT案優先 (シンプルアンサンブル → PBT Lite) で v2 を確定。 Phase 4 で「1脳+25肉体」を検討。

## 10. 次のアクション

- **A**: Shujiさんが v2 を確認 → Round 26 でGPT/Geminiに最終承認求めるか、 直接 Phase 3 完了
- **B**: Phase 4 設計叩き台に進む (Phase 3 v2 確定として)
- **C**: v2 にさらに修正 (具体的に指示)

Claudeとしては **Phase 3 v2 はShujiさん指示完全準拠** なので、 Round 26 は省略可。 直接 Phase 4 設計や、 Embedding完了待ち+Bybit testnet 着手に進める。
