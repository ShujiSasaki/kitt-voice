# R50 Priority 2 Round 2 Claude Source Audit (v2 = Gemini再監査反映後)

**作成日時 (JST)**: 2026-06-07 07:35:00 (v1) → 2026-06-07 08:24:00 (v2 revision)
**Verify Token**: `[Round2-Claude-Audit-Verify: R50-PRIORITY2-ROUND2-CLAUDE-SOURCE-AUDIT-REV2]`
**Revision history**:
- v1: Claude初版 (Verified 9 / Provisional 3 / Pending 3 / Contradicted 0)
- v2: Gemini Round 2再監査反映 (Verified 10 / Provisional 4 / Pending 1 / Contradicted 0)

---

## 1. Verified claims (10件 = v2)

公式ソースまたは Gemini直接確認で検証済:

1. ✅ **SBI VC→USDC直接購入**: 2025/3〜取扱、 100万円/回制限あり
2. ✅ **GMOコイン SOL対応**: 2022/10〜取扱
3. ✅ **bitbank SOL対応**: 2024/11上場 (Gemini現物・信用確認)
4. ✅ **国内CEX→Hyperliquid直送 不可**: Travel Rule非互換+通知対象国未登録による構造的不可
5. ✅ **GMOコイン出金手数料無料**: 日本円+全暗号資産送付fee=当社負担
6. ✅ **bitbank送金手数料**: XRP 0.1 / SOL 0.009 (Gemini公式2026年6月1日改定版直接確認)
7. ✅ **XRP fee/速度**: $0.0001-0.001 / 3-5秒、 経路コスト最小化適合 (Gemini確認)
8. ✅ **SOL fee/速度**: $0.0005-0.005 / 1-2秒、 経路コスト最小化適合 (Gemini確認)
9. ✅ **Travel Rule運用**: JVCEA/FSAガイドライン準拠、 自己管理WL送金時の宛先情報申告必須
10. ✅ **SOL/XRP→USDC交換=利確**: 国税庁「暗号資産税務上の取扱い」準拠、 ログ必須

## 2. Provisional (4件)

公式取扱なしだが計画中可能性、 または法的地位変更リスクあり:

11. 🟡 **bitFlyer SOL対応**: 公式取扱なし (外部情報のみ)、 RNDRソラナチェーン対応のみ
12. 🟡 **bitFlyer USDC対応**: 公式発表なし
13. 🟡 **bitbank USDC対応**: 公式発表なし
14. 🟡 **Hyperliquid/dYdX 日本居住者可否**: 現アクセス可だが規約・法的地位変更リスク

## 3. Pending (1件)

15. ⏳ **GMOコイン USDC対応**: **取扱なし**として経路設計から除外。 GMO起点の場合は XRP/SOL購入→送金→DEX内部USDCスワップ に一元化

## 4. Contradicted (0件)

---

## 5. Priority 2 Provisional Route Draft (v2 = Gemini再監査反映後)

### 経路A (主経路: コスト最適・調達分離型)
**国内CEX (GMOコイン: 日本円入金→XRP/SOL購入、 送金fee無料) → 自己管理ウォレット (MetaMask/Phantom: Travel Rule申告) → Hyperliquid (Arbitrum等経由入金、 内部USDCスワップ)**

- 採用理由:
  - GMOコイン出金fee無料 Verified
  - GMO SOL対応 Verified
  - 国内CEX→Hyperliquid直送不可のため自己管理WL中継必須
  - DEX(Hyperliquid)内部でUSDCスワップ = 国内USDC調達不可問題を回避
- 税務: SOL/XRP→USDC交換時点で利確発生、 CryptoAct CSV連携必須

### 経路B (副経路: ステーブル直接調達・100万円制限型)
**国内CEX (SBI VCトレード: 日本円入金→販売所でUSDC直購入、 送金fee無料) → 自己管理ウォレット → Hyperliquid**

- 採用理由:
  - SBI VC→USDC直購入 Verified (国内唯一)
  - SBI VC送金fee無料 Verified
