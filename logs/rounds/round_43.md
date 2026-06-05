# Round 43 — Shuji方針大転換: AI制約最小化 + データ先行

## Round 43 — Shujiさんからの方針 (verbatim、 2026-06-05)

> 「レバレッジは各クローンが判断、 上限や下限は設けない。 リスクリワードはクローンaiがゲームの最高成績の偏差値を得るために考えること。
> ロンポチの全投稿テキスト画像を集めないと土台が作れない。 ロンポチを語るには投稿データを集めないと。
> 取引所はこだわらない、 最適なところを使用する、 1取引所1口の口座でも複数の口座でも、 複数取引所で複数でも最適を導き出して、 運用中も取引所の条件変わるから変更の可能性もある。
> danjer dnaとロンポチdnaの資金比率は成長するaiの成績次第だから現時点では割合を決めれない。 ペーパーテストや実運用中にも最適を求めていくことになる」

Shuji方針 4点:
1. **レバ上限・下限なし、 AI 自律判断** (戦略Z v10 の レバ固定値 撤回)
2. **データ先行** (ロンポチ Wayback取得が最優先、 戦略議論より実装)
3. **取引所動的選定** (Phase別固定構成 撤回、 AI が最適選定+運用中変更)
4. **資金比率は AI が動的最適化** (Phase別 60:40等の固定値 撤回)

→ Round 0 「**ゲームアプローチ**」 への立ち返り、 v10 の細かい数値は **過剰設計** だった。 Claude/GPT/Gemini で **再議論** + **即座にロンポチデータ取得着手**。

## Round 43 — Claude 反省 + 3者再議論 (簡潔版)

### Claude の v10 過剰設計 反省

Round 42 で v10 として書いた:
- 「Phase 5 Cap 3で short 60% + long 40%」 → ❌ Shuji方針4違反
- 「ロンポチ AI のレバは Shuji 10x以内」 → ❌ Shuji方針1違反 (Shujiの言葉そのまま使ったが、 Shujiが本意で言ってない)
- 「ロンポチ運用先は Hyperliquid spot + perp 1.5x」 → ❌ Shuji方針3違反
- 「累計$80k or $100k でシフト」 → ❌ Shuji方針4違反

→ Claude が **Shuji の Round 42 説明を字義通り受けて 数値固定**、 これが過剰設計の原因。
→ Shuji 真意は「**AI に最適化を任せる**」、 数値固定は不要。

### 3者再議論 (Round 43、 簡潔)

#### GPT 司会判断
方針1-4 すべて受領、 戦略Z **v10 → v11 (AI自律化)** に更新:

```
[戦略Z v11 — Round 43 AI自律化]

数値固定 撤回:
- レバ: AI 判断 (上限・下限なし、 Risk Engineが安全側で制約)
- 取引所配分: AI判断 (動的選定、 運用中変更可)
- 資金比率 (danjer vs ロンポチ): AI判断 (paper/実運用で動的最適化)
- 「短期→長期 シフト」 ライン: AI判断 (Trade-EHRが最高となるタイミング)

Shuji が決めるのは:
- 評価関数 (= ゲームの偏差値 = Trade-EHR + 安全制約)
- 段階キャップ (Cap 1〜Cap 5 都度承認、 v8 Phase 5+設計)
- データ取得方針 (ロンポチ Wayback 等)

AI が決めるのは: 上記以外の **全部**
```

#### Gemini 技術深掘り
「AI 制約最小化」 の技術実装:

- **Risk Engine** は引き続き 安全制約 (清算回避、 SL未設置禁止 等) は維持
- レバ上限は「**理論上限 = Hyperliquid 50x or Exness 400x**」、 AI が自律判断
- 評価関数: **Trade-EHR + ガード減算** (R32 Black Swan、 R47マルチアセット同時清算 等のペナルティ)
- 「ゲームの偏差値」 = Trade-EHR を **paper運用全AIの中での順位** で評価 (PBT 文脈)

技術的に必要な追加実装:
1. **動的 exchange_router** (Phase別固定→AI判断)
2. **動的 資金配分** (Stance JSON拡張、 「**target_pool_allocation**」 フィールド)
3. **多 AI 並走 PBT** (danjer + ロンポチ + 独自 + 各々の hyperparameter variant)

#### Claude 実装責務
Phase 0 並行作業 優先順位 (Shuji方針反映):

```
[最優先 (Phase 0 期間中、 Day -7 〜 Day -1)]
1. ロンポチ Wayback Machine 取得スクリプト 実装 + 実行
   ├─ 9,874件 URL → HTML取得 → テキスト+画像URL抽出 → 画像実体取得
   └─ 想定: テキスト 7,000件 + 画像 600-1,750枚

[次優先 (Phase 0 後半 + Phase 2 並行)]
2. ロンポチ DNA 読解 (Anthropic Batch、 B-slim v3 + 画像読解)
3. danjer BC pre-training データ準備
4. exchange_router 動的化 (Phase別固定 撤去、 AI判断で動的選定)
5. Stance JSON 拡張 (target_pool_allocation 等)
```

### v11 = AI に最大限委ねる ミニマル設計

```
Phase 2 (Day 8-):
└─ AI が:
   ├─ 取引所選定 (現状: Hyperliquid のみだが、 将来追加可)
   ├─ レバ判断 (各トレード毎)
   ├─ SL/TP距離 (各トレード毎)
   ├─ 資金プール配分 (短期vs長期 ratio)
   └─ Trade-EHR 最大化を目指す

Shuji が:
├─ Phase 0 で データ用意 (ロンポチ Wayback)
├─ 段階キャップ承認 (Cap 1〜Cap 5 都度)
└─ 評価関数の方向性確認 (年次)
```

### Round 43 結論 (簡潔)

- ✅ AI制約最小化 採用 (戦略 v11)
- ✅ ロンポチ Wayback 取得 を **今すぐ着手** (Claude 自律実行)
- ✅ 取引所動的選定 (exchange_router 改修)
- ✅ 資金配分 AI動的判断 (Stance JSON 拡張)
- ✅ Shuji 数値設定は **段階キャップのみ** に絞る

実装着手 → Round 44 で実装報告。


---
