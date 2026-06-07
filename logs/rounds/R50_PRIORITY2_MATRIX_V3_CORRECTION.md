# R50 Priority 2 Matrix v3 Correction

**作成日時 (JST)**: 2026-06-07 08:57:13
**Verify Token**: `[Matrix-V3-Correction-Verify: R50-PRIORITY2-MATRIX-V3-CORRECTION]`
**Author**: Claude (実装担当)
**Trigger**: GPT Section 102指示 (経路A/B名称衝突修正 + Matrix集計一本化)

---

## 1. 修正理由

v2 Matrix/Audit/Revision で経路A/B名称衝突が発生していた:
- **本来の経路A** = Exness CFD検証枠 (国内銀行振込/クレカ → Exness)
- **本来の経路B** = 国内CEX → Hyperliquid系 (GMO/SBI VC/bitbank)

ただし v2 では Operational decision 等で「経路A主経路」 を **GMOコイン中継基地** や **DEX内部USDCスワップ** の意味で誤用していた。 これは v1の「経路A=GMO主経路」 表記 (Round 50第1周時点の暫定) を v2でも引きずった結果。

**GPT Section 102指摘**:
- 経路A/B定義を固定 (Exness=A、 Hyperliquid系=B)
- Matrix集計を一本化 (Verified 10 / Provisional 4 / Pending 1 / Contradicted 0)
- 誤記6箇所の修正 (Matrix Claim 2/9/11/12/15 + Audit + Revision)

これらをv3で反映。

---

## 2. A/B定義の固定

**経路A**: Exness / MT5 / BTC CFD検証枠
- 国内銀行振込/クレカ/デビットカード → Exness
- 用途: CFD検証・MT5運用
- **Hyperliquidとは混ぜない**

**経路B**: 国内CEX → 自己管理ウォレット → Hyperliquid/dYdX
- 主経路: GMOコイン → XRP/SOL → 自己管理WL → Hyperliquid内部USDCスワップ
- 副経路: SBI VC → USDC直購入 → 自己管理WL → Hyperliquid
- 第二バックアップ: bitbank → XRP/SOL → 自己管理WL → Hyperliquid

**今後の議論で経路A/B定義の再変更は禁止** (GPT Section 102明示)。

---

## 3. Matrix集計の一本化

| Status | Count | Claims |
|--------|-------|--------|
| **Verified** | **10** | 1, 2, 4, 8, 9, 10, 11, 12, 13, 15 |
| **Provisional** | **4** | 3, 6, 7, 14 |
| **Pending** | **1** | 5 |
| **Contradicted** | **0** | - |
| **合計** | **15** | - |

---

## 4. 修正した誤記一覧

### Matrix (R50_PRIORITY2_SOURCE_VERIFICATION_MATRIX.md)
| Claim | 誤 (v2) | 正 (v3) |
|-------|---------|---------|
| 2 (GMO SOL) | GMOコインを経路Aの中継基地として採用 | GMOコインを経路B主経路の中継基地として採用 |
| 9 (GMO出金fee無料) | GMOコインを経路A主経路の中継基地最優先 | GMOコインを経路B主経路の中継基地最優先 |
| 11 (XRP fee/速度) | 経路A主経路のXRP送金候補 | 経路B主経路のXRP送金候補 |
| 12 (SOL fee/速度) | 経路A主経路のSOL送金候補 | 経路B主経路のSOL送金候補 |
| 15 (税務利確) | 経路A主経路 (DEX内部USDCスワップ) 時の利確タイミング | 経路B主経路 (DEX内部USDCスワップ) 時の利確タイミング |

### Audit (R50_PRIORITY2_ROUND2_CLAUDE_SOURCE_AUDIT.md)
- Section 5 経路定義書き換え (経路A=Exness / 経路B=Hyperliquid系)
- 経路Aの場合 → 経路B主経路の場合
- 経路Aに一本化 → 経路B主経路に一本化
- 経路A主経路: DEX内部USDCスワップ → 経路B主経路: DEX内部USDCスワップ

### Revision (R50_PRIORITY2_ROUND2_MATRIX_REVISION.md)
- 経路定義書き換え + 全Operational decisionの経路A→経路B修正
- 集計表 (Verified 10 / Provisional 4 / Pending 1 / Contradicted 0) 確定明示

---

## 5. 修正後のPriority 2暫定経路

### 経路A (Exness CFD検証枠)
**国内銀行振込/クレカ/デビットカード → Exness → MT5 / BTC CFD検証**
- 用途: CFD検証・MT5運用のみ
- **Hyperliquidとは混ぜない**

### 経路B (Hyperliquid本命)
- **主経路**: GMOコイン → XRP/SOL → 自己管理WL → Hyperliquid内部USDCスワップ
- **副経路**: SBI VC → USDC直購入 → 自己管理WL → Hyperliquid (100万円/回制限)
- **第二バックアップ**: bitbank → XRP/SOL → 自己管理WL → Hyperliquid (送金fee XRP 0.1/SOL 0.009)

---

## 6. consensus_candidate=false維持理由

- Matrix/Audit/Revision の Claude v3修正完了 ✅
- ただし、 **設計書 (実装) 側のPriority 2記述修正が未完**:
  1. GMO起点USDC直送記述削除
  2. 経路B主経路「DEX内部USDCスワップ」 記述追加
  3. SBI VC 100万円/回制限ハンドリング規定追加
- これらが完了 + GPT最終確認で consensus_candidate=true 候補化可能

---

## 7. Gemini追加送信は不要というClaude案

### Claude推奨フロー
1. v3 Matrix/Audit/Revision/Correction を GPT へ提示 → GPT判定
2. GPT判定OKなら、 Claude実装担当として設計書修正 (Priority 2 final design) に進む
3. 設計書修正完了後、 GPT最終確認 → consensus_candidate=true 候補
4. 3者合意 → Shujiさん最終承認

### Gemini追加送信不要の理由
- Gemini Round 2再監査で必要な公式ソース確認は完了
- 経路A/B名称衝突修正はGPT司会整理であり、 Geminiの判定 (経路A=Exness/経路B=Hyperliquid) と完全整合
- Geminiの判定軸 (公式ソース取扱可否) はv3でも変更なし、 GeminiがVerifiedとした 10claimsは v3 でも Verified維持
- 残るは Claude実装担当の設計書修正のみ

### Alternative案 (慎重派)
v3 Matrix/Audit/Revision を Gemini に最終確認のため転送 (追加 controlled send 1回)。 Geminiが「v3 経路A/B名称修正OK+設計書修正方針OK」 を明示すれば consensus_candidate=true 候補化を補強できる。

### Claude推奨: **推奨フロー (Gemini追加送信なし)**

---

## 8. 必須末尾タグ

`[Matrix-V3-Correction-Verify: R50-PRIORITY2-MATRIX-V3-CORRECTION]`
`[NextActor: GPT]`
`[EndTime-JST: 08:57:13 (real Bash取得)]`
`[priority2-consensus_candidate-current: false]`
`[matrix_v3_summary: Verified=10 / Provisional=4 / Pending=1 / Contradicted=0]`
`[route_definition_v3_fixed: 経路A=Exness / 経路B=Hyperliquid系]`
`[is_shuji_represented: false]`
`[no_proxy_violation: true]`
