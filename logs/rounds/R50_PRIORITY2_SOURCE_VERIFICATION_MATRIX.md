# R50 Priority 2 Source Verification Matrix

**Last checked date**: 2026-06-07
**Verify Token**: `[Matrix-Verify: R50-PRIORITY2-SOURCE-VERIFICATION-MATRIX]`
**Round**: 2 (Claude Source Verification)

---

## Summary

- Total claims: 15
- **Verified**: 9
- **Provisional (一般知識/原則と整合、 公式直接出典は限定的)**: 3
- **Pending (公式fetch失敗/個別case未確認)**: 3
- **Contradicted**: 0

---

## Matrix詳細

### Claim 1: SBI VCトレード → USDC直接購入可否

- **Gemini assertion**: 条件付き可能、 ただしDEX直送制限多
- **Official source**: https://coin.z.com/jp/glossary/1195.html (GMO関連解説); CoinDesk Japan https://www.coindeskjapan.com/284124/
- **Source type**: 取引所公式関連解説 + メディア (CoinDesk Japan)
- **Status**: **Verified** (2026年2月時点で国内でUSDCを直接購入できるのはSBI VCトレードのみ)
- **Evidence excerpt**: 「2026年2月時点では、 国内でUSDCを直接購入できるのはSBI VCトレードのみ」 「SBI VCトレードは2026年3月にはUSDCを対象としたレンディングサービスを開始」
- **Risk if wrong**: 経路B選択肢誤り
- **Operational decision**: 経路B候補としてSBI VC利用検討可、 ただしDEX直送制限の個別case確認は別途
- **Last checked**: 2026-06-07

### Claim 2: GMOコイン SOL対応

- **Gemini assertion**: 対応○
- **Official source**: https://coin.z.com/jp/corp/guide/fees/
- **Source type**: 取引所公式 fee/取扱通貨ページ
- **Status**: **Verified**
- **Evidence excerpt**: GMOコイン公式ページに「BTC, ETH, XRP, SOL」 明記、 USDCは記載なし
- **Risk if wrong**: 中継基地不可
- **Operational decision**: GMOコインを経路Bの中継基地として採用可
- **Last checked**: 2026-06-07

### Claim 3: bitFlyer SOL対応

- **Gemini assertion**: 対応○
- **Official source**: https://bitflyer.com/ja-jp/virtual-currency-list (403 Forbidden、 アクセス失敗)
- **Source type**: 取引所公式 (fetch失敗)
- **Status**: **Pending** (公式ページfetchが403で失敗、 メディア情報「39種類取扱」 のみ)
- **Evidence excerpt**: 一般情報「bitFlyerは39種類の仮想通貨を取扱」、 SOL個別確認できず
- **Risk if wrong**: bitFlyerをバックアップ経路として使えない
- **Operational decision**: bitFlyer中継採用前に手動公式確認必須
- **Last checked**: 2026-06-07

### Claim 4: bitbank SOL対応

- **Gemini assertion**: 対応○
- **Official source**: https://bitbank.cc/info/asset/ (内容不十分); 検索結果Yahooニュース等
- **Source type**: メディア + 検索結果
- **Status**: **Verified** (2024年11月SOL上場確認)
- **Evidence excerpt**: 「bitbankは2024年11月よりSOLが上場された」 「44銘柄取扱」
- **Risk if wrong**: bitbankをバックアップ経路として使えない
- **Operational decision**: bitbank経路B採用可
- **Last checked**: 2026-06-07

### Claim 5: GMOコイン USDC対応

- **Gemini assertion**: ×非対応
- **Official source**: https://coin.z.com/jp/corp/guide/fees/ + CoinDesk Japan
- **Source type**: 取引所公式 + メディア
- **Status**: **Verified** (×非対応)
- **Evidence excerpt**: GMO公式ページUSDC記載なし、 CoinDesk Japan「国内でUSDCを直接購入できるのはSBI VCトレードのみ」 (2026年2月時点)
- **Risk if wrong**: 国内USDC経路再開可能 (Gemini結論が変わる)
- **Operational decision**: GMOコインからUSDC直接送金は不可、 SOL/XRP中継必須
- **Last checked**: 2026-06-07

