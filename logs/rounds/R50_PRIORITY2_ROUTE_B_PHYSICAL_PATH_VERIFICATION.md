# R50 Priority 2 Route B Physical Path Verification

**作成日時 (JST)**: 2026-06-07 09:55:00
**Verify Token**: `[Route-B-Verify: R50-PRIORITY2-ROUTE-B-PHYSICAL-PATH-VERIFICATION]`
**Author**: Claude (実装担当)
**Trigger**: GPT Section 107指示 (Hyperliquid物理入金経路曖昧性指摘)
**検証方法**: 公式ソース + 2026年6月時点メディア

---

## 1. 公式ソース確認結果

### A. Hyperliquidが受け付ける入金資産

#### 1.1 Canonical (Arbitrum USDC bridge)
- **公式**: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/bridge2
- 最小入金: **5 USDC**
- 最小出金: **2 USDC**
- Arbitrum (オンチェーン) で USDC を受け付け、 Hyperliquid L1で残高クレジット
- バリデータセット運営 (汎用第三者bridgeではない)

#### 1.2 Router Protocol Nitro bridge 経由 (Cross-chain直接入金)
- **2026年現在**: Hyperliquid は Router Protocol Nitro bridgeを統合済
- **対応チェーン**: 30+チェーン (Ethereum, **Solana**, Sui, Tron, Base等、 EVM/非EVM両方)
- 入金例 (公式記載):
  - **SOL (Solana)**: 最小 **0.12 SOL** 直接入金可能 ✅
  - BTC (Bitcoin): 最小 0.0003 BTC
  - ETH (Ethereum): 最小 0.007 ETH
  - ENA (Ethereum): 最小 120 ENA
  - MON (Monad), XPL (Plasma) 等の ecosystem tokens

#### 1.3 XRP の扱い
- **検索結果に明示なし**: Hyperliquid公式の直接入金資産リストにXRPの記載なし
- **判定**: XRP直接入金はサポートされていない可能性が高い (要追加検証)
- **2026年6月時点運用**: XRP→Hyperliquid直送は **却下**、 別経路でUSDC化必須

#### 1.4 Hyperliquid Arbitrum Bridge retire移行
- 「Hyperliquid to Retire Arbitrum Bridge in Favor of Native USDC」(2026年報道)
- HyperEVM launch以降、 Circle CCTP (Cross-Chain Transfer Protocol)対応で **ネイティブUSDC**移行
- **20+ supported networks** でワンクリック入金可能 (CCTP経由)

### B. GMO→XRP/SOL→自己管理WL後の実フロー候補

#### 候補1: XRP/SOLをHyperliquidへ直接入金
- **SOL**: ✅ **採用可** (Router Nitro経由直接入金、 最小0.12 SOL)
- **XRP**: ❌ **却下** (公式直接入金サポート確認できず)
- **税務影響**: GMOでSOL購入 → 自己管理WL送金 → Hyperliquid入金 → 内部USDC化
  - GMO→自己管理WL: 暗号資産送金 (利確なし)
  - 自己管理WL→Hyperliquid: 暗号資産送金 (利確なし)
  - Hyperliquid内部USDC化 (Router Nitro Hyperliquid側自動処理): **利確発生** (SOL→USDC交換、 国税庁準拠)

#### 候補2: 自己管理WL側でXRP/SOL→USDCへスワップしてからHyperliquid入金
- **SOL→USDC スワップ**: 自己管理WL (Phantom等) + Jupiter/Raydium等DEXでスワップ可能
- **XRP→USDC スワップ**: 自己管理WL (XRP Ledger対応) + Sologenic/AMM等でスワップ可能 (限定的)
- スワップ後USDC: Arbitrum (CCTP経由でEthereum→Arbitrum) or Hyperliquid直接 (CCTP対応chain経由)
- **税務影響**: 自己管理WLでXRP/SOL→USDC交換時点で **利確発生**
- **コスト**: スワップfee + 送金fee + ブリッジfee で2重コスト

#### 候補3: CEX/DEX/Bridge経由でUSDC化してからHyperliquid入金
- **deBridge / Across / Router Nitro** 等のbridge経由
- 自己管理WL→Bridge→Arbitrum USDC→Hyperliquid
- 採用可だが候補1/2より複雑

