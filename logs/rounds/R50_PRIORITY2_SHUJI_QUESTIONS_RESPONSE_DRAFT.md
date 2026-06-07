# R50 Priority 2 Shujiさん質問への回答ドラフト

**作成日時 (JST)**: 2026-06-07 13:20:00
**Verify Token**: `[Shuji-Questions-Response-Draft-Verify: R50-PRIORITY2-SHUJI-QUESTIONS-RESPONSE-DRAFT]`
**Author**: Claude (実装担当)
**Status**: GPTレビュー前ドラフト (Shujiさん未提示)
**Trigger**: Shujiさん1発目「会議へ発言」 (Section 117直後)

---

## Q1. Phantom自己管理ウォレットとは

### 簡潔な答え
**Solana専用の暗号資産ウォレット (スマホアプリ/Chrome拡張) で、 秘密鍵を Shujiさん自身が管理するタイプ**

### もう少し詳しく
- 「自己管理 (self-custody)」 = 取引所が秘密鍵を持つのではなく、 Shujiさんのスマホ/PCに秘密鍵が保存される
- **対比**: GMOコインや bitbank は「取引所管理」 = 取引所が鍵を持つ
- 自己管理WLが必要な理由: **Travel Rule (送金規制)** + **国内CEX→Hyperliquid直送不可** の構造的制約
  - 国内CEXから直接Hyperliquidに送金はできない
  - 国内CEX → 自己管理WL → Hyperliquid という経路が必須
- Phantom = Solana系の代表的な自己管理WL (他に Solflare 等もある)

### Shujiさんが理解すべきこと
- Phantomを初めて使う場合、 **シードフレーズ (12〜24単語) のバックアップ管理が必須** (紛失すると資金消失)
- スマホ/PCを変えるときは シードフレーズで復元
- **これを失う = Hyperliquid内資金も含めて全消失**

---

## Q2. Router Nitroとは

### 簡潔な答え
**異なるブロックチェーン (Solana/Ethereum/Arbitrum等) 間で資産を移すための「橋」 (bridge) 技術**

### もう少し詳しく
- Hyperliquid本体は独自チェーン (Hyperliquid L1) で動いている
- Solanaの SOLを Hyperliquidに直接入金するには、 「SolanaチェーンからHyperliquidチェーンへ送金できる橋」 が必要
- **Router Nitro** = 2025年1月に Hyperliquidが公式統合した bridgeプロトコル
- 30+チェーン (Solana, Ethereum, Sui, Tron, Base等) からHyperliquidへ 1クリック直接入金できる
- 他にも deBridge / Across 等の bridgeはあるが、 Router Nitroが Hyperliquid公式統合

### Shujiさんが理解すべきこと
- Router Nitroは「Hyperliquid側で公式に組み込まれた送金経路」
- Shujiさんが操作する画面 = Phantom (送金元) + Hyperliquid公式UI (受取確認) のみ
- Router Nitroは裏で動く仕組み (=技術的詳細はShujiさんが直接触らない)
- **最小送金量**: 0.12 SOL (約30 USDC相当 @ 2026年6月時点)

---

## Q3. 手数料概算総額

### 経路B主経路 (GMO→SOL→Phantom→Router Nitro→Hyperliquid→Spot売却)

| ステップ | 手数料 | 概算金額 (10万円送金時) |
|---------|--------|---------------------|
| 1. GMO 日本円入金 | 銀行振込fee (銀行依存) | 0〜660円 (Shuji銀行依存) |
| 2. GMO 販売所 SOL購入 | スプレッド (販売所) | 0.5〜1.0% (500〜1,000円) |
| 3. GMO→Phantom SOL送金 | **無料** | 0円 |
| 4. Phantom→Hyperliquid (Router Nitro) | Solanaオンチェーンfee | ~0.005 SOL ≒ 1円〜数円 |
| 5. Hyperliquid Spot SOL→USDC売却 | Taker fee 0.025%程度 | 25円程度 |
| **合計概算 (10万円送金時)** | | **約500〜1,100円 (0.5〜1.1%)** |

### 経路B副経路 (SBI VC→USDC直購入→CCTP→Hyperliquid)

| ステップ | 手数料 | 概算金額 (10万円送金時) |
|---------|--------|---------------------|
| 1. SBI VC 日本円入金 | 銀行振込fee (銀行依存) | 0〜660円 |
| 2. SBI VC 販売所 USDC購入 | スプレッド | 0.5〜2.0% (500〜2,000円) |
| 3. SBI VC→自己管理WL USDC送金 | **無料** | 0円 |
| 4. CCTP対応chain経由Hyperliquid | Ethereum/Base等のgas fee | 数十円〜数百円 (チェーン依存) |
| 5. Hyperliquid着金 (Spot売却不要) | 0円 | 0円 |
| **合計概算 (10万円送金時)** | | **約500〜2,700円 (0.5〜2.7%)** |
| **制約** | | **1回100万円相当額まで** |

