# Phase 4 設計書 (叩き台) — マルチアセット運用 + 1脳25肉体 PBT + IQN+DRQN

作成: 2026-06-03 / 担当: Claude / 監査予定: GPT (司会) / Gemini (技術)

## 1. Phase 4 の位置づけ

```
Phase 1 (Day 1-14): 評価基盤 ✅
Phase 2 (Day 15-45): Live Stage 0-1 (BTC、 2x) ✅ 設計v2確定
Phase 3 (Day 46-160): Stage 2 (BTC、 3x、 再現性検証) ✅ 設計v2確定
Phase 4 (Day 161-240): BTC+ETH+SOL マルチアセット運用 + PBT本格化 ← 今回
Phase 5+ (Day 240+): 完全自律 + OKX + 自己資本複利
```

**Phase 4 の主目的**:
- Phase 3 で確認した「BTC単体の再現性」を **マルチアセット (ETH/SOL) に横展開**
- Round 24 Gemini指摘の「**1脳 + 25肉体**」PBT を本格実装
- **IQN+DRQN** で時系列文脈を組み込んだリスク見積もり
- **LLM Strategy Proposer Loop** で新戦略を AI自身が提案
- 運用資金 $1,500-2,250 → $4,500-8,000 (3倍)、 月利目標 +5-10%

## 2. ロードマップ (Day 161-240、 80日間)

```
Day 161-175 (Phase 4.1 ETH/SOL DNA構築):
├─ CryptoHayes / Arthur Hayes ポストを ETH DNA に
├─ Solana 大口クジラ・コアトレーダー ポストを SOL DNA に
└─ Vector Search に統合 (BTC danjer + ETH Hayes + SOL クジラ)

Day 176-190 (Phase 4.2 ETH/SOL Stage 1):
├─ Bybit ETHUSDT/SOLUSDT testnet → Live Stage 0 (Shuji承認)
├─ Live Stage 1 (最小ロット、 2x、 デイリー承認)
└─ Phase 2 v2 と同じゲート体系

Day 191-205 (Phase 4.3 1脳 + 25肉体 PBT 本格):
├─ Slow Brain (Gemini Pro Context Cache) 1つ常駐
├─ 25 数理肉体 worker (TTL/Half-Kelly/レジーム閾値の変異体)
└─ 月次淘汰+クロスオーバー+変異

Day 206-220 (Phase 4.4 IQN+DRQN リスク見積もり本番投入):
├─ Phase 3 で POC した QR-DQN を IQN+DRQN にアップグレード
├─ LSTM/Transformer 層で時系列文脈組み込み
└─ Order Gate に CVaR_95 等の分位点リスクを渡す

Day 221-235 (Phase 4.5 LLM Strategy Proposer Loop):
├─ 週次自動戦略生成 (Cloud Run 火曜深夜実行)
├─ 11ゲート検証 (CPCV/DSR/PSR/Trade-EHR/etc.)
├─ Shujiさん Slack 承認で実機投入
└─ 既存 25肉体に新戦略を追加 or 弱い肉体を置換

Day 236-240 (Phase 4.6 Phase 5ゲート判定):
├─ 60稼働日分の マルチアセット成績 集計
├─ 3者会議で Phase 5 GO/NO-GO
└─ 自己資本複利+OKX追加へ
```

## 3. 主要コンポーネント

### 3.1 multi_asset/ (Phase 3v2 の data_collectors を拡張)

```
multi_asset/
├── data_collectors/   ← Phase 3v2 で実装済
│   ├── binance_ohlcv.py
│   ├── bybit_oi_fr.py
│   └── coinglass_liquidation.py
├── dna/               ← Phase 4 新規
│   ├── eth_dna_builder.py    # Hayes 投稿 → ETH DNA
│   ├── sol_dna_builder.py    # Solana 大口 → SOL DNA
│   └── dna_merger.py         # BTC + ETH + SOL のサブDNAを動的マージ
├── normalizer.py
└── cross_asset_executor.py   # マルチアセット同時注文管理
```

**DNA構造** (Gemini Round 24 案採用):
```
[danjer_BTC_core] (リスク管理・ディフェンス) — 共通ベース
+ [hayes_ETH_core] (マクロ・FR・流動性) — ETH発注時オーバーレイ
+ [solana_whale_core] (オンチェーン・ミーム熱狂) — SOL発注時オーバーレイ
```

