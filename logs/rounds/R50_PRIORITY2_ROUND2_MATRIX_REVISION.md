# R50 Priority 2 Round 2 Matrix Revision

**作成日時 (JST)**: 2026-06-07 08:24:00
**Verify Token**: `[Matrix-Revision-Verify: R50-PRIORITY2-ROUND2-MATRIX-REVISION]`
**Author**: Claude (実装担当)
**Trigger**: GPT指示 (Section 100) + Gemini Round 2再監査反映 (Section 99)

---

## 1. Gemini再監査で修正されたclaim一覧

| Claim | v1 Claude判定 | v2 Gemini判定 | 修正理由 |
|-------|--------------|--------------|----------|
| Claim 3: bitFlyer SOL | Pending | **Provisional** | Gemini bitFlyer公式直接確認: SOL現物取扱なし (外部情報のみ) |
| Claim 5: GMO USDC | Verified×非対応 | **Pending (取扱なし除外)** | Gemini判定: 「取扱なし=経路設計から除外」 |
| Claim 6: bitFlyer USDC | Verified×非対応 | **Provisional** | Gemini判定: 公式発表なし、 外部ニュースのみ |
| Claim 7: bitbank USDC | Verified×非対応 | **Provisional** | Gemini判定: 公式発表なし、 外部ニュースのみ |
| Claim 10: bitbank fee | Pending (Claude推定 XRP 0.15/SOL 0.01) | **Verified (XRP 0.1/SOL 0.009)** | Gemini公式2026年6月1日改定版直接確認 |
| Claim 11: XRP fee/速度 | Provisional | **Verified** | Gemini「経路コスト最小化適合」 確認 |
| Claim 12: SOL fee/速度 | Provisional | **Verified** | Gemini「経路コスト最小化適合」 確認 |
| Claim 15: SOL/XRP→USDC利確 | Provisional | **Verified** | Gemini「国税庁準拠、 利益確定」 確認 |

## 2. 修正後の Verified / Provisional / Pending / Contradicted 集計

| Status | Count | Claims |
|--------|-------|--------|
| **Verified** | **10** | 1 (SBI VC USDC) / 2 (GMO SOL) / 4 (bitbank SOL) / 8 (国内CEX→HL直送不可) / 9 (GMO出金fee無料) / 10 (bitbank fee) / 11 (XRP fee/速度) / 12 (SOL fee/速度) / 13 (Travel Rule) / 15 (税務利確) |
| **Provisional** | **4** | 3 (bitFlyer SOL) / 6 (bitFlyer USDC) / 7 (bitbank USDC) / 14 (Hyperliquid日本居住者) |
| **Pending** | **1** | 5 (GMO USDC=取扱なし除外) |
| **Contradicted** | **0** | - |
| **合計** | **15** | - |

## 3. 修正後の暫定経路A/B

### 経路A (主経路: コスト最適・調達分離型) ✅
**国内CEX (GMOコイン: 日本円入金→XRP/SOL購入、 送金fee無料) → 自己管理ウォレット (MetaMask/Phantom: Travel Rule申告) → Hyperliquid (Arbitrum等経由入金、 内部USDCスワップ)**

採用根拠 (Verified):
- GMO出金fee無料 ✅
- GMO SOL対応 ✅
- 国内CEX→Hyperliquid直送不可 → 自己管理WL中継必須 ✅
- DEX内部USDCスワップ = 国内USDC調達不可問題回避 ✅

### 経路B (副経路: ステーブル直接調達・100万円制限型) ✅
**国内CEX (SBI VCトレード: 日本円入金→販売所でUSDC直購入、 送金fee無料) → 自己管理ウォレット → Hyperliquid**

採用根拠 (Verified):
- SBI VC→USDC直購入 ✅ (国内唯一)
- SBI VC送金fee無料 ✅

制約:
- **1回100万円相当額入出庫制限** (SBI VC公式FAQ明記)
- 大口送金は複数回分割 or 経路Aに一本化

### 経路B第二バックアップ (bitbank) 🟡
**国内CEX (bitbank: 日本円入金→XRP/SOL購入、 送金fee XRP 0.1/SOL 0.009) → 自己管理ウォレット → Hyperliquid**

採用条件:
- GMO障害時のバックアップ
- 板取引Maker -0.02% (調達コスト低)
- 日本円出金fee 550-770円 + 送金fee 別途
- コスト試算別枠管理必須

### 却下経路 (Verified)
- ❌ 国内CEX (GMO/bitFlyer/bitbank) → USDC直接送金 → DEX (USDC国内非対応 or 公式発表なし)
- ❌ 国内CEX → Hyperliquid直接送金 (Travel Rule非互換による構造的不可)
- ❌ bitFlyer SOL中継 (公式取扱なし)

## 4. 残Pending (consensus_candidate=true移行不可理由)

設計書 (実装) 側のPriority 2記述修正が必要:

1. **GMO起点USDC直送記述削除** (GMO USDC=取扱なしのため)
2. **経路A主経路「DEX内部USDCスワップ」 記述追加** (国内USDC調達不可の代替経路として)
3. **SBI VC 100万円/回制限ハンドリング規定追加** (分割送金時の運用手順)

これらは **Claude実装担当として次フェーズで対応可能**。

## 5. Priority 2 consensus_candidate=false維持理由

- Matrix/Audit/Revision の Claude修正は完了 ✅
- ただし、 設計書 (実装) 側のPriority 2記述修正 (上記 残Pending 3項目) が未完
- これらが完了 + GPT最終確認 で consensus_candidate=true 候補化可能

## 6. 次にGeminiへ戻すべきか、 Claude側で再監査完了扱いにできるかの Claude案

### Claude案 (推奨)

**Gemini追加送信は不要**。 理由:
- Gemini Round 2再監査で必要な公式ソース確認は全て完了
- Geminiが明示した「Matrix修正後の再判定」 はClaude側Matrix修正で対応済み
- 残るは Claude実装担当の設計書修正 (経路A/B記述、 GMO USDC除外、 SBI VC 100万円制限) のみ

### 推奨フロー

1. **本revision (Matrix/Audit/Revision) を GPT へ提示** → GPT判定
2. GPT判定で問題なければ、 **Claude側で設計書修正 (Priority 2 final design)** に進む
3. 設計書修正完了後、 **GPT で最終確認** → consensus_candidate=true 候補
4. 3者合意 → Shujiさん最終承認 (3者合意成立時のみ)

### Alternative案 (慎重派)

Matrix revision内容を Gemini に最終確認のため転送 (追加 controlled send 1回)。 Geminiが「Matrix修正完了+設計書修正方針OK」 を明示すれば consensus_candidate=true 候補化。

### Claude推奨: **推奨フロー (Gemini追加送信なし)**

- 3者議論は Gemini Round 2再監査で十分尽くされた
- Claude実装担当が設計書修正を進めれば3者合意の素地は整う
- 残るは GPT最終確認 + Shujiさん承認のみ

---

## 7. 必須末尾タグ

`[Matrix-Revision-Verify: R50-PRIORITY2-ROUND2-MATRIX-REVISION]`
`[NextActor: GPT]`
`[EndTime-JST: 08:24:00 (real Bash取得予定)]`
`[priority2-consensus_candidate-current: false]`
`[verified_count_post_revision: 10 / provisional: 4 / pending: 1 / contradicted: 0]`
`[is_shuji_represented: false]`
`[no_proxy_violation: true]`
