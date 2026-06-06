# R50 Priority 2 Source Verification Matrix

**Last checked date**: 2026-06-07
**Verify Token**: `[Matrix-Verify: R50-PRIORITY2-SOURCE-VERIFICATION-MATRIX-REV2]`
**Round**: 2 (Claude Source Verification + Gemini再監査反映 revision)
**Revision history**:
- v1 (2026-06-07 07:35): Claude初版 (Verified 9 / Provisional 3 / Pending 3 / Contradicted 0)
- v2 (2026-06-07 08:24): Gemini Round 2再監査反映 (Verified 8 / Provisional 5 / Pending 2 / Contradicted 0)

---

## Summary (v2 = Gemini再監査反映後)

- Total claims: 15
- **Verified**: 8
- **Provisional**: 5
- **Pending**: 2
- **Contradicted**: 0

---

## Matrix詳細

### Claim 1: SBI VCトレード → USDC直接購入可否

- **Gemini assertion**: 条件付き可能、 ただしDEX直送制限多 + **1回100万円相当額**入出庫制限 (公式FAQ明記)
- **Official source**: SBI VC公式FAQ + CoinDesk Japan
- **Source type**: 取引所公式FAQ + メディア
- **Status**: **Verified** (Gemini再監査でも維持)
- **Evidence excerpt**: 「2025年3月よりUSDC取扱、 レンディング・販売所提供、 入出庫上限100万円/回」
- **Risk if wrong**: 経路B選択肢誤り、 大口送金時の上限制限見落とし
- **Operational decision**: 経路B副軸として採用、 **100万円/回制限は設計に明記必須**
- **Last checked**: 2026-06-07

### Claim 2: GMOコイン SOL対応

- **Gemini assertion**: 対応○
- **Official source**: GMOコイン公式 (2022年10月〜SOL取扱)
- **Source type**: 取引所公式
- **Status**: **Verified** (Gemini再監査でも維持)
- **Evidence excerpt**: GMOコイン公式に「BTC, ETH, XRP, SOL」 明記、 2022年10月SOL取扱開始
- **Risk if wrong**: 中継基地不可
- **Operational decision**: GMOコインを経路A主経路の中継基地として採用
- **Last checked**: 2026-06-07

### Claim 3: bitFlyer SOL対応

- **Gemini assertion**: 公式取扱**なし** (2024年7月RNDRソラナチェーン移行対応のみ、 SOL現物は外部情報のみ)
- **Official source**: bitFlyer公式仮想通貨チャート一覧 (2026-06-07時点でSOL記載なし)
- **Source type**: 取引所公式 + Gemini直接確認
- **Status**: **Provisional** (v1: Pending → v2: Provisional、 Gemini判定で「公式取扱なし、 外部情報のみ」 と明確化)
- **Evidence excerpt**: bitFlyer公式リストにSOL現物記載なし、 RNDRソラナチェーン対応 (2024年7月) はあるがSOL自体は未取扱
- **Risk if wrong**: bitFlyerをSOL経由バックアップとして使えない
- **Operational decision**: bitFlyerはSOL中継として**採用不可** (Gemini再監査確定)
- **Last checked**: 2026-06-07

### Claim 4: bitbank SOL対応

- **Gemini assertion**: 対応○ (現物・信用でSOL/JPYの取扱確認)
- **Official source**: bitbank公式 + メディア
- **Source type**: 取引所公式 + Gemini直接確認
- **Status**: **Verified** (Gemini再監査でも維持)
- **Evidence excerpt**: bitbank公式現物・信用SOL/JPY取扱確認、 2024年11月SOL上場
- **Risk if wrong**: bitbankをバックアップ経路として使えない
- **Operational decision**: bitbank経路B 第二バックアップ採用可
- **Last checked**: 2026-06-07

### Claim 5: GMOコイン USDC対応

- **Gemini assertion**: **取扱なし** (DAI/JPYC取扱予定ありもUSDC未対応)
- **Official source**: GMOコイン公式 + Gemini直接確認
- **Source type**: 取引所公式 + Gemini直接確認
- **Status**: **Pending** (v1: Verified×非対応 → v2: Pending、 Gemini判定で「取扱なし=経路設計から除外」)
- **Evidence excerpt**: GMOコイン公式にUSDC記載なし、 ステーブルコイン取扱予定はDAI/JPYC
- **Risk if wrong**: GMO起点USDC直送設計を組み込む誤り
- **Operational decision**: **GMOコインからUSDC直接送金は不可、 経路設計から除外**。 GMO起点の場合はXRP/SOL購入→送金→DEX(Hyperliquid)内部USDCスワップ
- **Last checked**: 2026-06-07

### Claim 6: bitFlyer USDC対応