### Claim 6: bitFlyer USDC対応

- **Gemini assertion**: ×非対応
- **Official source**: CoinDesk Japan https://www.coindeskjapan.com/284124/
- **Source type**: メディア (CoinDesk Japan)
- **Status**: **Verified** (×非対応、 ただしCircleが「近い将来上場」 予告)
- **Evidence excerpt**: 「ビットフライヤー、 ビットバンク、 バイナンスも上場・流通を計画」 (CoinDesk Japan、 2026年時点まだ非対応)
- **Risk if wrong**: 国内USDC経路再開可能
- **Operational decision**: bitFlyer→USDC直接送金は2026年6月時点で不可
- **Last checked**: 2026-06-07

### Claim 7: bitbank USDC対応

- **Gemini assertion**: ×非対応
- **Official source**: CoinDesk Japan + Yahoo News
- **Source type**: メディア
- **Status**: **Verified** (×非対応、 計画中)
- **Evidence excerpt**: 「ビットバンクUSDC取扱を計画」 (CoinDesk Japan、 2026年6月時点未対応)
- **Risk if wrong**: 国内USDC経路再開可能
- **Operational decision**: bitbank→USDC直接送金は2026年6月時点で不可
- **Last checked**: 2026-06-07

### Claim 8: 国内CEX→Hyperliquid直接送金不可

- **Gemini assertion**: 不可能 (トラベルルール遮断)
- **Official source**: JVCEA Travel Rule通達 (一般情報); 個別Hyperliquid case未確認
- **Source type**: 業界団体 + メディア
- **Status**: **Pending** (Travel Rule一般運用はVerified、 ただしHyperliquid個別case凍結事例は具体的ソース未確認)
- **Evidence excerpt**: TRUST/Sygna 2大ソリューション、 異なるソリューション間は送金不可 (CoinDesk Japan)
- **Risk if wrong**: 経路設計全面見直し
- **Operational decision**: 個人ウォレット中継を**前提**として実装、 個別Hyperliquid case確認は次ラウンド
- **Last checked**: 2026-06-07

### Claim 9: GMOコイン出金手数料無料 (暗号資産)

- **Gemini assertion**: 無料
- **Official source**: https://coin.z.com/jp/corp/guide/fees/
- **Source type**: 取引所公式
- **Status**: **Verified**
- **Evidence excerpt**: 「無料 送付元で手数料が発生する際はお客さま負担」 (GMO公式)
- **Risk if wrong**: 中継選択誤り
- **Operational decision**: GMOコインを中継基地最優先として採用可
- **Last checked**: 2026-06-07

### Claim 10: bitbank送金手数料 (XRP 0.15 / SOL 0.01)

- **Gemini assertion**: XRP 0.15 XRP, SOL 0.01 SOL固定
- **Official source**: https://bitbank.cc/info/asset/ (内容不十分); https://bitbank.cc/docs/withdrawal-fee/ (404)
- **Source type**: 取引所公式 (fetch失敗)
- **Status**: **Pending** (公式fee表fetch失敗、 メディア情報のみ)
- **Evidence excerpt**: 一般情報レベル、 公式fee表直接確認できず
- **Risk if wrong**: コスト試算誤り
- **Operational decision**: bitbank採用前に手動公式fee確認必須
- **Last checked**: 2026-06-07

### Claim 11: XRP fee ($0.0001-0.001) / 速度 (3-5秒)

