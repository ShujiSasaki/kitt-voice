# Round 33 — 3者合意+Shujiさん確認用 最終サマリ

## Round 33 — GPT(司会)+Gemini+Claude 共同声明

### α. 3者全員合意

戦略Z 改訂版 v4 (Hyperliquid 主 + bitget 副 + GMOコイン Tax用 + bitFlyer Lightning Vacation用) **3者全員合意済**。

ぐるぐる3者会議 Round 30-32 で:
- 候補12取引所を網羅調査
- 9つを脱落判定 (OKX/DMM/Kraken/Binance Japan/Exness/Vantage/zoomex/bitbank/BingX-Bitfinex)
- 3つを採用 (Hyperliquid主 / bitget副 / GMOコイン待機)
- bitFlyer Lightning は Vacation Mode 退避先として待機追加 (Round 32)

### β. 脆弱性潰し済 (R70-R83、 計14リスク)

| # | リスク | 対策 |
|---|---|---|
| R70 | Wallet秘密鍵管理ヒューマンエラー | Ledger Nano X + Cryptosteel 金属保管 |
| R71 | Bitget FSA完全撤退リスク | 月次規制監視ジョブ + 90日避難計画 |
| R72 | Hyperliquid 流動性集中リスク | 板厚監視閾値 ($30M下回り → bitget自動切替) |
| R73 | Wallet秘密鍵 ヒューマンエラー | (R70と同じ、 統合) |
| R74 | Bitget日本完全撤退シナリオ | (R71と統合) |
| R75 | Hot Wallet サービス障害 | Cobo MPC は Phase 4以降のみ、 Phase 2-3 は Ledger単体 |
| R76 | Hyperliquid 規制リスク (将来) | Phase 4+ bitget併用 (規制リスク分散) |
| R77 | Wallet階層 同期エラー | Cold/Hot/SA 補充ロジック自動化 + Slack警告 |
| R78 | Bridge ハック | Wise/Revolut直接USDC送金 (Bridge回避) |
| R79 | Hyperliquid 出金24-48h遅延 | Wallet残高上限 (Cap 2まで) + Cold保管 |
| R80 | USDC depeg | USDT併用検討 (Phase 5+) |
| R81 | Phase 0 21日準備期延長 | 各ステップ3日バッファ、 28日まで許容 |
| R82 | Hyperliquid 規約変更 | 月次規約監視ジョブ |
| R83 | Service Account 秘密鍵 漏洩 | IAM制御 + IP制限 + 出金禁止権限分離 |

### γ. Phase 2-5+ 全Phase 取引所別構成 (確定版)

```
              [Hyperliquid] [bitget]   [GMOコイン]  [bitFlyer]
Phase 0        準備のみ      (--)       (--)        (--)
Phase 2        主 $15-500    (--)       (--)        (--)
Phase 3        主 $500-5k    副 並走    (--)        (--)
Phase 4 Cap 1  主 $5k-25k   副 板厚    (--)        (--)
Phase 4 Cap 2  主 $25k      副 $25k    Tax連携     (--)
Phase 5 Cap 3  主 $50k      副 $50k    Tax連携     Vacation退避
Phase 5 Cap 4  主 $100k     副 $150k   Tax連携     Vacation退避
Phase 5 Cap 5  主 $200k     副 $300k   Tax連携     Vacation退避
```

### δ. 月コスト見直し (Bybit前提 → Hyperliquid前提)

| Phase | 月コスト (旧Bybit前提) | 月コスト (新Hyperliquid前提) | 差分 |
|---|---|---|---|
| Phase 2 | $52-136 | $30-80 | **-$30** (取引手数料減、 Cobo MPC不要) |
| Phase 3 | $71-170 | $50-120 | **-$30** (maker rebate効果) |
| Phase 4 | $180-350 | $150-300 | **-$50** (DEX手数料優位) |
| Phase 5+ | $155-400 | $140-380 | **-$20** (Cobo MPC Cap 1以降必要) |

**節約効果**: 全Phase で 月額 $20-50 の節約。 年間 $240-600 (約3-9万円) の節約。

### ε. ハードウェア・サービス 必要購入物

Shujiさんに事前購入が必要なもの:

| 項目 | 価格 | 用途 | 購入タイミング |
|---|---|---|---|
| Ledger Nano X | $150 (約23,000円) | Cold Wallet (秘密鍵物理保管) | Phase 0 Day -21 |
| Cryptosteel Capsule | $80 (約12,000円) | シードフレーズ金属保管 | Phase 0 Day -21 |
| Wise アカウント | 無料 (送金時0.5%手数料) | JPY→USDC直接送金 | Phase 0 Day -21 |
| Cobo MPC Lite | $99/月 | Hot Wallet MPC管理 | **Phase 4 Cap 1到達後** |

**Phase 2 着手前 一括コスト: 約35,000円**

### ζ. Shujiさん 大枠確認

3者会議 Round 30-33 で **戦略Z 改訂版 v4** に全員合意。 Shujiさんに以下3点を確認したい:

#### 確認1: 主軸取引所
> 「BTC自動売買の主軸取引所を **Hyperliquid (DEX)** にする」 で良いか?
>
> 副: bitget (Phase 4以降 板厚補完)
> Tax用: GMOコイン
> Vacation用: bitFlyer Lightning

#### 確認2: Wallet物理管理
> Wallet秘密鍵管理として **Ledger Nano X (物理デバイス、 約23,000円購入)** を使う。 シードフレーズは金属プレート ($80 = 12,000円) で保管。 Shujiさんの月次操作は **Cold→Hot 補充の1回 (5分作業)** のみ。
>
> これでよいか? それとも 全部 Claude側で自動化 (Service Account 1段だけ、 物理デバイスなし) のほうが良いか?

#### 確認3: Phase 2 着手タイミング
> Phase 2 着手が **Day 22 (元設計 Day 15 から 1週間遅延)** に変更。 Phase 0 (21日) 準備期で Ledger / Wise / Hyperliquid Wallet 準備。
>
> 配達稼働中で 平日昼間の時間が取れない場合、 さらに延長 (Day 30 着手) でも問題ない。 Shujiさんの希望は?

### η. ぐるぐる3者会議 終了宣言

GPT (司会) + Gemini + Claude の3者で:
- Round 30: 取引所候補絞り込み
- Round 31: 未開設取引所も含む網羅評価 (Shuji追加指示反映)
- Round 32: 戦略Z 改訂版 v3→v4 (Wallet階層 + 送金経路 + 出金遅延 対応)
- Round 33: 3者合意+Shuji確認用サマリ

**4ラウンドで合意到達**。 ぐるぐる無制限 と Shujiさん指示にあったが、 これ以上の脆弱性は3者で発見できなかったので 一旦終了。 Shujiさん回答後、 必要があれば Round 34+ 再開。

実装担当 Claude が:
1. Phase 2-5+ 設計書5本を v4 反映 (半日工数)
2. exchange/hyperliquid_client.py 新規実装 (5-7日工数、 Phase 2.2 として再着手)
3. Phase 0 Shuji 準備マニュアル作成 (3時間工数)

を実行する。 Shujiさん回答待ち。


---