- 制約:
  - **1回100万円相当額の入出庫制限** (SBI VC公式FAQ明記)
  - 大口送金は複数回分割 or 経路Aに一本化

### 経路B第二バックアップ (bitbank)
**国内CEX (bitbank: 日本円入金→XRP/SOL購入) → 自己管理ウォレット → Hyperliquid**

- 採用条件:
  - GMOコイン障害時のバックアップとして
  - 送金fee = XRP 0.1 / SOL 0.009 (発生)
  - 日本円出金fee 550-770円 (発生)
  - 取引所(板取引) Maker -0.02% で調達コスト低
- コスト試算別枠管理必須

### 却下経路 (Verified)
- ❌ 国内CEX (GMO/bitFlyer/bitbank) → USDC直接送金 → DEX
  - GMO USDC: 取扱なし (Pending=除外)
  - bitFlyer/bitbank USDC: 公式発表なし (Provisional)
- ❌ 国内CEX → Hyperliquid直接送金 (Travel Rule非互換による構造的不可、 Verified)
- ❌ bitFlyer SOL中継 (公式取扱なし、 Provisional)

### 税務運用 (Verified)
- SOL/XRP→USDC交換時点で利確発生、 CryptoAct等CSV連携必須
- 経路Aの場合: DEX(Hyperliquid)内部USDCスワップ時点で利確、 取得価額・売却価額ログ必須

### Shujiさん向け注意喚起 (Provisional - Hyperliquid関連)
- Hyperliquidは2026-06-07現在日本居住者ジオフェンシング未実施、 ただし FSA未登録業者
- 将来突発的「日本IP完全遮断」 や「国内CEXからのウォレット送金規制強化(実質隔離)」 リスクあり
- Hyperliquid内資金は「即時失っても致命傷を与えない範囲」 に留め、 利益はこまめに国内還流

---

## 6. Gemini再監査に回すべき質問リスト

Gemini Round 2再監査で大幅なソース品質向上が達成された。 **追加Gemini再監査は不要**。 ただし以下は次フェーズ (Priority 2 final consensus) で確認:

### Q1 (次フェーズ確認)
SBI VCトレード「100万円/回」 制限のハンドリング規定 (分割送金時の運用手順) の詳細をPriority 2 final designで詰める必要あり。

### Q2 (次フェーズ確認)
経路A主経路: DEX(Hyperliquid)内部USDCスワップ時の **税務記録自動化** (CryptoAct CSV連携) の具体的実装手順を Priority 2 final designで詰める必要あり。

---

## 7. Priority 2 consensus_candidate 判定

**現状**: **false 維持** (Gemini Round 2再監査反映後も同様)

理由:
- Matrix修正反映済みだが、 **設計書 (実装) 側のPriority 2記述修正が未完**:
  1. GMO起点USDC直送記述削除 (必須)
  2. 経路A主経路「DEX内部USDCスワップ」 記述追加 (必須)
  3. SBI VC 100万円/回制限ハンドリング規定追加 (必須)
- これらが完了し、 GPTで最終確認できれば consensus_candidate=true 候補化可能

**次フェーズ推奨 (Claude案)**:
- Claude側でMatrix/Audit修正完了 (本revision)
- 次は **GPTでMatrix/Audit revision内容確認** → consensus_candidate判定
- **Gemini追加送信は不要**: Gemini再監査で必要な情報は全て確認済み、 残るは Claude側の設計書修正反映のみ
- Geminiが既に「Matrix修正後に再判定」 と明示しているため、 修正完了 → Gemini再確認 (オプション) → GPT判定 → Shujiさん最終承認 の流れも可

`[Round2-Claude-Audit-Verify: R50-PRIORITY2-ROUND2-CLAUDE-SOURCE-AUDIT-REV2]`
`[NextActor: GPT]`
`[EndTime-JST: 08:24:00 (real Bash取得予定)]`
`[Revision: v2 (Gemini Round 2再監査反映)]`
`[is_shuji_represented: false]`
`[no_proxy_violation: true]`
