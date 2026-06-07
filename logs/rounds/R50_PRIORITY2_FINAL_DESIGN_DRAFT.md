# R50 Priority 2 Final Design Draft

**作成日時 (JST)**: 2026-06-07 09:35:00
**Verify Token**: `[Final-Design-Draft-Verify: R50-PRIORITY2-FINAL-DESIGN-DRAFT]`
**Author**: Claude (実装担当)
**Trigger**: GPT指示 Section 105 (R50-PRIORITY2-FINAL-DESIGN-DRAFT-6038)
**Source**: Matrix v3 clean + Gemini Round 2再監査結果 + GPT v3経路定義固定

---

## 経路A (Exness CFD検証枠)

**フロー**:
- 国内銀行振込 → Exness
- クレカ/デビットカード → Exness

**用途**: CFD検証・MT5運用

**重要事項**:
- **Hyperliquidとは混ぜない** (経路Bと完全分離)
- danjer DNA / ロンポチ DNA の本命検証ではない

---

## 経路B (Hyperliquid本命)

国内CEX → 自己管理ウォレット → Hyperliquid/dYdX

### 経路B主経路

**フロー**: GMOコイン → XRP/SOL → 自己管理WL (MetaMask/Phantom) → Hyperliquid内部USDCスワップ

**詳細手順**:
1. 国内銀行から GMOコインへ日本円入金
2. GMOコイン取引所/販売所で **XRPまたはSOLを購入** (USDCは購入しない)
3. GMOコインから自己管理ウォレットへ XRP/SOL送金 (Travel Rule申告、 送金fee無料)
4. 自己管理ウォレットから Hyperliquid (Arbitrum等) へ XRP/SOL ブリッジ送金
5. **Hyperliquid内部でUSDCにスワップ** (DEX内部スワップ)

**必須反映事項**:
- ❌ **GMO起点USDC直送記述は削除** (GMOはUSDC取扱なし、 Matrix v3 Claim 5 Pending=除外)
- ✅ GMOはUSDC調達元ではなく、 **XRP/SOL調達・送金元**
- ✅ Hyperliquid側でUSDC化 (DEX内部スワップ)
- ✅ **SOL/XRP→USDC交換時点の税務ログ必須** (国税庁準拠、 雑所得対象)
- ✅ **CryptoAct等CSV連携を運用要件に組み込む** (税務記録自動化)

**Verified根拠**:
- GMO出金fee無料 ✅
- GMO SOL対応 ✅
- 国内CEX→Hyperliquid直送不可 → 自己管理WL中継必須 ✅
- SOL/XRP→USDC交換=利確 ✅
- bitbank fee XRP 0.1/SOL 0.009 (経路B第二バックアップで採用) ✅

### 経路B副経路

**フロー**: SBI VC → USDC直購入 → 自己管理WL → Hyperliquid

**詳細手順**:
1. 国内銀行から SBI VCトレードへ日本円入金
2. SBI VC販売所で **USDCを直接購入** (国内唯一)
3. SBI VCから自己管理ウォレットへ USDC送金 (送金fee無料)
4. 自己管理ウォレットから Hyperliquidへ USDC送金

**必須反映事項**:
- ⚠️ **1回100万円相当額の入出庫制限** (SBI VC公式FAQ明記、 法的制約)
- ✅ 大額時は **複数回分割** または **経路B主経路へ切替**
- ✅ SBI VCは **副経路扱い** (主経路はGMO起点)

**Verified根拠**:
- SBI VC→USDC直購入 ✅ (国内唯一)
- SBI VC送金fee無料 ✅
- 100万円/回制限 ✅ (公式FAQ)

### 経路B第二バックアップ

**フロー**: bitbank → XRP/SOL → 自己管理WL → Hyperliquid

**詳細手順**:
1. 国内銀行から bitbank へ日本円入金
2. bitbank取引所 (板取引) で **XRPまたはSOLを購入** (Maker -0.02% 適用可)
3. bitbankから自己管理ウォレットへ XRP/SOL送金 (送金fee発生)
4. 自己管理ウォレットから Hyperliquid (Arbitrum等) へ XRP/SOL ブリッジ送金
5. Hyperliquid内部でUSDCにスワップ

