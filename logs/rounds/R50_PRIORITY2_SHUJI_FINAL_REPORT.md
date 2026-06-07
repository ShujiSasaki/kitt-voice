# R50 Priority 2 Shujiさん向け最終報告書

**作成日時 (JST)**: 2026-06-07 13:05:00
**Verify Token**: `[Shuji-Final-Report-Verify: R50-PRIORITY2-SHUJI-FINAL-REPORT]`
**宛先**: Shujiさん
**Author**: Claude (実装担当、 3AI内合意候補としてまとめ)
**Subject**: BTC自動売買「送金・入出金経路」 (Priority 2) の3AI内合意候補と承認依頼

---

## 1. 結論

- **Priority 2「送金・入出金経路」 は3AI内で consensus_candidate=true (合意候補)**
- **Gemini / GPT / Claude は3AI内で合意候補として承認**
- **Shujiさん最終承認は未取得**
- **実送金・実運用はまだ行わない** (Shujiさん承認をもって初めて実行)

3AI内合意の根拠:
- Gemini Round 3完全承認 (Section 114): 「2026年現在のオンチェーン仕様および税務要件を網羅した極めて実戦的な設計書」
- GPT判定 (Section 115/117): Must Fixなし、 任意推奨2点反映完了
- Claude実装担当 (Section 116): v4.1で全反映完了、 経路定義・税務ログ・却下経路すべて固定

---

## 2. 経路A (Exness CFD検証枠)

### フロー
**国内銀行振込 → Exness** / **クレカ/デビットカード → Exness**

### 用途
- CFD検証
- MT5運用

### 重要事項
- **Hyperliquidとは混ぜない** (経路Bと完全分離)
- danjer DNA / ロンポチ DNA の本命検証ではない

---

## 3. 経路B 主経路

### フロー
**GMOコイン → SOL購入 → Phantom自己管理ウォレット → Router Nitro等経由でHyperliquidへSOL入金 → Hyperliquid SpotアカウントにSOL着金 → Hyperliquid内SOL/USDC Spot市場で売却してUSDC取得**

### 必須事項
- ❌ **GMOはUSDC調達元ではない** (GMOではUSDC取扱なし)
- ❌ **XRPは使わない** (Hyperliquid公式入金リストに XRPなし)
- ✅ **SOL売却時に税務ログ発生** (国税庁準拠の利確イベント)
- ✅ **Spot Fills保存必須** (詳細は Section 7)

### 詳細手順
1. 国内銀行から GMOコインへ日本円入金
2. GMOコイン取引所/販売所で SOLを購入
3. GMOコインから Phantom自己管理ウォレットへ SOL送金 (Travel Rule申告、 送金fee無料)
4. Phantom自己管理ウォレットから Router Nitro等経由で Hyperliquidへ SOL入金
5. Hyperliquid SpotアカウントにSOLとして着金 (証拠金として使えるUSDCではない)
6. Hyperliquid内 SOL/USDC Spot市場で売却してUSDCを取得 (ユーザー自身が実行)
7. 売却で得たUSDCを Hyperliquid Perp証拠金として利用

### 根拠
- GMO SOL対応 (公式)、 GMO出金fee無料 (公式)、 Hyperliquid SOL Router Nitro経由直接入金対応 (公式Bridge2)、 Hyperliquid Spotアカウント着金仕様 (公式Onboarding)、 国内CEX→Hyperliquid直送不可 (Travel Rule非互換)

---

## 4. 経路B 副経路

### フロー
**SBI VCトレード → USDC直購入 → 自己管理ウォレット → CCTP対応chain (Base/Ethereum/Avalanche等) 経由Hyperliquid (ネイティブUSDC入金)**

### 制約
- ⚠️ **1回100万円相当額の入出庫制限** (SBI VC公式FAQ明記、 日本電子決済手段移動規制)
- ✅ 大額時は **複数回分割** または **経路B主経路へ切替**

### 詳細手順
1. 国内銀行から SBI VCトレードへ日本円入金
2. SBI VC販売所で USDCを直接購入 (国内唯一)
3. SBI VCから自己管理ウォレットへ USDC送金 (送金fee無料)
4. 自己管理ウォレットから CCTP対応chain経由でHyperliquidへネイティブUSDC入金 (1クリック)
5. Hyperliquid証拠金として直接利用 (Spot売却不要)

### 根拠
- SBI VC→USDC直購入 (国内唯一)、 SBI VC送金fee無料、 Hyperliquid Circle CCTP全面採用 (2025年12月〜)、 ネイティブUSDC 1クリック入金、 100万円/回制限 (公式FAQ)

---

## 5. 経路B 第二バックアップ

### フロー
**bitbank → SOL購入 (板取引Maker -0.02%推奨) → Phantom自己管理ウォレット → Router Nitro等経由でHyperliquidへSOL入金 → Hyperliquid SpotアカウントにSOL着金 → SOL/USDC Spot売却**

### 採用条件
- **GMO障害時のみ** (常用ではない)
- 板取引Maker -0.02% で調達コスト低
- **SOL送金fee 0.009 SOL** (Gemini公式2026年6月1日改定版直接確認)
- 日本円出金fee 550-770円 (発生)
- **コスト試算別枠** (送金fee + 日本円出金fee を別管理)

