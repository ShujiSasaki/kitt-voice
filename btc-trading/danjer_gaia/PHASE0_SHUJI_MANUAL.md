# Phase 0 — Shujiさん準備マニュアル

作成: 2026-06-04 (Round 30-33 3者会議 戦略Z v4 確定後)
対象: Shujiさん (非エンジニア向け、 配達稼働中の夜間+休日のみで完結する設計)

## 0. なぜ Phase 0 が必要か

Bybit が日本撤退したため、 3者会議 Round 30-33 で **Hyperliquid (DEX)** を主取引所に確定。 DEX は「自分のWallet」 (秘密鍵を自分で管理する仮想通貨のお財布) を使うので、 Phase 2 着手前に物理的な準備が必要。

**準備しないと何が起きるか**: Wallet がないので入金できない → 自動売買開始できない。
**準備すると何が良いか**: 取引所が倒産しても資産が消えない、 規制で取引所が日本撤退しても影響ゼロ、 手数料が普通のCEXより安い (maker rebate)。

## 1. Phase 0 全体スケジュール

```
Day -21 〜 Day -15 (Week 1): ハードウェア注文+到着
Day -14 〜 Day -8  (Week 2): Wallet初期化+送金経路確立
Day -7  〜 Day -1  (Week 3): 接続検証+紙トレ準備
Day 22 から Phase 2 着手 (実弾自動売買開始)
```

**Shuji作業時間 合計: 約4-5時間** (3週間に分散、 夜間+休日で完結可能)

## 2. 一括購入リスト (Day -21 朝までに発注)

| 項目 | 価格 | 購入先 | 注文時間 |
|---|---|---|---|
| Ledger Nano X | **約23,000円** (¥150 USD) | https://shop.ledger.com 公式ストア (Amazon は偽物リスクあり、 公式厳守) | 5分 |
| Cryptosteel Capsule Solo | **約12,000円** (¥80 USD) | https://cryptosteel.com 公式ストア | 5分 |
| **合計** | **約35,000円** | | 10分 |

⚠️ **絶対にAmazon/楽天/メルカリで Ledger を買わない**。 海外で偽物に既知の秘密鍵が仕込まれて、 入金した瞬間全額盗まれる事例多発。 公式ストアのみ。

⚠️ Cryptosteel は Shuji の秘密フレーズを金属プレートに刻印して保管するもの。 紙メモは火災・水濡れ・紛失で消える可能性あり、 金属保管が業界標準。

## 3. Week 1 (Day -21 〜 -15): ハードウェア調達

### Day -21: 発注