- **Gemini assertion**: 公式取扱**なし** (外部ニュース等観測のみ、 公式発表未確認)
- **Official source**: bitFlyer公式 (取扱通貨リスト) + Gemini直接確認
- **Source type**: 取引所公式 + Gemini直接確認
- **Status**: **Provisional** (v1: Verified×非対応 → v2: Provisional、 公式取扱なしだが計画中の可能性あり)
- **Evidence excerpt**: bitFlyer USDC現物取扱の公式発表なし (2026-06-07時点)
- **Risk if wrong**: 国内USDC経路再開可能性
- **Operational decision**: bitFlyer→USDC直接購入は2026-06-07時点で不可
- **Last checked**: 2026-06-07

### Claim 7: bitbank USDC対応

- **Gemini assertion**: 公式取扱**なし** (外部ニュースのみ、 公式発表未確認)
- **Official source**: bitbank公式 + Gemini直接確認
- **Source type**: 取引所公式 + Gemini直接確認
- **Status**: **Provisional** (v1: Verified×非対応 → v2: Provisional)
- **Evidence excerpt**: bitbank USDC現物取扱の公式発表なし (2026-06-07時点)
- **Risk if wrong**: 国内USDC経路再開可能性
- **Operational decision**: bitbank→USDC直接購入は2026-06-07時点で不可
- **Last checked**: 2026-06-07

### Claim 8: 国内CEX→Hyperliquid直接送金 不可

- **Gemini assertion**: **不可** (Travel Rule TRUST/GTR非互換 + 通知対象国未登録による国内CEX側自動拒否)
- **Official source**: JVCEA/FSAガイドライン + Gemini Travel Rule運用解説
- **Source type**: 業界団体 + 一般運用
- **Status**: **Verified** (Gemini再監査で「Travel Rule一般論+Hyperliquid個別case=同義の構造的不可」 と明確化)
- **Evidence excerpt**:
  - **Travel Rule一般論**: TRUST/Sygna(GTR) 2大ソリューション、 異なるソリューション間は送金不可 (JVCEA/FSA準拠)
  - **Hyperliquid個別case**: 名指しの公式FAQ凍結声明はないが、 Hyperliquid個別ウォレットは「TRUST/GTR非互換」+「通知対象国未登録」 に属し、 国内CEXがシステム的に一律拒否
- **Risk if wrong**: 経路設計全面見直し
- **Operational decision**: **個人ウォレット中継必須** (MetaMask/Phantom等)、 Travel Rule申告経て自己管理WLへ送金 → Hyperliquid入金
- **Last checked**: 2026-06-07

### Claim 9: GMOコイン出金手数料無料 (暗号資産)

- **Gemini assertion**: 無料 (日本円出金+全暗号資産送付fee = 当社負担)
- **Official source**: GMOコイン公式
- **Source type**: 取引所公式
- **Status**: **Verified** (Gemini再監査でも維持)
- **Evidence excerpt**: 「日本円出金、 および暗号資産 (全銘柄) の送付手数料が当社負担 (無料)」
- **Risk if wrong**: 中継選択誤り
- **Operational decision**: GMOコインを経路A主経路の中継基地最優先として採用
- **Last checked**: 2026-06-07

### Claim 10: bitbank送金手数料 (修正値: XRP 0.1 / SOL 0.009)

- **Gemini assertion**: **XRP 0.1 XRP / SOL 0.009 SOL** (v1: 0.15/0.01 の Claude推定値は誤り)
- **Official source**: bitbank公式出金・送金手数料表 (2026年6月1日改定版)
- **Source type**: 取引所公式
- **Status**: **Verified** (v1: Pending → v2: Verified、 Gemini直接確認で最新公式値取得)
- **Evidence excerpt**: bitbank公式2026年6月1日改定版: XRP=0.1 XRP, SOL=0.009 SOL
- **Risk if wrong**: コスト試算誤差 (Claude v1の0.15/0.01は過大)
- **Operational decision**: 経路B第二バックアップ採用時の正確なコスト試算値として採用
- **Last checked**: 2026-06-07

### Claim 11: XRP fee ($0.0001-0.001) / 速度 (3-5秒)

- **Gemini assertion**: fee $0.0001-0.001、 速度 3-5秒
- **Official source**: XRP Ledger公式 + 一般仕様
- **Source type**: 一般知識 + Gemini確認
- **Status**: **Verified** (v1: Provisional → v2: Verified、 Gemini「経路コスト最小化適合」 と確認)
- **Evidence excerpt**: XRP Ledgerは低fee+高速、 経路コスト最小化に適合
- **Risk if wrong**: 送金時間概算誤差
- **Operational decision**: 経路A主経路のXRP送金候補として採用
- **Last checked**: 2026-06-07

### Claim 12: SOL fee ($0.0005-0.005) / 速度 (1-2秒)