### 根拠
- bitbank SOL対応 (公式)、 bitbank fee XRP 0.1/SOL 0.009 (公式2026/6/1改定)

---

## 6. 却下経路

### 1. 国内CEX → Hyperliquid直接送金
- **理由**: Travel Rule TRUST/GTR非互換 + Hyperliquid通知対象国未登録 → 国内CEX側システム的に一律拒否
- **判定**: 構造的不可

### 2. 国内CEX → USDC直接送金 → DEX
- **理由**: USDC国内取扱はSBI VCのみ (GMO USDC取扱なし、 bitFlyer/bitbank USDC公式発表なし)
- **判定**: 経路設計から除外 (SBI VCのみ Section 4の副経路で採用)

### 3. XRP → Hyperliquid直送
- **判定**: **公式非対応のため物理経路から除外。 将来Hyperliquidが公式対応した場合のみ再検証対象**
- **理由**: Hyperliquid公式直接入金リストに XRP なし (BTC, ETH/ENA, SOL, MON, XPL等のみ)

### 4. bitFlyer SOL中継
- **理由**: bitFlyer SOL公式取扱なし (外部情報のみ)
- **判定**: 経路設計から除外

### 5. Wise既定路線
- **理由**: 「Wise送金=規約違反」 確定 (Round 50第1周〜第2周で確認、 memory project_round50_session_state.md参照)
- **判定**: 経路設計から除外

---

## 7. 税務ログ

### Spot Fills (現物約定履歴) 保存項目

Hyperliquid内 SOL → USDC Spot売却時、 以下を **絶対消失不可** で保存:

#### 税務必須項目 (7項目)
1. **SOL数量** (売却したSOLの数量)
2. **USDC獲得量** (取得したUSDCの数量)
3. **約定時刻** (UTC + JST両方推奨)
4. **約定価格** (SOL/USDC レート)
5. **約定時点の USD/JPY 円換算レート** (国税庁準拠の利確計算用)
6. **手数料** (Hyperliquid Spot taker/maker fee)
7. **取引ID** (Hyperliquid Spot Fill ID)

#### 任意項目 (1項目 - 監査・ガバナンス用)
8. **証拠金口座への振替日時** (Spot → Perpsマージン振替ログ、 税務計算には直接影響しないが、 将来のガバナンス・監査対応で盤石化)

### 税務ログの目的
- SOL→USDC Spot売却時点で利確発生 (国税庁「暗号資産に関する税務上の取扱い」 準拠の「暗号資産同士の交換」)
- SOL取得価額と USDC交換時点の円換算時価の差額 = **雑所得 (総合課税)** 対象
- 個人申告で雑所得計算必須

### CSV連携前提
- **CryptoAct等 (税務計算サービス) へ自動CSV連携前提で設計**
- 月次・年次の利確計算自動化
- 確定申告時の雑所得計算ロジック実装

---

## 8. 注意喚起

### Hyperliquid/dYdX 法的グレーゾーン
- **2026-06-07現在の状況**:
  - 日本居住者ジオフェンシング未実施 (アクセス可)
  - ただし **FSA未登録業者**
- **将来突発的リスク**:
  - 「日本IP完全遮断 (ジオフェンシング)」
  - 「国内CEXからのウォレット送金規制強化 (実質的隔離)」
  - dYdX等の先行例参照

### 運用方針 (リスク管理)
- ✅ **Hyperliquid内資金は「即時失っても致命傷を与えない範囲」 に留める**
- ✅ **利益はこまめに国内還流**
- ✅ **資金の全額ロックを避ける**
- ❌ **Shujiさん承認前に実送金しない**

### 税務リスク
- SOL→USDC Spot売却時の利確発生は **逃れられない**
- Spot Fills 7項目を確実に保存しないと確定申告破綻
- CryptoAct等CSV連携を運用要件に組み込み

### SBI VC 100万円/回制限
- 大額送金時の運用手順を Shujiさんが明確に理解
- 分割送金 or 経路B主経路 (GMO→SOL) への切替判断

---

## 9. Shujiさんへの承認依頼

以下の3択でご回答ください:

### A. 承認
→ Priority 2「送金・入出金経路」 確定。 Priority 3 (取引所運用ロジック) へ進む。
- 3AI内 consensus_candidate=true → 最終確定
- 経路A/B固定定義、 Spot Fills税務ログ、 却下経路すべて確定
- 実送金開始は Shuji判断のタイミングで

### B. 修正して続行
→ 修正点を指定してください。 3AI再議論で修正反映後、 再度承認依頼。
- 例: 「経路B主経路のRouter Nitroではなく別のbridgeを使いたい」
- 例: 「Spot Fills項目に追加してほしい項目がある」

### C. 差し戻し
→ Priority 2を根本から再議論。
- Round 50の前提条件 (Hyperliquid主軸、 Wise却下、 経路A/B分離) から再検討

---

## 必須末尾タグ

`[Shuji-Final-Report-Verify: R50-PRIORITY2-SHUJI-FINAL-REPORT]`
`[NextActor: GPT (Claude発言Section 118まで)、 その後Shujiさん]`
`[EndTime-JST: 13:05:00 (real Bash取得予定)]`
`[priority2-consensus_candidate: true]`
`[requires_shuji_final_approval: true]`
`[is_shuji_represented: false]`
`[no_proxy_violation: true]`