朝の配達前 or 夜に **配達中の待ち時間** で発注 (10分):
1. Ledger 公式ストア (https://shop.ledger.com) で **Ledger Nano X** を購入 (送付先 = Shuji自宅)
2. Cryptosteel 公式ストア (https://cryptosteel.com) で **Capsule Solo** を購入
3. Wise アカウント開設 (https://wise.com) — 無料、 JPY→USDC送金で使う

### Day -20 〜 -15: 到着待ち

- Ledger Nano X: 米国発送なので **3-7日** で到着
- Cryptosteel: 同じく **5-10日** で到着
- 到着まで Shuji 作業ゼロ。 配達稼働継続。

### Day -15 (Ledger 到着):

5分で確認:
- 商品箱の **改ざん防止シール** が無傷か (シール剥がし跡があれば即返品)
- 同梱物: Ledger Nano X 本体、 USB ケーブル、 シードフレーズ記入用カード、 ストラップ

⚠️ シードフレーズ記入用カード (24単語) はまだ書かない。 初期化時に画面に表示される単語を書く。

## 4. Week 2 (Day -14 〜 -8): Wallet初期化+送金経路

### Day -14 (夜2時間、 重要日)

**Ledger 初期化**:
1. Ledger を PC に接続 (USB)
2. ブラウザで https://www.ledger.com/start を開く
3. 「Set up your Ledger Nano X」 を選択
4. 画面の指示通り PIN コード (4-8桁) を設定 → **絶対にスマホメモに残さない**
5. 24単語のシードフレーズが画面に表示される → **紙に正しく書く** (1〜24まで)
6. 確認テスト (ランダムに数単語を再入力)
7. Ledger Live (公式アプリ) をインストール
8. Ethereum app を Ledger にインストール (Hyperliquid は Arbitrum (Ethereum L2) 経由なので)

**所要時間**: 90分 (初期化 30分 + シードフレーズ確認 30分 + アプリインストール 30分)

### Day -13 〜 -10 (夜30分ずつ): Cryptosteel 刻印

1. Cryptosteel Capsule にシードフレーズの **24単語を1文字ずつ刻印** (4日間に分散、 1日6単語)
2. 各単語の最初の4文字だけ刻印すれば BIP-39 規格で復元可能 (Cryptosteel 公式ガイド準拠)
3. 完成後、 紙のシードフレーズメモは **シュレッダー** で破棄 (or 別の物理金庫に保管)

⚠️ シードフレーズの写真をスマホで撮らない。 クラウド同期で漏洩する。

### Day -9 〜 -8: Wise + USDC送金経路 確立 (夜90分)

Wise でJPYをUSDCに変える経路を1度試す:
1. Wise アカウントに JPY 入金 (国内銀行から振込、 手数料数百円)
2. Wise から **$50 USDC** を発注 (手数料 0.5% = $0.25)
3. Wise が USDC を Arbitrum チェーン上の Shuji Wallet (Ledger MetaMask 連携) に送付
4. 受領確認 (10-30分後)

**ここで動作確認できれば、 Phase 2 で実弾入金できる**。 失敗したら Claude に Slack DM で連絡。

## 5. Week 3 (Day -7 〜 -1): 接続検証+紙トレ準備

### Day -7 〜 -5 (Claude側で並行作業、 Shuji作業最小)

Claude が並行で実装:
- `exchange/hyperliquid_client.py` 雛形作成 (公式 Python SDK 経由)
- Hyperliquid testnet 接続検証 (`https://api.hyperliquid-testnet.xyz`)
- 紙トレ simulator に Hyperliquid 手数料モデル組み込み (maker -0.001% / taker 0.035%)

Shuji 作業: **なし** (Claude 完了後に動作確認のみ)

### Day -4 〜 -1: 紙トレ最終リハーサル

Shuji 作業 (夜30分 × 3日):
1. Hyperliquid mainnet 用 Wallet に **$50 USDC を Wise経由で入金** (Day -8 と同じ手順、 本番経路確認)
2. Hyperliquid に testnet残高 を取得 (mainnet入金履歴があれば faucet 1000 USDC配布される)
3. KITT の朝サマリー機能で「今日のテスト発注: BTC LONG $5 仮想」を読み上げてもらう (動作確認)

### Day -1: Phase 2 着手前 最終確認会議 (Shuji+Claude、 30分)

確認項目:
- [ ] Ledger Cold Wallet $50 入金済
- [ ] MetaMask Hot Wallet 動作確認済
- [ ] Hyperliquid Wallet 接続確認済
- [ ] Cryptosteel シードフレーズ刻印完了
- [ ] 紙のシードフレーズメモ破棄完了
- [ ] Claude 側実装 (`hyperliquid_client.py`, `paper_trading/simulator.py` 更新) 完了

全 ✅ なら **Day 22 Phase 2 着手 GO**。

## 6. トラブルシューティング

### Q1. Ledger 到着が遅れた (1週間遅延)
A. Phase 0 を Day -28 〜 -1 (4週間枠) に延長。 Phase 2 着手は Day 29 にずらす。

### Q2. シードフレーズの単語が分からない (英語スペル不明)
A. BIP-39 公式単語リスト (https://github.com/bitcoin/bips/blob/master/bip-0039/english.txt) を参照。 全2,048単語。 Claude に質問しても OK。

### Q3. Wise の USDC 送金が届かない (24時間以上経過)
A. Wise サポートに連絡 + Arbitrum scan (https://arbiscan.io/) で送金トランザクション確認。 Claude 側で同時に調査開始。

### Q4. Ledger を紛失したら
A. **シードフレーズ (Cryptosteel刻印) が無事なら復元可能**。 新しい Ledger を購入 → シードフレーズ24単語を入力 → 残高復元。 これが「物理Wallet」 の本質。

### Q5. シードフレーズも紛失したら (Ledger も Cryptosteel も両方失う)
A. **資産永久喪失**。 だから Cryptosteel が必要。 紙メモだけだと火災で消える。

⚠️ Cryptosteel は **必ず Ledger 本体と別の場所に保管** (例: Ledger は自宅、 Cryptosteel は実家)。 同じ場所だと火災で両方失う。

## 7. Phase 0 完了後の状態

```
Shuji の物理保管物:
├─ Ledger Nano X (自宅、 USB接続でWallet操作)
└─ Cryptosteel Capsule (別の場所、 緊急復元用)

GCP Cloud Run の自動保管:
├─ MetaMask Hot Wallet (秘密鍵を GCP Secret Manager 暗号化保管)
└─ Cloud Run service account (Hyperliquid自動売買用)

Hyperliquid 残高:
├─ Stage 0: $15-50 (Phase 2 Day 22-32)
├─ Stage 1: $50 (Phase 2 Day 33-45)
└─ Stage 2: $150-2,250 (Phase 3 Day 46-167)
```

Shujiさんの日常操作: **月1回 Ledger → MetaMask Hot Wallet に補充** (5分)。 残りは全自動。

## 8. Phase 0 で困ったら

Slack DM (Shuji ↔ Claude) で 24時間質問可能。 Claude は Phase 0 期間中 Shujiさんの作業を全面サポート。

具体的に困った時の連絡例:
- 「Ledger の画面が固まった」
- 「Cryptosteel の刻印を間違えた」
- 「Wise からUSDC送金エラー」

→ Claude が Slack で対応、 必要なら GitHub Pages の KITT 経由で音声サポートも可能。

---

## 付録A: 用語集 (非エンジニア向け)

| 用語 | 意味 |
|---|---|
| Wallet (ウォレット) | 仮想通貨のお財布。 銀行口座のようなもの |
| 秘密鍵 (private key) | お財布の暗証番号。 持ってる人だけが残高を動かせる |
| シードフレーズ | 秘密鍵を生成する種となる24単語。 これがあれば Wallet 復元可能 |
| Ledger | USB型のハードウェアWallet。 秘密鍵を物理デバイスに保管 |
| Cold Wallet | オフライン (インターネット未接続) で保管する Wallet。 ハッキング不可 |
| Hot Wallet | オンライン (常時接続) で運用する Wallet。 自動売買用 |
| DEX (Decentralized Exchange) | 分散型取引所。 取引所が倒産しても資産は自分のWalletにあるので消えない |
| Hyperliquid | 我々が選んだ DEX。 BTC perpetual (永続契約) を扱う |
| Arbitrum | Ethereum の Layer 2。 手数料が安い。 USDC はここを使って送金 |
| USDC | 米ドルと連動する仮想通貨 (ステーブルコイン)。 1 USDC = $1 |
| Wise | 国際送金サービス。 JPY → USDC を 0.5% 手数料で直接変換 |
| maker rebate | 取引所が「板厚を提供する注文」 (limit order) にリベートを支払う仕組み。 手数料が マイナス = 取引するほど利益 |

## 付録B: Phase 2 着手以降の Shuji 操作 (日常)

Phase 2 〜 Phase 4 までの Shuji 作業:
- **月1回**: Ledger Cold → MetaMask Hot 補充 (5分)
- **週1回**: 朝サマリー確認 (デイリー方針承認、 KITT で音声、 1分)
- **緊急時**: L3-L4 通知時の即時対応 (Slack DM、 数分)

→ 配達稼働の邪魔を一切しない。 KITT がほぼ全部やる。