- **Gemini assertion**: fee $0.0001-0.001、 速度 3-5秒
- **Official source**: XRP Ledger 一般公開情報 (公式explorer未直接fetch)
- **Source type**: 一般知識 / Provisional
- **Status**: **Provisional Confirmed** (XRP Ledgerの一般仕様と整合)
- **Evidence excerpt**: XRP Ledgerは伝統的に低fee+高速で知られる
- **Risk if wrong**: 送金時間概算誤差
- **Operational decision**: provisional値を採用、 実測は別途
- **Last checked**: 2026-06-07

### Claim 12: SOL fee ($0.0005-0.005) / 速度 (1-2秒)

- **Gemini assertion**: fee $0.0005-0.005、 速度 1-2秒
- **Official source**: Solana 一般公開情報 (公式explorer未直接fetch)
- **Source type**: 一般知識 / Provisional
- **Status**: **Provisional Confirmed** (Solanaの一般仕様と整合)
- **Evidence excerpt**: Solanaは伝統的に超低fee+1-2秒高速で知られる、 ただし優先手数料高騰時は高くなる
- **Risk if wrong**: 送金時間概算誤差
- **Operational decision**: provisional値を採用、 実測は別途
- **Last checked**: 2026-06-07

### Claim 13: Travel Rule 2026年運用

- **Gemini assertion**: TRUST/Traveler相互接続不完全、 厳格化
- **Official source**: CoinDesk Japan, JVCEA関連 (https://www.coindeskjapan.com/learn/travel-rule/)
- **Source type**: 業界団体 + メディア
- **Status**: **Verified** (基本運用)
- **Evidence excerpt**: 「TRUSTとSygnaの2種類のソリューション、 異なるソリューション間は送金不可」
- **Risk if wrong**: 規制リスク誤判定
- **Operational decision**: 経路設計でTRUST/Sygnaソリューション照合必須
- **Last checked**: 2026-06-07

### Claim 14: Hyperliquid/dYdX 日本居住者可否

- **Gemini assertion**: 2026年現在IP制限なし、 ガバナンス変更リスクあり
- **Official source**: Hyperliquid公式利用規約 (https://app.hyperliquid.xyz/)、 JinaCoin等メディア
- **Source type**: メディア + 公式利用規約 (2025-01-26更新)
- **Status**: **Verified** (基本)
- **Evidence excerpt**: 「Hyperliquidは国内ユーザーでも問題なく利用、 入出金・取引まで制限なし」「アジア太平洋地域アクセス提供」 「ただし法的グレーゾーン存在」
- **Risk if wrong**: アクセス断絶
- **Operational decision**: Hyperliquid採用可、 ただし法的グレーゾーンShujiさん明示了承前提
- **Last checked**: 2026-06-07

### Claim 15: SOL/XRP→USDC交換 = 利確 (税務)

- **Gemini assertion**: 雑所得発生、 自動損益計算CSV必須
- **Official source**: 国税庁 (https://www.nta.go.jp/) 一般原則; CryptoAct等公式
- **Source type**: 一般税法原則 / Provisional
- **Status**: **Provisional Confirmed** (国税庁の暗号資産交換時利確原則と整合)
- **Evidence excerpt**: 国税庁: 暗号資産同士の交換も雑所得対象
- **Risk if wrong**: 確定申告破綻
- **Operational decision**: CryptoAct等CSV連携必須を運用方針に組み込む
- **Last checked**: 2026-06-07

---

## 集計

| Status | Count | Claims |
|--------|-------|--------|
| Verified | 9 | 1, 2, 4, 5, 6, 7, 9, 13, 14 |
| Provisional Confirmed | 3 | 11, 12, 15 |
| Pending | 3 | 3 (bitFlyer SOL公式fetch失敗), 8 (Hyperliquid個別case), 10 (bitbank fee表fetch失敗) |
| Contradicted | 0 | - |

**Priority 2 consensus_candidate判定**: 3件Pending残存のため **false 維持**

`[Matrix-Verify: R50-PRIORITY2-SOURCE-VERIFICATION-MATRIX]`
`[Last checked: 2026-06-07]`
`[is_shuji_represented: false]`
`[no_proxy_violation: true]`
