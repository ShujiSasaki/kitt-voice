# R50 Priority 2 Final Design v4 Revision

**作成日時 (JST)**: 2026-06-07 10:40:00
**Verify Token**: `[V4-Revision-Verify: R50-PRIORITY2-FINAL-DESIGN-V4-REVISION]`
**Author**: Claude (実装担当)
**Trigger**: GPT指示 Section 111 + Gemini Route B 再監査 Section 110

---

## 1. Gemini Route B再監査の採用内容

Section 110のGemini判定を100%採用:

### 採用判定 (Gemini承認)
- ✅ 経路B方向性 (Solana/CCTPマルチチェーン構造): 極めて妥当
- ✅ Arbitrum bridge依存脱却 (Hyperliquid Arbitrum bridge retire対応): 完璧
- ✅ Q2 XRP直送却下: 妥当 (永久却下)
- ✅ Q4 SBI VC→USDC→CCTP対応chain: 完全に妥当

### 採用修正指摘 (Gemini指摘)
- ✅ Q1 自動USDC化は誤認: SOLは Hyperliquid Spotアカウントに着金、 マニュアル売却でUSDC化
- ✅ Q3 旧表現修正: 「Hyperliquid内Spot市場でSOLを売却しUSDC化」
- ✅ Q5 税務トリガー明示: SOL→USDC交換時点で利確発生
- ✅ Q6 v3.5案前修正点: 「Spot着金後にUSDCへ交換」 への表現修正
- ✅ Q7 consensus_candidate=false維持: 修正反映後Round 3でtrue承認

---

## 2. v3.5 → v4 修正一覧

### 経路B主経路
- **旧 (v3.5)**: GMO → SOL → Phantom自己管理WL → Router Nitro Hyperliquid直接入金 → Hyperliquid側で自動USDC化
- **新 (v4)**: GMO → SOL → Phantom自己管理WL → Router Nitro等経由でHyperliquidへSOL入金 → HyperliquidのSpotアカウントにSOLとして着金 → Hyperliquid内SOL/USDC Spot市場で売却してUSDC取得

### 経路B第二バックアップ (bitbank)
- **旧 (v3.5)**: bitbank → SOL → Phantom自己管理WL → Router Nitro Hyperliquid直接入金 → 自動USDC化
- **新 (v4)**: bitbank → SOL → Phantom自己管理WL → Router Nitro等経由でHyperliquidへSOL入金 → SpotアカウントにSOL着金 → SOL/USDC Spot市場で売却してUSDC取得

### 禁止表現の全削除 (採用経路本文より)
- ❌ 「自動USDC化」
- ❌ 「Hyperliquid側で自動USDC化」
- ❌ 「自動スワップ」
- ❌ 「着金時にUSDC化」

### Spot Fills税務ログ7項目追加
Hyperliquid内 SOL → USDC Spot売却時、 以下7項目を絶対消失不可で保存:
1. SOL数量
2. USDC獲得量
3. 約定時刻 (UTC + JST)
4. 約定価格 (SOL/USDC レート)
5. 約定時点の USD/JPY 円換算レート
6. 手数料 (Hyperliquid Spot taker/maker fee)
7. 取引ID (Hyperliquid Spot Fill ID)

### XRP直送永久却下追加
- 旧 (v3.5): XRP却下 (公式リスト未掲載)
- 新 (v4): **永久却下** + 「XRPを使う場合は別途USDC化経路の再検証が必要」 明記

### SBI VC副経路維持
- v3.5から変更なし (Gemini Q4で完全に妥当判定)
- 100万円/回制限明記維持

---

## 3. 自動USDC化削除のgrep結果

### 設計本文 (採用経路) のチェック

| Pattern | カウント | 残存箇所の意味 |
|---------|---------|---------------|
| 「自動USDC化」 | 4件残存 | 採用経路本文ではない (禁止表現リスト + 削除確認説明) |
| 「自動スワップ」 | 1件残存 | 採用経路本文ではない (禁止表現リスト) |
| 「Hyperliquid側で自動」 | 1件残存 | 採用経路本文ではない (禁止表現リスト) |
| 「XRP/SOL → Hyperliquid」 | 0件 | 完全削除 |
| 「XRP → Hyperliquid」 | 1件残存 | 却下経路の見出し: `### 4. **GMO/bitbank → XRP → Hyperliquid直送** (v4 新規追加却下)` |

### 残存箇所の詳細 (許容範囲)

**「自動USDC化」 残存4件**:
- L50: 「❌ 「自動USDC化」」 (禁止表現リスト)
- L51: 「❌ 「Hyperliquid側で自動USDC化」」 (禁止表現リスト)
- L188: 「✅ 「自動USDC化」 表現の全削除 (v4で対応済み)」 (設計書側残作業の完了確認)
- L219: 「`[v4_revisions_applied: 自動USDC化全削除 + ...]`」 (メタタグ)

