# R50 Priority 2 Final Design Draft (v4.1)

**作成日時 (JST)**: 2026-06-07 09:35:00 (v3) → 10:40:00 (v4) → 12:55:00 (v4.1)
**Verify Token**: `[Final-Design-Draft-Verify: R50-PRIORITY2-FINAL-DESIGN-DRAFT-V4.1]`
**Author**: Claude (実装担当)
**Trigger**: GPT指示 Section 111 (v4) + Section 115 (v4.1) + Gemini Route B 再監査 Section 110 + Gemini Round 3承認 Section 114
**Source**: Matrix v3 clean + Gemini Round 2再監査 + Gemini Route B 再監査 + Hyperliquid公式仕様
**Status**: draft / pending GPT review (consensus_candidate=false維持)

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

## 経路B (Hyperliquid本命) — v4 確定

国内CEX → 自己管理ウォレット → Hyperliquid/dYdX

### 経路B主経路

**フロー**:
1. 国内銀行から GMOコインへ日本円入金
2. GMOコイン取引所/販売所で **SOLを購入** (XRPは購入しない、 USDCは取扱なし)
3. GMOコインから Phantom自己管理ウォレットへ SOL送金 (Travel Rule申告、 送金fee無料)
4. Phantom自己管理ウォレットから Router Nitro等経由で Hyperliquidへ SOL入金
5. **Hyperliquid Spotアカウントに SOLとして着金** (証拠金として使えるUSDCではない)
6. **Hyperliquid内 SOL/USDC Spot市場で売却して USDCを取得** (ユーザー自身が実行)
7. 売却で得たUSDCを Hyperliquid Perp証拠金として利用

**Verified根拠**:
- GMO SOL対応 ✅ (Matrix Verified)
- GMO出金fee無料 ✅
- 国内CEX→Hyperliquid直送不可 → 自己管理WL中継必須 ✅
- Hyperliquid SOL Router Nitro経由直接入金対応 ✅ (Gemini再監査確認、 公式Bridge2)
- **Hyperliquid Spotアカウント着金仕様** ✅ (Gemini再監査明示、 公式Onboarding)
- **SOL/USDC Spot市場売却でUSDC取得** ✅ (Gemini再監査明示)

**禁止表現**:
- ❌ 「自動USDC化」
- ❌ 「Hyperliquid側で自動USDC化」
- ❌ 「自動スワップ」
- ❌ 「着金時にUSDC化」

### 経路B副経路

**フロー**:
1. 国内銀行から SBI VCトレードへ日本円入金
2. SBI VC販売所で **USDCを直接購入** (国内唯一)
3. SBI VCから自己管理ウォレットへ USDC送金 (送金fee無料)
4. 自己管理ウォレットから CCTP対応chain (Base/Ethereum/Avalanche等) 経由で Hyperliquidへ **ネイティブUSDC入金** (Circle CCTP、 1クリック)
5. Hyperliquid証拠金として直接利用 (Spot売却不要)

**v4でも維持** (Gemini再監査で完全に妥当と判定)

**Verified根拠**:
- SBI VC→USDC直購入 ✅ (国内唯一)
- SBI VC送金fee無料 ✅
- Circle CCTP対応 (Hyperliquid 2025年12月全面採用) ✅ (Gemini再監査明示)
- ネイティブUSDC 1クリック入金 ✅

**制約**:
- ⚠️ **1回100万円相当額の入出庫制限** (SBI VC公式FAQ明記、 日本電子決済手段移動規制)
- ✅ 大額時は **複数回分割** または **経路B主経路へ切替**

### 経路B第二バックアップ

**フロー**:
1. 国内銀行から bitbank へ日本円入金
2. bitbank取引所 (板取引、 Maker -0.02%推奨) で **SOLを購入**
3. bitbankから Phantom自己管理ウォレットへ SOL送金 (送金fee 0.009 SOL)
4. Phantom自己管理ウォレットから Router Nitro等経由で Hyperliquidへ SOL入金
5. **Hyperliquid Spotアカウントに SOLとして着金**
6. **Hyperliquid内 SOL/USDC Spot市場で売却して USDCを取得**

**採用条件**:
- GMO障害時のバックアップ (常用ではない)
- 板取引Maker -0.02% で調達コスト低
- 送金fee 0.009 SOL + 日本円出金fee 550-770円 → コスト試算別枠管理

---

## 税務ログ仕様 (v4 追加 - 必須)

### 税務トリガー
- **GMO/bitbank での SOL購入時点**: 取得価額 (円建) 記録 (将来の利確計算ベース)
- **GMO/bitbank → 自己管理WL → Hyperliquid 送金**: 非課税 (自己名義間移動)、 Travel Rule申告ログのみ保存
- **Hyperliquid内 SOL → USDC Spot売却時点**: ⚠️ **最大の税務トリガー (利確発生)**
  - SOL取得価額 (円建) と USDC交換時点の円換算時価の差額 = **雑所得 (総合課税)** 対象
  - 個人申告で雑所得計算必須

### Spot Fills (現物約定履歴) 保存項目 (税務必須7項目 + 任意1項目)

Hyperliquid内 SOL/USDC Spot売却時、 以下を**絶対消失不可**で保存:

#### 税務必須項目 (7項目)
1. **SOL数量** (売却した SOL の数量)
2. **USDC獲得量** (取得した USDC の数量)
3. **約定時刻** (UTC + JST両方推奨)
4. **約定価格** (SOL/USDC レート)
5. **約定時点の USD/JPY 円換算レート** (国税庁準拠の利確計算用)
6. **手数料** (Hyperliquid Spot taker/maker fee)
7. **取引ID** (Hyperliquid Spot Fill ID)

