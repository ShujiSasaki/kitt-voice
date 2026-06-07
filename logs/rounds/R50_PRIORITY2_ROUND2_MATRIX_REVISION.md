# R50 Priority 2 Round 2 Matrix Revision (v3 = GPT経路A/B名称衝突修正反映)

**作成日時 (JST)**: 2026-06-07 08:24:00 (v2) → 08:57:13 (v3)
**Verify Token**: `[Matrix-Revision-Verify: R50-PRIORITY2-ROUND2-MATRIX-REVISION-V3]`
**Author**: Claude (実装担当)
**Trigger**: GPT指示 (Section 100) + Gemini Round 2再監査反映 (Section 99) + GPT v3修正指摘 (Section 102)

---

## 経路定義 (v3固定 - GPT Section 102反映)

**経路A**: Exness / MT5 / BTC CFD検証枠
- 国内銀行振込/クレカ/デビットカード → Exness
- 用途: CFD検証・MT5運用
- **Hyperliquidとは混ぜない**

**経路B**: 国内CEX → 自己管理ウォレット → Hyperliquid/dYdX
- 主経路: GMOコイン → XRP/SOL → 自己管理WL → Hyperliquid内部USDCスワップ
- 副経路: SBI VC → USDC直購入 → 自己管理WL → Hyperliquid
- 第二バックアップ: bitbank → XRP/SOL → 自己管理WL → Hyperliquid

---

## 1. Gemini再監査で修正されたclaim一覧 (v2で対応済み)

| Claim | v1 Claude判定 | v2 Gemini判定 | 修正理由 |
|-------|--------------|--------------|----------|
| Claim 3: bitFlyer SOL | Pending | **Provisional** | Gemini bitFlyer公式直接確認: SOL現物取扱なし (外部情報のみ) |
| Claim 5: GMO USDC | Verified×非対応 | **Pending (取扱なし除外)** | Gemini判定: 「取扱なし=経路設計から除外」 |
| Claim 6: bitFlyer USDC | Verified×非対応 | **Provisional** | Gemini判定: 公式発表なし、 外部ニュースのみ |
| Claim 7: bitbank USDC | Verified×非対応 | **Provisional** | Gemini判定: 公式発表なし、 外部ニュースのみ |
| Claim 10: bitbank fee | Pending (Claude推定 XRP 0.15/SOL 0.01) | **Verified (XRP 0.1/SOL 0.009)** | Gemini公式2026年6月1日改定版直接確認 |
| Claim 11: XRP fee/速度 | Provisional | **Verified** | Gemini「経路Bコスト最小化適合」 確認 |
| Claim 12: SOL fee/速度 | Provisional | **Verified** | Gemini「経路Bコスト最小化適合」 確認 |
| Claim 15: SOL/XRP→USDC利確 | Provisional | **Verified** | Gemini「国税庁準拠、 利益確定」 確認 |

## 2. v3 で修正された経路A/B名称誤記 (GPT Section 102反映)

| 誤 (v2) | 正 (v3) |
|---|---|
| GMOコインを経路A主経路の中継基地として採用 | GMOコインを経路B主経路の中継基地として採用 |
| 経路A主経路のXRP送金候補 | 経路B主経路のXRP送金候補 |
| 経路A主経路のSOL送金候補 | 経路B主経路のSOL送金候補 |
| 経路A主経路 (DEX内部USDCスワップ)時の利確タイミング管理 | 経路B主経路 (DEX内部USDCスワップ)時の利確タイミング管理 |
| GMOコインを経路A主経路の中継基地最優先 | GMOコインを経路B主経路の中継基地最優先 |
| 経路A主経路「DEX内部USDCスワップ」 記述追加 | 経路B主経路「DEX内部USDCスワップ」 記述追加 |

修正対象ファイル:
- `R50_PRIORITY2_SOURCE_VERIFICATION_MATRIX.md` (Claim 2, 9, 11, 12, 15 修正)
- `R50_PRIORITY2_ROUND2_CLAUDE_SOURCE_AUDIT.md` (全面書き直し)
- 本ファイル `R50_PRIORITY2_ROUND2_MATRIX_REVISION.md` (v3更新)

## 3. 修正後の Verified / Provisional / Pending / Contradicted 集計 (v3 = 確定)