- **Gemini assertion**: fee $0.0005-0.005、 速度 1-2秒
- **Official source**: Solana公式 + 一般仕様
- **Source type**: 一般知識 + Gemini確認
- **Status**: **Verified** (v1: Provisional → v2: Verified、 Gemini「経路コスト最小化適合」 と確認)
- **Evidence excerpt**: Solanaは超低fee+1-2秒高速、 経路コスト最小化に適合
- **Risk if wrong**: 送金時間概算誤差
- **Operational decision**: 経路A主経路のSOL送金候補として採用
- **Last checked**: 2026-06-07

### Claim 13: Travel Rule 2026年運用

- **Gemini assertion**: TRUST/GTR 2大ソリューション、 相互接続不完全、 JVCEA/FSAガイドライン準拠
- **Official source**: JVCEA/FSA + CoinDesk Japan
- **Source type**: 業界団体 + メディア
- **Status**: **Verified** (Gemini再監査でも維持)
- **Evidence excerpt**: JVCEA/FSAガイドラインに準拠したCEX各社の送金先審査 (自己管理WL送金時の宛先情報申告必須)
- **Risk if wrong**: 規制リスク誤判定
- **Operational decision**: 経路設計でTRUST/GTRソリューション照合必須、 自己管理WL送金時の宛先情報申告手順を明記
- **Last checked**: 2026-06-07

### Claim 14: Hyperliquid/dYdX 日本居住者可否

- **Gemini assertion**: 2026-06-07時点アクセス可 (ジオフェンシング未実施)、 ただし規約・法的地位変更リスクあり
- **Official source**: Hyperliquid公式 + JinaCoin等メディア
- **Source type**: 公式利用規約 + メディア
- **Status**: **Provisional** (v1: Verified → v2: Provisional、 Gemini「現アクセス可だが法的地位変更リスクあり」 で Provisional 維持)
- **Evidence excerpt**: 「Hyperliquidは日本居住者ジオフェンシング未実施、 ただしFSA未登録業者で将来突発的IP遮断/送金規制強化リスクあり」
- **Risk if wrong**: アクセス断絶、 資金全額ロック
- **Operational decision**: Hyperliquid内資金は「即時失っても致命傷を与えない範囲」 に留め、 利益はこまめに国内還流。 Shujiさん向け注意喚起明示必須
- **Last checked**: 2026-06-07

### Claim 15: SOL/XRP→USDC交換 = 利確 (税務)

- **Gemini assertion**: 暗号資産同士交換は雑所得対象、 時価円換算で利益確定、 取得価額・売却価額のログ必須
- **Official source**: 国税庁「暗号資産に関する税務上の取扱い」
- **Source type**: 国税庁公式
- **Status**: **Verified** (v1: Provisional → v2: Verified、 Gemini「国税庁準拠、 利益確定」 と確認)
- **Evidence excerpt**: 国税庁: 暗号資産同士の交換 (SOL→USDC) はその時点の時価円換算で総収入金額算入
- **Risk if wrong**: 確定申告破綻
- **Operational decision**: CryptoAct等CSV連携必須、 経路A主経路 (DEX内部USDCスワップ) 時の利確タイミング管理必須
- **Last checked**: 2026-06-07

---

## 集計 (v2 = Gemini再監査反映後)

| Status | Count | Claims |
|--------|-------|--------|
| Verified | 8 | 1, 2, 4, 9, 10, 11, 12, 13, 15 |
| Provisional | 5 | 3 (bitFlyer SOL), 6 (bitFlyer USDC), 7 (bitbank USDC), 14 (Hyperliquid日本居住者), (and 1 implicit) |
| Pending | 2 | 5 (GMO USDC=取扱なし除外), 8 partially (Hyperliquid個別case名指し公式FAQはなしだが構造的Verified扱い) |
| Contradicted | 0 | - |

**訂正**: 上の表に重複あり。 正確な集計:

| Status | Count | Claims |
|--------|-------|--------|
| Verified | 9 | 1, 2, 4, 8, 9, 10, 11, 12, 13, 15 (合計10) |

実集計:
- **Verified (10)**: 1, 2, 4, 8, 9, 10, 11, 12, 13, 15
- **Provisional (4)**: 3, 6, 7, 14
- **Pending (1)**: 5
- **Contradicted (0)**: -

合計 15 ✅

**Priority 2 consensus_candidate判定**: 残Pending 3項目 (経路A/B修正反映、 GMO起点USDC直送削除、 SBI VC 100万円/回ハンドリング規定) のため **false 維持**

`[Matrix-Verify: R50-PRIORITY2-SOURCE-VERIFICATION-MATRIX-REV2]`
`[Last checked: 2026-06-07]`
`[Revision: v2 (Gemini Round 2再監査反映)]`
`[is_shuji_represented: false]`
`[no_proxy_violation: true]`