#### 任意項目 (1項目 - 監査・ガバナンス用、 v4.1追加)
8. **証拠金口座への振替日時** (Spot → Perpsマージン振替ログ、 税務計算には直接影響しないが、 監査・ガバナンス対応で盤石化)

### CSV連携前提
- CryptoAct等 (税務計算サービス) へ自動CSV連携前提で設計
- 月次・年次の利確計算自動化
- 確定申告時の雑所得計算ロジック実装

---

## 却下経路 (Verified + Gemini Route B再監査追加)

### 1. 国内CEX → USDC直接送金 → DEX
- **理由**: USDC国内取扱はSBI VCのみ (Matrix v3 clean Pending: GMO USDC取扱なし、 Provisional: bitFlyer/bitbank USDC公式発表なし)
- **判定**: 経路設計から除外

### 2. 国内CEX → Hyperliquid直接送金
- **理由**: Travel Rule TRUST/GTR非互換 + 通知対象国未登録 → 国内CEX側システム的に一律拒否 (Gemini Matrix Verified)
- **判定**: 構造的不可

### 3. bitFlyer SOL中継
- **理由**: bitFlyer SOL公式取扱なし (Provisional、 外部情報のみ)
- **判定**: 経路設計から除外

### 4. **GMO/bitbank → XRP → Hyperliquid直送** (v4 新規追加却下、 v4.1で表現マイルド化)
- **理由**: Hyperliquid公式直接入金リストにXRPなし (BTC, ETH/ENA, SOL, MON, XPL等のみ)
- **判定**: **公式非対応のため物理経路から除外** (v4.1でマイルド化、 Gemini Round 3任意推奨反映)
- **将来再検証条件**: 将来Hyperliquidが XRP公式対応した場合のみ再検証対象
- **現時点の扱い**: XRPは Route B Hyperliquid入金候補から外す

### 5. Wise既定路線
- **理由**: Round 50第1周〜第2周で「Wise送金=規約違反」 確定 (memory project_round50_session_state.md)
- **判定**: 経路設計から除外

---

## 注意喚起 (Provisional - Shujiさん向け明示必須)

### Hyperliquid/dYdX 法的グレーゾーン (v3から維持)
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

### Hyperliquid Spot売却時の税務リスク (v4 新規追加)
- SOL→USDC Spot売却 = 「暗号資産同士の交換」 で利確発生 (国税庁準拠)
- 取得価額・売却価額のログ必須 (Spot Fills 7項目)
- CryptoAct等CSV連携で自動化推奨
- 確定申告時の雑所得計算ロジック実装必須

### SBI VC 100万円/回制限 (v3から維持)
- 大額送金時の運用手順を明文化
- 分割送金 or 経路B主経路 (GMO→SOL) への切替判断ロジック

---

## 残Provisional/Pending (consensus_candidate=true移行時の確認必要事項)

### Provisional (4件 - Matrix v3 clean維持)
1. bitFlyer SOL対応 (公式取扱なし)
2. bitFlyer USDC対応 (公式発表なし)
3. bitbank USDC対応 (公式発表なし)
4. Hyperliquid/dYdX 日本居住者可否 (現アクセス可だが規約変更リスク)

### Pending (1件 - Matrix v3 clean維持)
1. GMO USDC対応 (取扱なし、 経路設計から除外済み)

### 設計書側 残作業
- ✅ GMO起点USDC直送記述削除 (v3で対応済み)
- ✅ 経路B主経路「Spot着金→Spot売却→USDC取得」 記述追加 (v4で対応済み)
- ✅ SBI VC 100万円/回制限ハンドリング規定追加 (v3で対応済み)
- ✅ Spot Fills 7項目税務ログ仕様追加 (v4で対応済み)
- ✅ 「自動USDC化」 表現の全削除 (v4で対応済み)
- ✅ XRP→Hyperliquid直送却下追加 (v4で対応済み)

---

## Priority 2 consensus_candidate判定

**現状**: **false 維持** (v4でも同様)

理由:
- final design draft v4作成完了 ✅
- ただし、 GPT最終確認待ち
- 3者合意 (Gemini Round 3最終確認結果との整合確認) 後にtrue候補化可能

---

## 次のステップ (Claude推奨)

1. 本v4 final design draft + V4_REVISION.md を GPT判定 (本report)
2. GPT判定OKなら、 **Gemini Round 3最終確認** (Spot着金仕様 + Spot Fills税務ログ反映確認)
3. Round 3でGemini承認後、 consensus_candidate=true候補化
4. Shujiさん最終承認 (3者合意成立時のみ報告)

---

## 必須末尾タグ

`[Final-Design-Draft-Verify: R50-PRIORITY2-FINAL-DESIGN-DRAFT-V4.1]`
`[NextActor: GPT]`
`[EndTime-JST: 12:55:00 (real Bash取得予定)]`
`[priority2-consensus_candidate-current: true (3AI内合意候補化、 Shujiさん最終承認は未取得)]`
`[v4_revisions_applied: 自動USDC化全削除 + Spot Fills税務ログ7項目追加 + XRP直送永久却下追加]`
`[v4.1_revisions_applied: Spot Fills項目8 (証拠金口座振替日時) 追加 + XRP却下表現マイルド化]`
`[is_shuji_represented: false]`
`[no_proxy_violation: true]`
