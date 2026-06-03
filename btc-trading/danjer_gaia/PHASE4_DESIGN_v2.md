# Phase 4 設計 v2 — Round 26 監査反映版

更新: 2026-06-03 (Claude Round 27、 GPT 3レーン制+Gemini 技術深掘り 全反映)

## v1 → v2 主要変更

| # | 旧 (v1) | 新 (v2) | 出典 |
|---|---|---|---|
| 1 | 単一レーン (全部本番投入) | **3レーン制 (Production / Research / Governance)** | GPT |
| 2 | ETH/SOL 同時 Stage 1 | **ETH Stage 1候補 / SOL Stage 0中心** | GPT |
| 3 | PBT 25肉体 本番投入 | **paper/Shadow のみ、 Live発注権限なし** | GPT |
| 4 | IQN+DRQN 本番リスク見積もり | **Risk Estimator限定 (本番Order Gate投入は Phase 5)** | GPT |
| 5 | LLM Strategy Proposer 単一モデル | **Gemini提案/GPT監査/Claude実装の分業** | GPT |
| 6 | 個別注文承認 (3アセット同時) | **方針承認制 (朝の方針セット一括)** | GPT |
| 7 | Hayes/Solanaクジラ DNA 名そのまま | **市場テーマ別コード名** (macro_perp_view / onchain_whale_pattern) | GPT (R62) |
| 8 | コスト $141-354 | **現実レンジ $180-450** | GPT |
| 9 | R54-R60 | **+R61-R63 追加** (相関過小/個人名/Proposer複雑化量産) | GPT |
| 10 | IQN 固定 ε | **動的 ε-greedy (BTC非定常性追従)** | Gemini |
| 11 | DNA テキストのみ | **+オンチェーン DNA** (Etherscan/SolScan API) | Gemini |
| 12 | LLM Proposer 自由生成 | **sandbox 実行+import whitelist** | Gemini |

## 1. Phase 4 v2 ロードマップ (3レーン制)

```
Production レーン (実弾、 Shujiさん監督):
├─ Day 161-180: BTC Stage 2 継続 (Phase 3v2 から自然継続)
├─ Day 181-200: ETH Stage 0→Stage 1候補 (小ロット paper先行)
└─ Day 201-240: SOL Stage 0 のみ (paper のみ、 実弾は Phase 5以降)

Research レーン (paper/Shadow only、 Live発注権限なし):
├─ Day 161-190: ETH/SOL DNA構築 (市場テーマ別、 オンチェーン併用)
├─ Day 191-210: 1脳25肉体 PBT paper運用
├─ Day 211-230: IQN+DRQN Risk Estimator のみ (Order Gate未投入)
└─ Day 221-235: LLM Strategy Proposer Loop (paper検証のみ、 Phase 5で本番)

Governance レーン (Shujiさん監督負荷 KPI化):
├─ 週次レビュー時間 < 1時間
├─ 1日承認件数 < 5件 (デイリー方針承認のみ)
├─ 通知頻度: L0自律/L1注意/L2方針承認 (1日1回)/L3-L4緊急のみ
└─ Day 236-240 Phase 5 ゲート判定 (3者会議+Shujiさん最終承認)
```

## 2. 3レーン制 詳細

### Production レーン

- **BTC**: Stage 2 (Phase 3v2 で確立) を継続。 レバ最大 3x
- **ETH**: Phase 4で初投入。 Day 181 から Stage 0 (Shujiさん全件→デイリー承認)、 Gate B 達成で Stage 1 (最小ロット自動)
- **SOL**: paper のみ、 実弾は Phase 5以降
- すべて **方針承認制** (個別注文ではなく、 朝の方針セット 「BTC LONG bias / ETH WAIT / SOL なし」 を1日1回承認)

### Research レーン (paper/Shadow 専用)

- PBT 25肉体: paper環境で並走、 上位3体だけ Production への昇格候補
- IQN+DRQN: Risk Estimator のみ、 Order Gate には 「参考スコア」 として渡すが拒否権なし
- LLM Strategy Proposer: 週次新戦略を生成、 11ゲート+人間レビュー、 採用後 paper 2週間 → Stage 0扱い

### Governance レーン