### 3.2 pbt/ (Phase 3v2 Lite から「1脳25肉体」に拡張)

Gemini Round 24 案を本格採用:

```
pbt/
├── slow_brain_singleton.py     # LLM (Gemini Pro Context Cache) 1つだけ常駐
├── numerical_worker.py         # 数理パラメータ 個体 (TTL/Half-Kelly/レジーム閾値)
├── population_manager.py       # 25 worker 管理、 月次淘汰
├── mutation.py                 # パラメータ突然変異
├── crossover.py                # 親worker から子worker 生成
└── tests/
```

**25肉体のハイパラ多様化**:
- Slow Brain TTL (5/10/15/20/30 分の中から)
- Half-Kelly 係数 (0.3/0.4/0.5/0.6/0.7)
- レジーム ATR period (10/14/20)
- ガード減算重み (Liquidation/MaxDD/NoStop の係数)
- noop ペナルティ閾値

**月コスト** (Gemini指摘「1脳ハック」採用):
- 全25肉体が同じ Slow Brain Cache を共有 → LLMコスト 25倍にならない
- 数理worker のみ並走 (各 CPU 軽量、 Cloud Run e2-micro 1台で複数 worker実行可)
- → 月 $30-80 で 25肉体並走可能 (vs 25LLM並走なら $750+)

### 3.3 iqn_drqn/ (Phase 3v2 QR-DQN POC からアップグレード)

```
iqn_drqn/
├── network.py          # PyTorch IQN + LSTM/Transformer
├── replay_buffer.py    # 時系列を保持する episodic buffer
├── trainer.py          # CPCV-aware 訓練
├── inference.py        # 分位点リスク (CVaR_95) を Order Gate に
└── tests/
```

**IQN vs QR-DQN の違い** (Geminiの指摘採用):
- QR-DQN: 固定数の分位点 (例: 200) を学習
- **IQN**: 連続分位点 (任意の τ ∈ [0,1] でクエリ可)、 ファットテール対応に強い
- + DRQN (LSTM): 時系列文脈を 保持、 BTCのレジーム変動に追従

**機材**: GPU Spot A100 × 週2回 (1h各) = $12-30/月

### 3.4 strategy_proposer/ (Phase 4.5 LLM Strategy Proposer Loop)

```
strategy_proposer/
├── weekly_proposer.py      # 火曜深夜 Cloud Run trigger
├── analysis_engine.py      # 先週の負けトレード分析
├── new_strategy_generator.py  # Gemini Pro で新コード生成
├── eleven_gate_validator.py   # 11ゲート検証
├── slack_approval.py       # Shuji 承認待ち
└── tests/
```

**11ゲート検証** (Round 1-10 で議論済):
1. CPCV passing
2. Deflated Sharpe > threshold
3. PSR > threshold
4. PBO < threshold
5. Trade-EHR が baseline超え
6. 最大DD 制限内
7. Slippage 想定内
8. レジーム別致命弱点なし
9. SL未設置率 0
10. Explainability OK
11. 月額API追加コスト < $50

11ゲート全通過 → Shujiさん Slack 承認 → 25肉体に追加 or 既存弱体置換

### 3.5 cross_asset_monitor/ (Phase 3v2 から運用拡張)

```
cross_asset_monitor/
├── correlation_tracker.py    # BTC/ETH/SOL 30日相関、 既存
├── pair_trading_signals.py   # 比率 RSI、 統計的裁定
├── liquidation_cascade_detector.py  # R47 強化: マルチアセット同時清算検知
└── tests/
```

## 4. リスク追加 R54-R60 (Phase 4 想定)

| # | リスク | 対策 |
|---|---|---|
| R54 | ETH/SOL DNA構築失敗 (Hayes/クジラポスト不足) | 最低500件/アセット確保、 不足ならPhase 4遅延 |
| R55 | マルチアセット同時清算 (R47本格化) | Fast Guard 数理レイヤーで圧縮済イベント→Slow Brain (Gemini Round 24) |
| R56 | 25肉体 同時バグ拡散 | 全肉体に decision_trace_id、 弱体は paper only、 本番投入は段階的 |
| R57 | IQN+DRQN 訓練データ不足 | Phase 3 paper + Live Stage 2 のデータ蓄積、 60日後にトレーニング |
| R58 | LLM Strategy Proposer のhallucination | 11ゲート + Shuji承認 + 1ヶ月paper monitoring 必須 |
| R59 | Phase 4 月コスト爆発 (拡張で予算超過) | 各成果物の予算上限を設定、 超えたら機能凍結 |
| R60 | OKX/3取引所連携で API互換性問題 | Phase 4 はBybit+Hyperliquid のみ、 OKXは Phase 5 |

