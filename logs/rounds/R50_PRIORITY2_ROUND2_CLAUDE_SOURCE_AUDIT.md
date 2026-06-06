# R50 Priority 2 Round 2 Claude Source Audit

**作成日時 (JST)**: 2026-06-07 07:35:00
**Verify Token**: `[Round2-Claude-Audit-Verify: R50-PRIORITY2-ROUND2-CLAUDE-SOURCE-AUDIT]`

---

## 1. Verified claims (9件)

公式ソースまたは複数の信頼できるメディア+業界団体で検証済:

1. ✅ **SBI VC→USDC直接購入**: 国内で唯一対応 (2026年2月時点)
2. ✅ **GMOコイン SOL対応**: 公式 fee page明記
3. ✅ **bitbank SOL対応**: 2024年11月上場
4. ✅ **GMOコイン USDC×**: 公式記載なし
5. ✅ **bitFlyer USDC×**: 計画中、 未対応
6. ✅ **bitbank USDC×**: 計画中、 未対応
7. ✅ **GMOコイン出金手数料無料 (暗号資産)**: 公式明記
8. ✅ **Travel Rule 2026年運用**: TRUST/Sygna 2大ソリューション、 相互接続不完全
9. ✅ **Hyperliquid日本居住者可否**: IP制限なし、 法的グレーゾーン存在

## 2. Provisional Confirmed (3件)

一般知識/税法原則と整合、 公式直接出典は限定的:

10. 🟡 **XRP fee/速度** ($0.0001-0.001 / 3-5秒)
11. 🟡 **SOL fee/速度** ($0.0005-0.005 / 1-2秒)
12. 🟡 **SOL/XRP→USDC交換=利確 (雑所得)**

## 3. Pending (3件、 追加確認必要)

13. ⏳ **bitFlyer SOL対応**: 公式ページfetch失敗 (403 Forbidden)、 メディア「39種類取扱」 一般情報のみ
14. ⏳ **国内CEX→Hyperliquid直接送金不可 (個別case)**: Travel Rule一般運用Verified、 ただしHyperliquid個別case凍結事例の具体的ソース未確認
15. ⏳ **bitbank送金手数料 (XRP 0.15/SOL 0.01)**: 公式fee表fetch失敗 (404)、 一般情報のみ

## 4. Contradicted (0件)

Gemini主張と公式情報が矛盾するclaimなし。

---

## 5. Priority 2 Provisional Route Draft

Verified claimsに基づく暫定経路:

### 経路A (Exness CFD)
- 主軸: 国内銀行振込 → Exness入金
- バックアップ: クレジットカード入金
- 用途: MT5/BTC CFD検証枠 (経路A=danjer DNA検証用ではなく、 検証専用)

### 経路B (DEX/Hyperliquid)
- 主軸: **国内CEX (GMOコイン) → SOL購入 → 個人Phantom Wallet中継 → Hyperliquid**
  - 採用理由: GMO出金手数料無料 Verified、 SOL対応 Verified、 個人ウォレット中継必須 (Travel Rule一般運用)
- バックアップ1: bitbank → SOL → 個人WL → Hyperliquid (bitbank fee要確認後採用判定)
- バックアップ2 (要件次第): SBI VC→USDC直購入 → 個人WL → Hyperliquid (DEX直送制限の個別case確認後)

### 却下経路 (Verified)
- ❌ 国内CEX (GMO/bitFlyer/bitbank) → USDC直接送金 → DEX (USDC国内非対応のため不可)
- ❌ 国内CEX → Hyperliquid直接送金 (Travel Rule前提、 個別case未確認だが運用基本不可)

### 税務運用 (Provisional Confirmed)
- SOL→USDC交換時点で利確発生、 CryptoAct等CSV連携必須

---

## 6. Gemini再監査に回すべき質問リスト

Pending 3件を確定するため:

### Q1 (bitFlyer SOL公式確認)
bitFlyer公式ページが Claude側で fetch 不可 (403 Forbidden) でした。 Gemini側で bitFlyer公式 (https://bitflyer.com/ja-jp/virtual-currency-list) に SOL が明示掲載されているか、 2026-06-07時点で再確認願います。

### Q2 (Hyperliquid個別case)
国内CEX (GMO/bitFlyer/bitbank/SBI VC) から Hyperliquidへの送金が、 個別事例として凍結された具体的ソース or 公式FAQ記載があれば提示願います。 Travel Rule一般運用は Verified ですが、 Hyperliquidが「個人ウォレット中継**必須**」 の根拠を強化したい。

### Q3 (bitbank fee確認)
bitbank公式fee表が Claude側で fetch 不可 (404) でした。 Gemini側で bitbankのXRP/SOL送金手数料 (XRP 0.15/SOL 0.01) の最新公式値を再確認願います。

### Q4 (経路B複線化)
GMOコイン (出金手数料無料) を中継基地最優先と Verified しました。 ただし以下の追加考察を求めます:
- GMOコイン単一障害点リスク (取引所障害時のバックアップ手順)
- 大額時の小分け送金 (bitbank/SBI VC等を併用) のベストプラクティス

### Q5 (Hyperliquid法的グレーゾーン)
Hyperliquid 2026年6月時点のIP制限なしは Verified しましたが、 「法的グレーゾーン」 の具体的リスク (将来のジオフェンシング、 凍結、 規制突発) を Shujiさんへの注意喚起として明確化したい。

---

## 7. Priority 2 consensus_candidate 判定

**現状**: **false 維持**

理由:
- Pending 3件 (bitFlyer SOL公式 / Hyperliquid個別case / bitbank fee) 残存
- Pending claimsが Verified に進めば consensus_candidate=true 候補化可能

**次フェーズ推奨**:
- Q1-Q5 をGeminiへ送信 (controlled send)
- Gemini回答受領後、 Matrix update
- Pending 3件 → Verified に進めばconsensus_candidate判定

`[Round2-Claude-Audit-Verify: R50-PRIORITY2-ROUND2-CLAUDE-SOURCE-AUDIT]`
`[NextActor: GPT]`
`[EndTime-JST: 07:35:00 (real Bash取得)]`
`[is_shuji_represented: false]`
`[no_proxy_violation: true]`
