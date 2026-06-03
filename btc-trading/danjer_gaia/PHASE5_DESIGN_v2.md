# Phase 5+ 設計 v2 — Round 28 監査全反映 (Claude Round 29)

更新: 2026-06-03

## v1 → v2 哲学転換

**🚨 GPT Round 28 最重要発見**:
> 「Phase 5+ の本質は、 完全自律で拡大することではなく、 利益・税金・生活・心理・休暇・縮小権を含めて、 **壊れずに続けること**」

| # | 旧 (v1) | 新 (v2) | 出典 |
|---|---|---|---|
| 1 | **合法ヘッジファンド化** | **「個人資産運用の永続化・税務整備・規模管理」** | GPT |
| 2 | 年率+60-120% 攻め | **守り優先、 壊れずに続ける** | GPT |
| 3 | CPA相談 Phase 5.3 前 | **Phase 4 終了時点で初回** | GPT |
| 4 | OKX 本格Live | **採用せず** (OKX日本居住者完全禁止判明、 Round 31)、 代わりに bitFlyer Lightning Vacation用 | GPT |
| 5 | 複利 50:50 → 30:70 → 20:80 | **資金増えるほど再投資比率を下げる** (逆方向) | GPT |
| 6 | 拡大したくない時 不明 | **Maintain / Protect Mode 正式機能化** | GPT |
| 7 | 旅行時 通常運用継続 | **Vacation Mode** (新規禁止、 SLのみ機能) | GPT |
| 8 | 規模上限 不明 | **段階キャップ制** $25k/$50k/$100k/$250k/$500k 都度承認 | GPT |
| 9 | コスト 月利益から払う | **固定予算キャップ管理** ($400/月上限、 超過時 機能凍結) | GPT |
| 10 | 税務 個人雑所得 | **+Tax-Engine** (BQ→雑所得自動計算→確定申告CSV) | Gemini |
| 11 | 出金固定比率 | **Bandit出金** (Multi-armed bandit で動的最適化) | Gemini |
| 12 | 取引所間ポジ移管 | **移管禁止** (全閉→新規) | Gemini |

## 1. Phase 5+ v2 ロードマップ (時間制限なし、 永続)

```
Day 240-300 (Phase 5.1 守りの土台):
├─ Tax-Engine 実装 (BQ→雑所得自動計算→確定申告CSV)
├─ Safety Reserve / Living Reserve / 税金引当Equity の分離
├─ Maintain / Protect / Vacation Mode 実装
└─ OKX 接続検証 (本格Liveはまだ)

Day 300-365 (Phase 5.2 規模管理):
├─ 段階キャップ制 ($25k 到達で Shujiさん承認、 次キャップへ)
├─ Bandit出金 (生活費・再投資・税金引当の動的比率)
└─ 完全自律 Demotion (1事故即降格)

Day 365-450 (Phase 5.3 多様化、 守り中心):
├─ bitFlyer Lightning Vacation Mode 退避先確立 (OKXは日本居住者禁止のため不採用、 Round 31)
├─ BNB / SOL Stage 2 (拡大ではなく多様化)
└─ CPA相談 + 確定申告自動化

Day 450+ (Phase 5.4 永続):
├─ 段階キャップ + Maintain Mode で「これ以上拡大しない」選択肢
├─ 月次レビュー + 年次 CPA確認
└─ 「壊れずに続ける」 が KPI
```

## 2. Equity 分離 (GPT必須修正)

```
[全Equity]
├─ Trading Equity (実際の運用資金)
├─ Safety Reserve (DD許容超え用のバッファ、 全Equityの 20%)
├─ Living Reserve (生活費6ヶ月分、 月次出金から積立)
└─ Tax Engine Reserve (年次納税予測、 月次積立)
```

### Bandit出金 (Gemini採用、 動的比率)
```python
# Multi-armed bandit (簡易版)
def daily_allocation(monthly_profit, current_equity, target_caps):
    arms = [
        ("trading_reinvest", reward=expected_ehr_uplift),
        ("living_reserve",   reward=shuji_satisfaction),
        ("tax_reserve",      reward=tax_obligation_coverage),
        ("safety_reserve",   reward=dd_buffer_health),
    ]
    # ε-greedy で 30日ごとに比率調整
    # 規模ステージ ($25k→$50k→...) で arms の weight 変える
```

## 3. Vacation/Maintain/Protect Mode (GPT必須機能化)

### Vacation Mode (旅行・休暇)
- 新規エントリー **完全禁止**
- 既存ポジは保持 + SL のみ機能
- Shujiさんへの通知頻度 1/3 に削減
- 期間: Shujiさんが Slack で「/vacation 7days」 等で指定

### Maintain Mode (これ以上拡大したくない)
- 現状規模 維持、 段階キャップ昇格申請しない
- 25肉体の数を増やさない
- LLM Strategy Proposer 凍結
- 月次出金比率 100% (新規再投資なし)

### Protect Mode (相場急変や個人危機時)
- 全ポジ縮小 (Equity の 30% 以下に)
- Stage 0 相当の最低運用のみ
- Shujiさん承認しない限り Stage 2 復帰不可