## 5. コスト見積もり (Phase 4 月次)

### 固定費
| サービス | 月額 |
|---|---|
| Cloud Run slow-brain (Min=1、 1脳共有) | $10-15 |
| Cloud Run fast-guard (常駐) | $5-10 |
| Cloud Run 25肉体 worker (e2-micro × 数台) | $10-30 |
| Cloud Run Strategy Proposer (週1trigger) | $0-2 |
| BigQuery Storage (3アセット×OHLCV他) | $15-30 |
| Cloud Storage | $5-15 |
| **固定費合計** | **$45-102** |

### 変動費
| サービス | 月額 |
|---|---|
| Gemini クエリ (15分毎、 1脳共有) | $20-40 |
| Vertex AI Vector Search (BTC+ETH+SOL DNA) | $30-60 |
| BigQuery query | $10-30 |
| GPU Spot (IQN+DRQN 週2回) | $12-30 |
| 取引手数料 (BTC + ETH + SOL Stage 2) | $20-80 |
| LLM 戦略提案 (週1、 1回 $1-3) | $4-12 |
| **変動費合計** | **$96-252** |

**Phase 4 月額合計: $141-354**

3者会議 Round 10 合意 ($350) と一致。 Shujiさん予算 $135-400 内。

## 6. 運用資金推移 (Phase 4)

```
Day 161 (Phase 4 開始): $1,500-2,250 (Phase 3 持ち越し)
Day 175 (ETH/SOL Stage 0 開始): + $50-100 (paper)
Day 190 (ETH/SOL Stage 1):    + $100-200 (実弾)
Day 220 (PBT 25肉体本格):     + Trade-EHR次第で 0.5-2倍
Day 240 (Phase 5 移行ゲート):  $4,500-8,000
```

## 7. Phase 5 移行ゲート (Day 240)

- Phase 4 で 60稼働日達成
- 3アセット (BTC/ETH/SOL) 全てで Trade-EHR > baseline
- 累計DD < 20%
- 25肉体中 10体以上が継続的に勝ち越し
- LLM Strategy Proposer から1つ以上 採用済 (実機投入)
- 月コスト $350 以内に収まる
- 重大事故 0 (取引所障害除く)
- Shujiさん監督負荷が低水準 (週1サマリーレビューだけで運用回る)

## 8. Phase 5+ (Day 240+) 概要 — Phase 4設計書では概要のみ

- OKX追加 (3取引所障害退避)
- BNB追加、 SOL Stage 2 へ
- **完全自律 Demotion** (ミリ秒、 非対称設計): 悪い個体・戦略は即座に paper降格、 昇格は段階的
- ファンド化禁止、 **自己資本のみで合法的ヘッジファンド化** (Shujiさん個人運用)
- 月コスト $400 (Round 10 合意)

Phase 5+ 設計書は Phase 4 終盤 (Day 230頃) に別途作成。

## 9. 3者会議で議論したい論点 (Round 26+ で投げる)

1. **ETH/SOL DNA: Hayes/Solanaクジラ ポストの法的扱い** (R17 SNSデータ権利との関係)
2. **1脳25肉体 の同期/非同期**: 各肉体が同時に Slow Brain呼ぶ vs 順番制
3. **IQN+DRQN 訓練データ量**: Phase 3 60日分で十分か、 過去2年のbacktest data merge要か
4. **LLM Strategy Proposer の信頼性**: GPT-5 vs Gemini Pro vs Claude Opus どれが提案精度高いか
5. **Phase 5 移行条件**: 25肉体中10体勝越し は厳しすぎないか
6. **マルチアセット運用での Shujiさん監督疲れ**: 3アセット同時で承認件数が3倍にならないか

## 10. 次のアクション

- **A**: 3者会議 (Round 26+) で Phase 4 監査
- **B**: Shujiさんに先にレビュー
- **C**: 実装は Phase 2 testnet 完了+Phase 3 Stage 2 達成後なので、 当面は概念設計止め

Claude推奨: **A** (前回 Round 22/24 で重要発見が出た。 Phase 4 も同様に「拡張しすぎ」「コスト見落とし」が出る可能性大)