- **監督負荷 KPI**:
  - 週次レビュー時間 < 1時間 (Shujiさんが朝サマリーを読む時間)
  - 1日承認件数 < 5件 (方針承認 数件 + 緊急対応0-1件)
  - 通知頻度: L0自律 / L1注意 / L2方針承認 (1日1回) / L3-L4緊急のみ
- KPI超過時: Research レーンの拡張を凍結

## 3. ETH/SOL DNA構築 (Round 26 反映)

### 名称: 市場テーマ別 (個人名禁止、 R62対策)

```
[btc_core]           — 共通リスク管理ベース (Phase 1-3 で確立)
[macro_perp_view]    — マクロ・FR・流動性視点 (元 Hayes アプローチ)
[onchain_whale]      — 大口アドレス追跡 (Etherscan/SolScan API)
[memecoin_cycle]     — ミーム熱狂サイクル (SOL特化)
```

### データソース

- **macro_perp_view**: CryptoHayes (3,656件 SQLite x_tweets.db) + 公開Substack (内部参照のみ)
- **onchain_whale**: Etherscan API (ETH大口アドレス上位100)、 SolScan API (Solanaクジラ追跡)、 Glassnode (もしShujiさんが既存契約)
- **memecoin_cycle**: 2024-2026 SOL ミーム熱狂時の価格パターン+トレーダー反応

### 法的扱い (R17/R62 対策)
- 内部分析参照のみ。 公開資料・再配布・モデル学習用データセット化禁止
- DNA名は **コード名** (Hayes 等の個人名を使わない)
- 投稿全文は内部DB保管、 引用は分析時の最小限

## 4. 1脳25肉体 PBT (Round 26 統合)

### 構造 (Gemini Round 24 + Round 26 統合)

```
Slow Brain (Gemini Pro Context Cache) ← 1つ常駐
    │
    ▼ (同じ Stance を broadcast)
[25肉体 worker]
    ├─ 各 worker は数理ハイパラ (TTL/Half-Kelly/レジーム閾値/ガード重み) が異なる
    ├─ paper 環境で並走、 Trade-EHR 評価
    ├─ Cloud Run e2-micro × 数台で並走 (Geminiメモリ管理)
    └─ 月次淘汰+クロスオーバー+変異
```

### 本番昇格条件 (GPT Round 26)
- 上位3体のみ Live候補
- 各候補は paper 30日連続勝越し+相関0.7未満
- Shujiさん承認1回で Stage 0 から開始

## 5. IQN+DRQN Risk Estimator (本番Order Gate投入は Phase 5)

### Phase 4 での扱い: **参考スコアのみ**

- Order Gate 6ステップ通過後、 IQN+DRQN の CVaR_95 を「参考スコア」として表示
- スコアが極端に悪い (例: VaR_95 < -5% Equity) → Shuji 通知だが拒否権なし
- Phase 4 で 60日データ蓄積後、 Phase 5 で本番Order Gate へ昇格

### Gemini 動的 ε-greedy
```python
# レジームに応じて ε を変更
def adaptive_epsilon(current_regime, base_epsilon=0.1):
    if current_regime in ('storm_up', 'storm_down'):
        return base_epsilon * 0.5  # 高ボラ時は探索を抑える
    elif current_regime in ('calm_up', 'calm_down'):
        return base_epsilon * 1.5  # 低ボラ時は探索を増やす
    return base_epsilon
```

## 6. LLM Strategy Proposer Loop (Round 26 分業案)

### モデル分業

```
[提案レーン] Gemini 3.1 Pro
    ↓ 新戦略コード生成 (週次、 火曜深夜)
[監査レーン] GPT-5
    ↓ 論理矛盾、 過学習、 リスクをレビュー
[実装レーン] Claude Opus 4.7
    ↓ コード化可能性、 テスト可能性、 例外処理レビュー
[11ゲート] CPCV/DSR/PSR/PBO/EHR/MaxDD/Slippage/レジーム/SL/Explainability/コスト
    ↓ 全通過
[Shujiさん承認]
    ↓
[Paper 2週間]
    ↓ 事故0
[Stage 0 扱い → 段階昇格]
```