## 4. 段階キャップ制 (GPT必須採用)

| Cap | Equity 到達 | 次キャップへの条件 |
|---|---|---|
| Cap 1 | $25,000 | 30日連続 Trade-EHR プラス + DD < 10% + Shuji承認 |
| Cap 2 | $50,000 | 同条件 + CPA相談済 |
| Cap 3 | $100,000 | 同条件 + 税務予測精度確認 |
| Cap 4 | $250,000 | 同条件 + 流動性影響テスト |
| Cap 5 | $500,000 | 同条件 + 永続化 SOP 確立 |

各キャップで **Shujiさん が「No」を選べる**。 自動で次へ進まない。

## 5. リスク統合 R64-R69 (Phase 5+ v2)

| # | リスク | 対策 |
|---|---|---|
| R64 | 取引所同時障害 (v3: Hyperliquid+bitget) | Hyperliquid主、 bitget副 (Phase 3後半から)、 GMOコイン Tax用、 bitFlyer Lightning Vacation退避用。 全障害時は全閉+Shuji緊急通知 |
| R65 | 完全自律 Demotion 過剰反応 | 1事故即降格 (速さ優先)、 ただし取引所側障害は除外 (Gemini) |
| R66 | 規模拡大で流動性影響 | 1注文サイズ上限「板厚 × 5%以下」維持 (R48継続)、 Cap 4以降は更に厳格化 |
| R67 | 税務 大幅利益時の納税予測 | **Tax-Engine** で月次積立 (Gemini)、 年次 CPA確認 (GPT) |
| R68 | 規模拡大時の Shujiさん心理負担 | **Maintain Mode** 正式機能化 (GPT)、 「資金額を見ない日」運用、 KPIで監督負荷監視 |
| R69 | コスト爆発 (利益なくても $400固定) | **固定予算キャップ管理** ($400/月上限)、 超過時 機能凍結 (GPT) |

## 6. コスト見積もり (Phase 5+ v2、 固定キャップ式)

**月額上限 $400 厳守** (GPT 必須修正、 利益前提でない):

| 項目 | 月額 |
|---|---|
| Cloud Run (slow-brain+fast-guard+routing) | $20-40 |
| Cloud Storage / BigQuery / Vector Search | $40-80 |
| Gemini クエリ + Cache | $30-60 |
| GPU Spot (週次訓練) | $10-25 |
| LLM Strategy Proposer (週1、 分業) | $5-15 |
| 取引手数料 (3取引所×多アセット) | $30-100 |
| 予備 | $20-80 |
| **合計** | **$155-400** |

超過時:
1. PBT 25肉体を 10体に削減
2. Strategy Proposer 隔週化
3. Vector Search クエリ削減
4. それでも超えるなら **Maintain Mode** へ移行

## 7. 全Phase 1-5+ v2 統合俯瞰

```
[Phase 1] 評価基盤 (Day 1-14)
    └─ Trade-EHR / TTL / Fast Guard / Order Gate / DNA移植
        ↓
[Phase 2 v2] Stage 0/1 (Day 15-45) — BTC 2x、 $15-50
    └─ 紙トレ + Hyperliquid Live + デイリー承認制 (Round 30-33 反映、 v3)
        ↓
[Phase 3 v2] BTC再現性検証 (Day 46-160) — BTC 3x、 $150-2,250
    └─ Stage 2 + PBT Lite + QR-DQN POC + ETH/SOL データ収集
        ↓
[Phase 4 v2] マルチアセット (Day 161-240) — 3レーン制
    └─ ETH Stage 1候補 + 1脳25肉体 + IQN+DRQN + LLM Strategy Proposer (paper)
        ↓
[Phase 5+ v2] 守りの永続 (Day 240+、 永続)
    ├─ Vacation / Maintain / Protect Mode
    ├─ Tax-Engine + Bandit出金
    ├─ Safety/Living/Tax Reserve 分離
    ├─ 段階キャップ ($25k→$500k、 都度Shuji承認)
    └─ **「壊れずに続ける」** がKPI、 月額$400固定上限
```

## 8. Round 29 Claude 結論

GPT「拡大ではなく守り」哲学転換+Gemini技術提案を **全面採用**。

主要修正:
- 名称変更 「個人資産運用の永続化・税務整備・規模管理」
- 守り中心 (Equity分離、 Mode機能化、 キャップ制)
- 固定予算 $400/月
- Tax-Engine + Bandit出金

**3者会議 Round 0-28 で Phase 1-5+ 全設計完了**。 これで Shujiさんが Day 0 から永続フェーズまでの全体俯瞰が可能。

## 9. Shujiさんに大枠で確認したい (1点)

> Phase 5+ の哲学を 「**拡大して年率+60-120%**」 から 「**壊れずに続けて、 段階キャップで Shujiさんが No と言える設計**」 に転換しました。 これでよいですか?

特に:
- 規模上限を **段階キャップ ($25k→$500k 都度承認)** にする
- 旅行/拡大停止/危機 のため **Vacation/Maintain/Protect Mode** を正式機能化
- 月コストは **$400固定上限** (利益関係なく超過時 機能凍結)

これで進めて よいか、 修正したい部分があれば。