### 経路B第二バックアップ (bitbank→SOL→Phantom→Router Nitro→Hyperliquid→Spot売却)

| ステップ | 手数料 | 概算金額 (10万円送金時) |
|---------|--------|---------------------|
| 1. bitbank 日本円入金 | 銀行振込fee | 0〜660円 |
| 2. bitbank 板取引 SOL購入 | Maker -0.02% (リベート) | -20円 (受取) |
| 3. bitbank→Phantom SOL送金 | **0.009 SOL** | ~2円相当 |
| 4. Phantom→Hyperliquid (Router Nitro) | Solanaオンチェーンfee | 数円 |
| 5. Hyperliquid Spot SOL→USDC売却 | Taker fee 0.025% | 25円 |
| 6. bitbank 日本円出金 fee | 550〜770円 | 550〜770円 |
| **合計概算 (10万円送金時)** | | **約560〜800円 (0.56〜0.8%)** |

### 結論
- **コスト最安**: 経路B主経路 (GMOコイン) = **0.5〜1.1%程度**
- **大額時**: 経路B副経路 (SBI VC) = 100万円/回制限あり
- **GMO障害時**: 経路B第二バックアップ (bitbank) = 0.56〜0.8%程度

⚠️ **注意**: 上記は2026年6月時点の概算。 実際のスプレッド・gas fee・SOL/USDC市場価格で変動。

---

## Q4. Hyperliquidありきだったのか / どこから本物4者会議か / Claude仮想会議の範囲

### Round 50の経緯整理 (時系列)

**Round 49 (Shujiさん承認後)**:
- 議題確定: Bybit撤退 + Hyperliquid主軸 + danjer-DNA完全移植 等
- (注: Round 49は本物4者会議でアジェンダ確定済み)

**Round 50第1周 (2026-06-06頃)**:
- 「取引所インフラ ゼロベース全選択肢リサーチ」 を実施
- **前提条件廃止**: Hyperliquid前提・Wise前提を **一旦廃止**
- 全選択肢リサーチ後、 結果的に Hyperliquid+Exness+GMO/bitbank/SBI VC に収束
- これは Claude仮想会議ではなく、 GPT/Gemini/Claude/Shuji の本物4者会議

**Round 50第2周〜 (2026-06-07)**:
- Shujiさん明示承認 (Shuji#28-31等) でPriority 2に進む
- Priority 2 = 送金・入出金経路の確定

### Hyperliquidありきだったか
**答え**: 半分Yes、 半分No
- **Yes**: Round 49で Hyperliquid主軸はShujiさん承認済みで確定
- **No**: Round 50第1周で「ゼロベースリサーチ」 をやり直し、 結果として Hyperliquidが再選定された (前提条件を一度全廃した上で再選定)

### Claude仮想会議の範囲
- **過去のClaude仮想会議の嘘**: Round 30-47の一部 (Wise送金=規約違反を見落とし)
- **本物4者会議として再検証済み**: Round 49以降、 Round 50全体
- **本物4者会議のなかで Claude単独で進めた範囲**: Claude実装作業 (ファイル更新、 grep、 commit、 push等) のみ。 経路選定・経路除外などの意思決定はGPT/Gemini判定 + Shujiさん発言で確定

### Shujiさんが直接「3択」 等で意思表明した発言
- **Shuji#28**: 「思考=GPT+Gemini+Claude / 実装=Claude」 役割確定
- **Shuji#29「A」**: Phase 1.5 final consensus承認
- **Shuji#31「1」**: 「Phase 1.5実装→Priority 2-7自動進行」 選択
- **Shuji#30**: EndTime-JST drift問題指摘
- **本「会議へ発言」 (本Section 117周辺)**: 用語不明 + 手数料概算要求 + Hyperliquidありき検証 + 監視疲労

### 結論
- Round 49以降 = 本物4者会議
- Hyperliquid選定 = ゼロベースリサーチ + Shujiさん承認の二重チェック済み
- ただし、 Phantom/Router Nitro等の用語はShujiさんに事前説明不足 → 本ドラフトで解消

---

## 必須末尾タグ

`[Shuji-Questions-Response-Draft-Verify: R50-PRIORITY2-SHUJI-QUESTIONS-RESPONSE-DRAFT]`
`[NextActor: GPT]`
`[EndTime-JST: 13:20:00 (real Bash取得予定)]`
`[priority2-consensus_candidate: true]`
`[requires_shuji_final_approval: true]`
`[priority2_approval_paused_by_shuji_questions: true]`
`[is_shuji_represented: false]`
`[no_proxy_violation: true]`