**「XRP → Hyperliquid」 残存1件**:
- L134: 「### 4. **GMO/bitbank → XRP → Hyperliquid直送** (v4 新規追加却下)」 (却下経路の見出し)

### grep結果判定: ✅ **修正成功**
- 採用経路本文に禁止表現は残っていない
- 残存はすべて「禁止表現リスト」 「削除確認説明」 「却下経路見出し」 として正当な目的で残されている

---

## 4. Spot Fills税務ログ仕様 (v4 確定)

### 税務トリガーの整理

| イベント | 利確発生 | 保存項目 |
|---------|---------|---------|
| GMO/bitbank での SOL購入 | ❌ なし | 取得価額 (円建) 記録 |
| GMO/bitbank → 自己管理WL → Hyperliquid 送金 | ❌ なし (自己名義間) | Travel Rule申告ログ |
| Hyperliquid Spotアカウント着金 | ❌ なし | 着金履歴ログ |
| **Hyperliquid内 SOL → USDC Spot売却** | ✅ **発生** | **Spot Fills 7項目 (必須)** |

### Spot Fills保存仕様
```
{
  "sol_amount": 1.234,          // 売却したSOL数量
  "usdc_amount": 150.0,         // 取得したUSDC数量
  "executed_at_utc": "2026-06-07T01:40:00Z",
  "executed_at_jst": "2026-06-07T10:40:00+09:00",
  "execution_price": "121.55",  // SOL/USDC レート
  "usd_jpy_rate": "147.20",     // 約定時点の円換算レート
  "fee_usdc": "0.045",          // Hyperliquid Spot手数料
  "trade_id": "0x123abc..."     // Hyperliquid Spot Fill ID
}
```

### CSV連携設計
- 出力フォーマット: CryptoAct CSV準拠
- 連携頻度: 月次自動エクスポート (確定申告時の年次データも自動生成)
- 計算ロジック: 国税庁「暗号資産に関する税務上の取扱い」 準拠雑所得計算

---

## 5. 経路B v4 確定案

### 経路B主経路 ✅
**GMO (日本円→SOL購入、 送金fee無料) → Phantom自己管理WL (Travel Rule申告) → Router Nitro等経由でHyperliquidへSOL入金 → Hyperliquid SpotアカウントにSOL着金 → Hyperliquid内 SOL/USDC Spot市場で売却してUSDC取得**

### 経路B副経路 ✅
**SBI VC (日本円→USDC直購入、 送金fee無料) → 自己管理WL → CCTP対応chain (Base/Ethereum/Avalanche等) 経由でHyperliquidへネイティブUSDC入金** (1クリック)
- 制約: 1回100万円相当額、 大額時は分割or経路B主経路切替

### 経路B第二バックアップ 🟡
**bitbank (日本円→SOL購入、 板取引Maker -0.02%、 送金fee 0.009 SOL) → Phantom自己管理WL → Router Nitro等経由でHyperliquidへSOL入金 → Spotアカウント着金 → SOL/USDC Spot市場で売却**
- GMO障害時のみ、 コスト試算別枠

---

## 6. consensus_candidate=false維持理由

- v4反映完了 ✅
- ただし、 GPT最終確認待ち
- 3者合意 (Gemini Round 3最終確認) 後にtrue候補化可能

---

## 7. Gemini Round 3へ回すべきかのClaude案

### Claude推奨: **回すべき** (Gemini Round 3最終確認実施)

理由:
- v4で経路B中核の「Spot着金 → Spot売却 → USDC取得」 仕様を Gemini Section 110指摘に従って修正
- Spot Fills税務ログ7項目もGemini指摘の「Spot Fills (現物約定履歴) 保存」 を具体化
- Geminiが「Round 3でtrue承認」 と明示しているため、 Round 3で最終確認が論理的に整合
- GPT判断 (Section 111) も「修正後にGPT確認 → Gemini Round 3最終確認」 と明示

### Gemini Round 3送信案 (Q1-Q5)
1. Spot着金仕様の正確性確認
2. Spot Fills税務ログ7項目の十分性確認
3. SBI VC副経路の最終承認
4. XRP却下の永久性確認
5. consensus_candidate=true移行可否最終判定

---

## 8. 必須末尾タグ

`[V4-Revision-Verify: R50-PRIORITY2-FINAL-DESIGN-V4-REVISION]`
`[NextActor: GPT]`
`[EndTime-JST: 10:40:00 (real Bash取得予定)]`
`[priority2-consensus_candidate-current: false]`
`[v4_revisions_applied: 自動USDC化全削除 + Spot Fills税務ログ7項目追加 + XRP直送永久却下追加]`
`[grep_check_result: 採用経路本文に禁止表現なし、 残存は禁止表現リスト/却下経路見出し/削除確認説明のみ]`
`[recommended_next: GPT確認 → Gemini Round 3最終確認 → consensus_candidate=true候補化 → Shujiさん承認]`
`[is_shuji_represented: false]`
`[no_proxy_violation: true]`