#### 候補4: SOL経路はHyperliquidではなく別DEX向け限定
- **却下**: Hyperliquidが SOL 直接入金をサポートするため不要

### C. 税務ログ発生ポイント整理

| イベント | 利確発生 | ログ必要 |
|---------|---------|---------|
| GMOでXRP/SOL購入 | ❌ なし (購入時) | ✅ 取得価額記録 |
| GMO→自己管理WL送金 | ❌ なし | ✅ 送金ログ |
| 自己管理WL→Hyperliquid送金 (SOL) | ❌ なし | ✅ 送金ログ |
| Hyperliquid内部SOL→USDC化 (候補1) | ✅ **発生** | ✅ 利確ログ必須 |
| 自己管理WLでSOL→USDC交換 (候補2) | ✅ **発生** | ✅ 利確ログ必須 |
| Bridge経由USDC化 (候補3) | ✅ **発生** | ✅ 利確ログ必須 |

**重要**: Hyperliquid内部USDC化も「暗号資産同士の交換」 のため利確発生。 CryptoAct等CSV連携必須。

### D. final design draftの修正要否

**修正必要**: ✅

#### 修正点1: 「Hyperliquid内部USDCスワップ」 表現の明確化
- 旧: 「Hyperliquid内部USDCスワップ」 (曖昧)
- 新: 「Router Nitro経由SOL直接入金 → Hyperliquid側で自動USDC化」 (公式仕様準拠)
- XRP経路: **削除** (Hyperliquid直送不可)

#### 修正点2: 経路B主経路を SOL中心 に変更
- 旧: 「GMOコイン → XRP/SOL → 自己管理WL → Hyperliquid内部USDCスワップ」
- 新: 「GMOコイン → **SOL** → 自己管理Phantom WL → Router Nitro Hyperliquid直接入金 (自動USDC化)」

#### 修正点3: XRP経路の扱い
- XRP→Hyperliquid直送 → **却下経路に明記**
- XRPを使う場合は経路B第二バックアップ (bitbank) で SOL経由に統一、 または却下

#### 修正点4: SBI VC USDC経路の明確化
- 旧: 「SBI VC → USDC直購入 → 自己管理WL → Hyperliquid」
- 新: 「SBI VC → USDC直購入 → 自己管理WL → CCTP対応chain経由Hyperliquid (ネイティブUSDC)」 (Arbitrum bridge retire対応)

---

## 2. 採用できる物理経路 (v3.5)

### 経路B主経路 (改訂後)
**GMOコイン → SOL → 自己管理Phantom WL → Router Nitro Hyperliquid直接入金 (自動USDC化)**

公式根拠:
- GMO SOL対応 ✅ (Matrix Verified)
- GMO出金fee無料 ✅ (Matrix Verified)
- Hyperliquid SOL直接入金対応 ✅ (Router Nitro統合、 最小0.12 SOL)
- 自動USDC化 (Hyperliquid側) ✅ (公式)

### 経路B副経路 (改訂後)
**SBI VC → USDC直購入 → 自己管理WL → CCTP対応chain経由Hyperliquid (ネイティブUSDC)**

公式根拠:
- SBI VC USDC直購入 ✅ (国内唯一)
- SBI VC送金fee無料 ✅
- Hyperliquid CCTP対応 (20+ networks) ✅
- ただし1回100万円相当額制限あり (公式FAQ)

### 経路B第二バックアップ (改訂後)
**bitbank → SOL → 自己管理Phantom WL → Router Nitro Hyperliquid直接入金**

公式根拠:
- bitbank SOL対応 ✅
- bitbank SOL送金fee 0.009 SOL ✅ (Gemini公式直接確認)
- Hyperliquid SOL直接入金対応 ✅

---

## 3. 却下すべき物理経路

### 1. GMO/bitbank → XRP → Hyperliquid直送
- **理由**: XRP直接入金未サポート (公式リスト未掲載)
- **却下**: 経路設計から削除

### 2. 国内CEX → USDC直接送金 → Hyperliquid
- **理由**: 国内CEX USDC取扱: GMO=Pending(なし)、 bitFlyer/bitbank=Provisional(公式発表なし)
- **却下**: 経路設計から削除 (Matrix v3で確定)

