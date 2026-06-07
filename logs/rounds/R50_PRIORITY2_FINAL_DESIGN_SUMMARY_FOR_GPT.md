# R50 Priority 2 Final Design Summary for GPT (v4)

**作成日時 (JST)**: 2026-06-07 09:35:00 (v3) → 10:40:00 (v4)
**Verify Token**: `[Final-Design-Summary-Verify: R50-PRIORITY2-FINAL-DESIGN-SUMMARY-FOR-GPT-V4]`
**Author**: Claude (実装担当)
**Subject**: R50_PRIORITY2_FINAL_DESIGN_DRAFT.md v4 の GPT確認用サマリー

---

## 1. Gemini Route B再監査での修正点 (v3 → v4)

### 自動USDC化削除確認
- ❌ 旧表現「Hyperliquid側で自動USDC化」 → 全削除
- ✅ 新表現「HyperliquidのSpotアカウントにSOLとして着金 → Hyperliquid内SOL/USDC Spot市場で売却してUSDC取得」

### Spot Fills税務ログ追加確認
- ✅ Hyperliquid内 SOL→USDC Spot売却時点が **最大の税務トリガー** と明記
- ✅ Spot Fills (現物約定履歴) 保存7項目 (SOL数量/USDC獲得量/約定時刻/約定価格/円換算レート/手数料/取引ID)
- ✅ CryptoAct等CSV連携前提を運用要件に組み込み

### XRP直送却下確認
- ✅ 「GMO/bitbank → XRP → Hyperliquid直送」 を **永久却下** として却下経路に明記
- ✅ 「XRPを使う場合は別途USDC化経路の再検証が必要」 と注記

### SBI VC副経路維持確認
- ✅ 「SBI VC → USDC直購入 → 自己管理WL → CCTP対応chain経由Hyperliquid」 (Gemini Q4で完全に妥当判定)
- ✅ 1回100万円相当額制限明記
- ✅ 大額時は分割or経路B主経路切替

---

## 2. v4で残る論点

### 確認待ち
1. **GPT確認待ち**: 本v4 final design draft の GPT判定
2. **Gemini Round 3最終確認待ち**: Spot着金仕様 + Spot Fills税務ログ反映の最終確認

### 残Provisional (4件 - Matrix v3 clean維持)
- bitFlyer SOL対応
- bitFlyer USDC対応
- bitbank USDC対応
- Hyperliquid/dYdX 日本居住者可否

### 残Pending (1件 - Matrix v3 clean維持)
- GMO USDC対応 (取扱なし、 経路設計から除外済み)

---

## 3. Gemini Round 3最終確認に回すべき質問案

### Q1: Spot着金仕様の正確性
v4で「HyperliquidのSpotアカウントにSOLとして着金 → Hyperliquid内SOL/USDC Spot市場で売却してUSDC取得」 と修正したが、 Gemini Section 110明示の仕様と一致しているか最終確認。

### Q2: Spot Fills税務ログ7項目の十分性
v4で以下7項目を保存対象とした:
- SOL数量
- USDC獲得量
- 約定時刻
- 約定価格
- 約定時点の USD/JPY 円換算レート
- 手数料
- 取引ID

これで国税庁準拠の雑所得計算に十分か、 追加項目はあるか確認。

### Q3: 経路B副経路 (SBI VC) の最終承認
「SBI VC → USDC直購入 → 自己管理WL → CCTP対応chain (Base/Ethereum/Avalanche等) 経由Hyperliquid (ネイティブUSDC、 1クリック)」 の表現で最終承認可能か確認。

### Q4: XRP却下の永久性
「XRP → Hyperliquid直送」 を **永久却下** としたが、 将来Hyperliquidが XRP直接入金をサポートした場合の再検討余地について Geminiの見解確認。

### Q5: consensus_candidate=true 移行可否
v4反映完了で、 Gemini Round 3でtrue移行承認可能か最終判定。

---

## 4. GPTが確認すべきチェックリスト

### v4必須反映確認
- [ ] 経路B主経路「自動USDC化」 → 「Spot着金 → Spot売却」 修正されているか
- [ ] 経路B第二バックアップ (bitbank) の同様修正がされているか
- [ ] 禁止表現 (自動USDC化/自動スワップ/Hyperliquid側で自動/着金時にUSDC化) が設計本文に残っていないか
- [ ] Spot Fills税務ログ7項目が明記されているか
- [ ] CryptoAct等CSV連携が運用要件に追加されているか
- [ ] XRP→Hyperliquid直送が **永久却下** として却下経路に明記されているか
- [ ] SBI VC 100万円/回制限が副経路に明記されているか
- [ ] Hyperliquid Spot売却時の税務リスク注意喚起がShujiさん向けに明記されているか

### consensus_candidate判定
- [ ] false維持が妥当か
- [ ] Gemini Round 3最終確認に進める準備が整っているか

### grep結果
- [ ] 「自動USDC化」 = 設計本文 (採用経路) に残っていない
- [ ] 「自動スワップ」 = 設計本文 (採用経路) に残っていない
- [ ] 「Hyperliquid側で自動」 = 設計本文 (採用経路) に残っていない
- [ ] 「XRP/SOL → Hyperliquid」 = 設計本文 (採用経路) に残っていない
- [ ] 「XRP → Hyperliquid」 = 却下経路の説明としてのみ残存可

---

## 必須末尾タグ

`[Final-Design-Summary-Verify: R50-PRIORITY2-FINAL-DESIGN-SUMMARY-FOR-GPT-V4]`
`[NextActor: GPT]`
`[EndTime-JST: 10:40:00 (real Bash取得予定)]`
`[priority2-consensus_candidate-current: false]`
`[is_shuji_represented: false]`
`[no_proxy_violation: true]`