| Status | Count | Claims |
|--------|-------|--------|
| **Verified** | **10** | 1 (SBI VC USDC) / 2 (GMO SOL) / 4 (bitbank SOL) / 8 (国内CEX→HL直送不可) / 9 (GMO出金fee無料) / 10 (bitbank fee) / 11 (XRP fee/速度) / 12 (SOL fee/速度) / 13 (Travel Rule) / 15 (税務利確) |
| **Provisional** | **4** | 3 (bitFlyer SOL) / 6 (bitFlyer USDC) / 7 (bitbank USDC) / 14 (Hyperliquid日本居住者) |
| **Pending** | **1** | 5 (GMO USDC=取扱なし除外) |
| **Contradicted** | **0** | - |
| **合計** | **15** | - |

## 4. 修正後の暫定経路 (v3固定 - 名称衝突解消)

### 経路A (Exness CFD検証枠)
**国内銀行振込/クレカ/デビットカード → Exness → MT5 / BTC CFD検証**

- 用途: CFD検証・MT5運用のみ
- **Hyperliquidとは混ぜない**

### 経路B (Hyperliquid本命)

#### 経路B主経路 ✅
**国内CEX (GMOコイン: 日本円入金→XRP/SOL購入、 送金fee無料) → 自己管理ウォレット (MetaMask/Phantom: Travel Rule申告) → Hyperliquid (Arbitrum等経由入金、 内部USDCスワップ)**

採用根拠 (Verified):
- GMO出金fee無料 ✅
- GMO SOL対応 ✅
- 国内CEX→Hyperliquid直送不可 → 自己管理WL中継必須 ✅
- DEX内部USDCスワップ = 国内USDC調達不可問題回避 ✅

#### 経路B副経路 ✅
**国内CEX (SBI VCトレード: 日本円入金→販売所でUSDC直購入、 送金fee無料) → 自己管理ウォレット → Hyperliquid**

採用根拠 (Verified):
- SBI VC→USDC直購入 ✅ (国内唯一)
- SBI VC送金fee無料 ✅

制約:
- **1回100万円相当額入出庫制限** (SBI VC公式FAQ明記)
- 大口送金は複数回分割 or **経路B主経路に一本化**

#### 経路B第二バックアップ (bitbank) 🟡
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

## 5. 残Pending (consensus_candidate=true移行不可理由)

設計書 (実装) 側のPriority 2記述修正が必要:

1. **GMO起点USDC直送記述削除** (GMO USDC=取扱なしのため)
2. **経路B主経路「DEX内部USDCスワップ」 記述追加** (国内USDC調達不可の代替として)
3. **SBI VC 100万円/回制限ハンドリング規定追加** (分割送金時の運用手順)

これらは **Claude実装担当として次フェーズで対応可能**。

## 6. Priority 2 consensus_candidate=false維持理由

- Matrix/Audit/Revision の Claude修正は v3で完了 ✅
- ただし、 設計書 (実装) 側のPriority 2記述修正 (上記 残Pending 3項目) が未完
- これらが完了 + GPT最終確認 で consensus_candidate=true 候補化可能

## 7. Gemini追加送信は不要 (Claude案)

### Claude推奨フロー
1. 本v3 revision (Matrix/Audit/Revision/Correction) を GPT へ提示 → GPT判定
2. GPT判定で問題なければ、 **Claude側で設計書修正 (Priority 2 final design)** に進む
3. 設計書修正完了後、 **GPT で最終確認** → consensus_candidate=true 候補
4. 3者合意 → Shujiさん最終承認

### Gemini追加送信不要の理由
- Gemini Round 2再監査で必要な公式ソース確認は全て完了
- Geminiが明示した「Matrix修正後の再判定」 はClaude側Matrix修正 (v2→v3) で対応済み
- 経路A/B名称衝突修正はGPT指摘 (司会整理) であり、 Geminiの判定とは別軸 (Geminiの「経路A=Exness/経路B=Hyperliquid」 識別と完全整合)
- 残るは Claude実装担当の設計書修正 (経路B主経路記述、 GMO USDC除外、 SBI VC 100万円制限) のみ

### Alternative案 (慎重派)
v3 Matrix/Audit/Revision を Gemini に最終確認のため転送 (追加 controlled send 1回)。 Geminiが「v3 経路A/B修正OK+設計書修正方針OK」 を明示すれば consensus_candidate=true 候補化。

### Claude推奨: **推奨フロー (Gemini追加送信なし)**

---

## 8. 必須末尾タグ

`[Matrix-Revision-Verify: R50-PRIORITY2-ROUND2-MATRIX-REVISION-V3]`
`[NextActor: GPT]`
`[EndTime-JST: 08:57:13 (real Bash取得)]`
`[priority2-consensus_candidate-current: false]`
`[verified_count_v3: 10 / provisional: 4 / pending: 1 / contradicted: 0]`
`[is_shuji_represented: false]`
`[no_proxy_violation: true]`