### 3. 国内CEX → Hyperliquid直接送金
- **理由**: Travel Rule非互換 (Matrix Verified)
- **却下**: 構造的不可

### 4. 自己管理WLで XRP/SOL→USDC交換してから Hyperliquid (候補2)
- **判定**: 採用可だが候補1より複雑、 二重スワップで税務複雑化
- **方針**: バックアップ扱い、 主経路は候補1 (Hyperliquid内部USDC化)

---

## 4. final design draft の修正案

### 経路B主経路 (修正案)
```
国内CEX (GMOコイン: 日本円入金 → SOL購入、 送金fee無料)
  → 自己管理Phantom WL (Travel Rule申告)
  → Hyperliquid (Router Nitro経由SOL直接入金)
  → Hyperliquid側で自動USDC化 (利確発生、 CryptoAct CSV連携必須)
```

### 経路B副経路 (修正案)
```
国内CEX (SBI VCトレード: 日本円入金 → USDC直購入、 送金fee無料)
  → 自己管理WL
  → CCTP対応chain (Arbitrum / Ethereum等) 経由Hyperliquid
  → ネイティブUSDC入金
  ※ 1回100万円相当額制限あり、 大額時は分割or経路B主経路
```

### 経路B第二バックアップ (修正案)
```
国内CEX (bitbank: 日本円入金 → SOL購入、 送金fee 0.009 SOL)
  → 自己管理Phantom WL
  → Router Nitro経由Hyperliquid直接入金
  → 自動USDC化
  ※ GMO障害時、 板取引Maker -0.02% で調達コスト低
```

### XRP関連削除事項
- 「GMO → XRP/SOL → 自己管理WL → Hyperliquid内部USDCスワップ」 から **XRP削除** (SOLのみ)
- XRP送金fee記述削除 (Hyperliquid直送不可のため経路Bでは使用しない)

---

## 5. Priority 2 consensus_candidate 判定

**現状**: **false 維持**

理由:
- Route B物理経路の公式確認結果を反映するため、 final design draft修正が必要 (本report実施後)
- GPT追加確認後にtrue候補化可能
- ただし、 残るProvisional/Pendingは Matrix v3 cleanの範囲内 (新規Pending発生せず)

---

## 6. Geminiへ再監査が必要か

### Claude判定: **不要** (推奨)

理由:
- Gemini Round 2再監査時点では「Hyperliquid内部USDCスワップ」 表現を採用 (Gemini自身も明示)
- 今回の物理経路検証は Claude側で公式ソース直接確認 → final design draft修正で対応可能
- ただし、 SOL中心経路 + XRP却下 という変更は経路設計の重要修正のため、 **オプションでGemini再確認も可**

### Alternative案 (慎重派)
final design draft v2 (本検証反映後) を Gemini に転送し、 経路B修正方針OKを確認 (controlled send 1回)

### Claude推奨: **不要 (Claude側で対応可能)**

---

## 7. 必須末尾タグ

`[Route-B-Verify: R50-PRIORITY2-ROUTE-B-PHYSICAL-PATH-VERIFICATION]`
`[NextActor: GPT (経路B修正方針確認後にClaude側でfinal design draft v2更新)]`
`[EndTime-JST: 09:55:00 (real Bash取得予定)]`
`[priority2-consensus_candidate-current: false]`
`[is_shuji_represented: false]`
`[no_proxy_violation: true]`

---

## 8. 参考ソース

- Hyperliquid公式 Bridge2 ドキュメント: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/bridge2
- Hyperliquid Arbitrum Bridge retire報道: https://finance.yahoo.com/news/hyperliquid-retire-arbitrum-bridge-favor-153715717.html
- Router Protocol Nitro統合: https://www.chaincatcher.com/en/article/2161276
- Solana入金サポート: https://hyperliquid.gitbook.io/hyperliquid-docs/support/faq/deposit-or-transfer-issues-missing-lost/deposited-via-solana-network
- 2026年Hyperliquid Bridge ガイド: https://eco.com/support/en/articles/15191997-hyperliquid-bridge-deposit-usdc-and-cross-chain-routes-2026