**必須反映事項**:
- ✅ **XRP送金fee 0.1 XRP** (Gemini公式2026年6月1日改定版確認)
- ✅ **SOL送金fee 0.009 SOL** (同上)
- ✅ **GMO障害時バックアップ** (常用ではない)
- ✅ **コスト試算別枠** (送金fee + 日本円出金fee 550-770円 を別管理)

**Verified根拠**:
- bitbank SOL対応 ✅
- bitbank fee XRP 0.1/SOL 0.009 ✅

---

## 却下経路 (Verified)

### 1. 国内CEX → USDC直接送金 → DEX
- **理由**: USDC国内取扱はSBI VCのみ (Pending: GMO USDC取扱なし、 Provisional: bitFlyer/bitbank USDC公式発表なし)
- **判定**: 経路設計から除外

### 2. 国内CEX → Hyperliquid直接送金
- **理由**: Travel Rule TRUST/GTR非互換 + Hyperliquid通知対象国未登録 → 国内CEX側システム的に一律拒否
- **判定**: 構造的不可、 自己管理WL中継必須

### 3. bitFlyer SOL中継
- **理由**: bitFlyer SOL公式取扱なし (Provisional、 外部情報のみ)
- **判定**: 経路設計から除外

### 4. Wise既定路線
- **理由**: Round 50第1周〜第2周で「Wise送金=規約違反」 と確定 (memory project_round50_session_state.md参照)
- **判定**: 経路設計から除外

---

## 注意喚起 (Provisional - Shujiさん向け明示必須)

### Hyperliquid/dYdX 法的グレーゾーン
- **2026-06-07現在の状況**:
  - 日本居住者ジオフェンシング未実施 (アクセス可)
  - ただし FSA未登録業者
- **将来突発的リスク**:
  - 「日本IP完全遮断 (ジオフェンシング)」
  - 「国内CEXからのウォレット送金規制強化 (実質的隔離)」
  - dYdX等の先行例参照
- **運用方針**:
  - Hyperliquid内資金は **「即時失っても致命傷を与えない範囲」 に留める**
  - **利益はこまめに国内還流**
  - **資金の全額ロックを避ける**

### Hyperliquid内部USDCスワップの税務リスク
- DEX内部USDCスワップ = 雑所得発生 (国税庁準拠)
- 取得価額・売却価額のログ必須
- CryptoAct等CSV連携で自動化推奨

### SBI VC 100万円/回制限
- 大額送金時の運用手順を明文化
- 分割送金 or 経路B主経路 (GMO→XRP/SOL) への切替判断ロジック

---

## 残Provisional/Pending (consensus_candidate=true移行時の確認必要事項)

### Provisional (4件)
1. bitFlyer SOL対応 (公式取扱なし)
2. bitFlyer USDC対応 (公式発表なし)
3. bitbank USDC対応 (公式発表なし)
4. Hyperliquid/dYdX 日本居住者可否 (現アクセス可だが規約変更リスク)

### Pending (1件)
1. GMO USDC対応 (取扱なし、 経路設計から除外済み)

### 設計書側 残作業
- ✅ GMO起点USDC直送記述削除 (本design draftで対応)
- ✅ 経路B主経路「DEX内部USDCスワップ」 記述追加 (本design draftで対応)
- ✅ SBI VC 100万円/回制限ハンドリング規定追加 (本design draftで対応)

---

## Priority 2 consensus_candidate判定

**現状**: **false 維持**

理由:
- final design draft作成完了 ✅
- ただし、 GPT最終確認待ち
- 3者合意 (Gemini再監査結果との整合確認) 後にtrue候補化可能

---

## 次のステップ (Claude推奨)

1. 本design draftをGPT判定
2. GPT判定OKなら、 Gemini追加確認 (オプション、 Claude推奨は不要)
3. consensus_candidate=true 候補化 → Shujiさん最終承認

---

## 必須末尾タグ

`[Final-Design-Draft-Verify: R50-PRIORITY2-FINAL-DESIGN-DRAFT]`
`[NextActor: GPT]`
`[EndTime-JST: 09:35:00 (real Bash取得予定)]`
`[priority2-consensus_candidate-current: false]`
`[is_shuji_represented: false]`
`[no_proxy_violation: true]`