### Gemini sandbox 制約 (Round 26)
- 生成コードは sandbox 実行 (Cloud Run 隔離環境)
- File system / 外部 API アクセス禁止
- Import whitelist: `numpy`, `pandas`, `numpy.typing`, `dataclasses`, `typing` のみ
- danjer_gaia パッケージへの readアクセスはOK

## 7. 監督負荷 KPI (Round 26 GPT 最重要発見)

### 個別注文承認 → 方針承認制

**悪い例** (v1):
```
朝7:00: BTC LONG 0.001 承認?
朝7:15: ETH WAIT
朝7:30: BTC TP更新承認?
朝8:00: SOL paper結果 通知
...
```

**良い例 (v2)**:
```
朝7:00: 本日の方針セット (Slack DM)
- BTC: LONG bias 推奨 (3候補、 Equity 0.5%以内、 自動可)
- ETH: WAIT (高ボラ低確信)
- SOL: paper only
[✅ 全承認] [🎯 BTCのみ] [❌ 全却下]
```

→ 1日1回の承認で 3アセット分が片付く

### KPI 数値目標
- 週次レビュー時間: **< 1時間**
- 1日承認件数: **< 5件**
- 通知頻度: L0自律 / L1注意は集約 / L2方針承認 1日1回 / L3-L4のみ即時

## 8. R54-R63 統合リスク表 (Phase 4 v2)

(R54-R60 は v1 から、 R61-R63 は Round 26 追加)

| # | リスク | 対策 |
|---|---|---|
| R54 | ETH/SOL DNA データ不足 | 最低500件/アセット、 不足ならPhase 4遅延 |
| R55 | マルチアセット同時清算 | Fast Guard 数理レイヤーで圧縮 (Gemini Round 24) |
| R56 | 25肉体 バグ拡散 | paper only限定、 本番昇格は上位3体のみ |
| R57 | IQN+DRQN 訓練データ不足 | 過去2年 backtest merge必須 |
| R58 | LLM Proposer hallucination | 11ゲート+Criticモデル+Paper 2週間 |
| R59 | 予算超過 | 25肉体は常時稼働しない、 上位3体のみLive候補 |
| R60 | OKX API互換性 | Phase 4ではOKX接続検証まで、 Live売買はPhase 5 |
| **R61** | 相関リスク過小評価 | 毎日相関更新+相関急上昇時に全体レバ縮小 |
| **R62** | 個人名DNAブランド/人格模倣 | 市場テーマ別コード名、 個人名は内部参照のみ |
| **R63** | Strategy Proposer 複雑化量産 | 月2本まで、 禁止条件提案から開始 |

## 9. コスト見積もり v2 (Round 26 反映)

### 慎重構成 (Production レーンのみフル稼働、 Research レーンはスケジュール)
- 月額 **$180-350**
- 25肉体は常時稼働しない (例: 平日深夜のみ訓練+評価)
- LLM Proposer は週1のみ
- IQN+DRQN GPU Spot 週2 → 週1に削減

### Shujiさん予算 $135-400 内で運用可能

## 10. Phase 5 移行ゲート (Day 240)

GPT Round 26 反映の多軸判定:

| 条件 | GO基準 |
|---|---|
| Phase 4 稼働日数 | 60日 |
| 25肉体中 Trade-EHRプラス | 10体以上、 相関0.7超は1グループ扱い |
| BTC/ETH/SOL 各アセット安定系統 | 最低1系統/アセット |
| 最大DD | 許容内 (例: 累計20%以内) |
| Order Gate違反 | 0 |
| Fast Guard 重大事故 | 0 |
| Strategy Proposer 採用案 | 最低2週間事故0 |
| Shujiさん監督負荷 | KPI内 |

## 11. Round 27 Claude結論

GPT + Gemini Round 26 監査を **全面採用**。 v2 で重要修正:

- 3レーン制 (Production / Research / Governance)
- 監督負荷 KPI化 + 方針承認制
- PBT 25肉体は paper/Shadow only
- IQN+DRQN は Risk Estimator限定
- LLM Strategy Proposer は分業 + sandbox
- 個人名DNA禁止 (R62)
- 相関リスク対策 (R61)

**実装着手は Phase 3v2 達成後** (Day 161 以降)、 当面は概念設計止め。 Phase 5+ 設計叩き台は Phase 4 終盤に作成予定。
