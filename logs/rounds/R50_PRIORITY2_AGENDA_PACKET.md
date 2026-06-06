# Priority 2 議題開始パケット (ドラフト、 GPT review待ち)

**作成日時 (JST)**: 2026-06-07 06:45:30
**Verify Token**: `[Packet-Verify: R50-PRIORITY2-AGENDA-PACKET-DRAFT]`
**送信先**: Gemini (実送信は GPT review後)
**状態**: DRAFT (実Send禁止、 GPT承認待ち)

---

## Priority 2: 送金・入出金経路

### Round 49確定議題本文 (verbatim from round_49.md L633-635)

> Priority 2: 送金・入出金経路
> - JPY → USDC/USDT/BTC/XRP 経路 / Wise経由 / SBI VCトレード経由 / 国内取引所経由 / BTC直送 / XRP送金 / 手数料 / 着金速度 / KYC / 出金制限 / 小額vs大額運用の違い

### Shujiさん発言 (verbatim、 関連)
- 「Wise既定路線却下」 (R50 第2周 取引所選定議論より)
- 「既登録取引所に限定しない」 (Round 49確定条件)
- 「AI育成に最適な取引所を選びたい」 (Round 49確定条件)

### Round 50で確定済の関連事項 (R50_PHASE15_FINAL_CONSENSUS_REPORTおよびR50最終インフラ報告書ドラフトより)
- 経路A: 日本円/銀行/カード等 → Exness → MT5/BTC CFD検証
- 経路B: 国内取引所 → XRP / USDC対応チェーン / SOL → Hyperliquid / dYdX v4
- Wise既定路線却下確定
- DMM Bitcoin除外確認

### Priority 2で深掘りすべき論点 (議題分解)

#### 2.1 JPY → 仮想通貨 経路選択
- (A) Wise経由 → 海外口座: 却下確定 (Shuji意見)
- (B) SBI VCトレード経由: 日本居住者向け、 KYC、 出金制限、 税務記録
- (C) 国内取引所 (GMO / bitFlyer / bitbank): JPY入金 → 仮想通貨買付 → Hyperliquid/dYdX v4送金
- (D) クレジットカード経由 (Exness等): 経路A用、 検証枠

#### 2.2 仮想通貨 中継トークン選択
- BTC直送: 送金時間 (~30分-1時間) / fee高 / セキュリティ高
- XRP: 高速 (~5秒) / fee低 / 規制リスク (2023米SECで一部解決)
- USDC: ステーブルコイン / 価格変動なし / 一部チェーンで高速
- SOL: 高速 / fee低 / 一部チェーン障害履歴

#### 2.3 送金経路シミュレーション (具体的)
- ケース1 (小額 1-10万円): 国内取引所JPY → XRP → 海外取引所
- ケース2 (中額 10-100万円): SBI VC → USDC → Hyperliquid
- ケース3 (大額 100万円+): 国内取引所JPY → BTC → 海外取引所 (or 直接Hyperliquid)

#### 2.4 KYC / 税務記録 / 出金制限
- 日本居住者の KYC要件 (Travel Rule + Article 36-2)
- 税務記録: 取引履歴CSV、 譲渡益計算
- 出金制限: 1日上限、 月間上限、 KYCレベル別

#### 2.5 手数料 / 着金速度 マトリクス
- 各経路の手数料 (取引所fee + 送金fee + 受取fee + スプレッド)
- 着金速度 (秒～時間単位)
- 失敗時の保証 / リスク

#### 2.6 小額 vs 大額 運用の違い
- 小額: fee比率重視、 経路の単純性
- 大額: 監視性、 セキュリティ、 分割送金、 KYC上限

---

## Gemini向け送信ペイロード (GPT補強反映済、 controlled send用)

GPT第122追加A (最新確認義務) + 追加B (仮説候補明示) を反映。

```
[Phase 1.5 Priority 2 開始 — Geminiへ]

Phase 1.5自動会議システムによる Priority 2 議題開始です。 Round 49確定アジェンダに基づき、 自動進行モードでお願いします。

【議題】 Priority 2: 送金・入出金経路

【既確定事項 (覆らない)】
- Wise既定路線却下 (Shuji意見)
- 既登録取引所に限定しない (Round 49確定条件)
- 経路A (Exness → MT5/CFD検証枠) と経路B (国内取引所 → Hyperliquid/dYdX v4) 並存
- DMM Bitcoin除外確認

【最新確認義務 (GPT第122追加A)】
各事実は2026-06-07時点で最新確認すること。 特に:
- Travel Rule (改正履歴・現行運用)
- 国内取引所の取扱銘柄 (最新ラインナップ)
- 出金制限 (現行上限・KYCレベル別)
- USDC/SOL/XRP対応状況 (チェーン・対応取引所)
- 海外DEX/CEXの日本居住者可否 (規制動向)

【仮説候補明示 (GPT第122追加B)】
以下は仮説候補であり、 実対応可否はGemini監査で確認してください。 未確認前提を確定事項として扱わないこと:
- SBI VC → USDC (実対応可否要確認)
- 国内取引所 (GMO/bitFlyer/bitbank) → USDC/SOL対応可否
- 各取引所の Hyperliquid直接送金可否
- XRP/SOLのチェーン手数料・速度実測値

【深掘り論点 (Round 49確定アジェンダから)】
1. JPY → 仮想通貨 経路選択 (SBI VC / GMO / bitFlyer / bitbank / クレカ - 仮説候補、 実対応要確認)
2. 中継トークン選択 (BTC / XRP / USDC / SOL - 対応状況要最新確認)
3. 送金経路シミュレーション (小額/中額/大額 3ケース)
4. KYC / 税務記録 / 出金制限 (最新運用要確認)
5. 手数料 / 着金速度 マトリクス (実測値ベース)
6. 小額 vs 大額 運用の違い

【依頼】
Geminiは技術監査担当として、 6論点それぞれについて:
- 既存案 (経路A/B) の網羅性チェック
- 漏れている検討候補の指摘
- 日本居住者の規制リスク監査 (Travel Rule等、 最新運用ベース)
- 各ケース別の推奨経路提案 (小額/中額/大額)
- 仮説候補 (追加B) の実対応可否確認
- 最新情報 (追加A) との照合

【運用ルール (Round 49確定 A/B/C/D)】
- A: Shuji意見はverbatim根拠必須
- B: 仮想AI主張は別分類
- C: 後続Roundの訂正優先
- D: 議題と結論を分ける

【必須末尾】
[Gemini-Verify: R50-PRIORITY2-GEMINI-AUDIT]
[NextActor: Claude]
[EndTime-JST: HH:MM:SS]
[is_shuji_represented: false]
[no_proxy_violation: true]
```

---

## state.json 更新予定 (GPT review後に適用)
- `next_priority: 2`
- `current_phase: Priority 2 auto progression preparation`
- `next_actor: GPT` (本パケットレビュー)
- `blocker: Awaiting GPT review of Priority 2 agenda packet`

`[Packet-Verify: R50-PRIORITY2-AGENDA-PACKET-DRAFT]`
`[Status: DRAFT - 実Send禁止, GPT承認待ち]`
`[EndTime-JST: 06:46:00 (real Bash取得)]`
`[is_shuji_represented: false]`
`[no_proxy_violation: true]`
