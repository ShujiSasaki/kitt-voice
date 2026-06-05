# Phase 0 — Shujiさん準備マニュアル (v8 Wallet段階導入版)

更新: 2026-06-04 (Round 38 戦略Z v8 反映、 ハード購入なし1週間完結)
対象: Shujiさん (非エンジニア向け、 配達稼働中の夜間で完結)

## 0. なぜ Phase 0 が必要か (v8 簡略版)

Bybit が日本撤退したため、 3者会議 Round 30-38 で **Hyperliquid (DEX)** を主取引所に確定。 v8 (Round 38) で **ハード購入は Phase 4 Cap 1 直前 (3-5ヶ月後)** に延期、 Phase 2 着手は **ソフトWallet (MetaMask + GCP Secret Manager)** で7日完結。

**準備しないと何が起きるか**: Wallet がないので入金できない → 自動売買開始できない。
**準備すると何が良いか**: 取引所が倒産しても資産が消えない、 規制で取引所が日本撤退しても影響ゼロ、 手数料が普通のCEXより安い (maker rebate)。

## 1. Phase 0 全体スケジュール (v8 = 1週間)

```
Day -7 〜 -5: Wallet作成 (Shuji 15分)
Day -4 〜 -2: 送金経路+接続検証 (Shuji 30分)
Day -1:       最終確認 (Shuji 30分)
Day 8 から:   Phase 2 着手 (実弾自動売買開始)
```

**Shuji 作業時間 合計: 約75分** (夜間1-2回で完結)
**Phase 0 一括コスト: 0円** (ハード購入なし)

## 2. Day -7 〜 -5: Wallet作成 (Shuji 15分)

### MetaMask Wallet 作成 (5分)
1. Chrome ブラウザに **MetaMask 拡張機能** インストール (https://metamask.io)
2. 「Create a new wallet」 を選択
3. パスワード設定 (8文字以上、 ブラウザでのみ使用)
4. シードフレーズ12-24単語 表示 → **画面に表示されたまま、 まだ書かない**
5. **Claude Code チャットで連絡** 「MetaMask作成、 シードフレーズ表示中」 と書き込む
6. Claude が **GCP Secret Manager** にシードフレーズと秘密鍵を暗号化保管する手順をリモート支援

⚠️ シードフレーズを **メモアプリ・写真・クラウドメモ** に絶対残さない。 GCP Secret Manager のみ。

### Wise アカウント開設 (10分)
1. https://wise.com にアクセス
2. 「アカウント開設」 → メール+パスワード入力
3. 本人確認 (運転免許証アップロード)
4. 国内銀行口座を連携 (JPY 入金用)
5. Multi-currency account 有効化 (USDC受領のため)

## 3. Day -4 〜 -2: 送金経路+接続検証 (Shuji 30分)

### Wise → USDC送金経路確立 (Shuji 30分)
1. Wise アカウントに JPY 入金 (国内銀行から振込、 手数料数百円)
2. Wise から **$50 USDC** を発注 (手数料 0.5% = $0.25)
3. Wise が USDC を Arbitrum チェーン上の MetaMask Wallet に送付
4. 10-30分後、 MetaMask に USDC受領確認
5. Hyperliquid 公式サイト (https://app.hyperliquid.xyz) で Wallet接続
6. Hyperliquid mainnet に $50 USDC 入金 (testnet faucet eligibility 確保)

### Claude 並行作業 (Shuji作業不要、 Day -4〜-2)
- Hyperliquid testnet 接続検証
- `exchange/hyperliquid_client.py` 雛形作成
- paper_trading/simulator.py に Hyperliquid 手数料モデル組み込み
- GCP Secret Manager IAM設定 (Cloud Run専用アクセス)

## 4. Day -1: 最終確認 (Shuji 30分)

確認項目 (Shuji側):
- [ ] MetaMask Wallet 接続 OK
- [ ] Hyperliquid mainnet $50 USDC 入金 完了
- [ ] Wise → USDC送金経路 動作確認済
- [ ] GCP Secret Manager 秘密鍵保管 完了 (Claude確認)
- [ ] 紙のシードフレーズメモ シュレッダー破棄完了

Claude 側:
- [ ] Hyperliquid testnet 動作確認
- [ ] paper_trading シミュレータ 174 → 200+テスト通過
- [ ] Cloud Run keep-alive スケジューラ 設定済
- [ ] デイリー承認通知ロジック 確認 (KITT音声 + Email 想定、 Slackは不使用)

全 ✅ なら **Day 8 Phase 2 Stage 0 着手 GO**。

## 5. Phase 2 着手以降の Shuji 操作 (日常、 Phase 4 Cap 1 まで)

Phase 2 〜 Phase 4 Cap 1 ($25k) までの Shuji 作業:
- **月1回**: Wise → USDC補充 (10分、 規模に応じて $50-$5,000)
- **週1回**: 朝サマリー確認 (デイリー方針承認、 KITT で音声、 1分)
- **緊急時**: L3-L4 通知時の即時対応 (KITT音声+Email、 数分)

## 6. Phase 4 Cap 1 直前 (Day 144-154、 ハード購入時期)

Cap 1 ($25k) 到達が見えてきた Day 144 頃に以下を実施:

### Ledger Nano X 購入 + 初期化 (Day 144-148)
1. **Ledger 公式ストア** (https://shop.ledger.com) で **Ledger Nano X** 注文 (約23,000円)
2. **Cryptosteel 公式ストア** で **Capsule Solo** 注文 (約12,000円)
3. Ledger 到着後、 初期化 (90分):
   - PIN コード設定
   - シードフレーズ24単語生成・紙に書く
   - Ledger Live インストール、 Ethereum app 追加

⚠️ **絶対にAmazon/楽天/メルカリで Ledger を買わない**。 偽物に既知の秘密鍵が仕込まれて即盗難。 公式ストアのみ。

### Cryptosteel 刻印 (Day 149-152)
- シードフレーズ24単語の最初の4文字を金属プレートに刻印 (4日に分散、 1日6単語)
- 完成後、 紙メモはシュレッダー破棄

### MetaMask → Ledger Cold 資金移管 (Day 153-154)
- MetaMask Hot Wallet 残高の一部 ($20k 程度) を Ledger Cold Wallet に移管
- MetaMask Hot Wallet は $5k 程度を維持 (日常運用用)

### Wallet階層 完成 (Day 155)
```
Ledger Cold ($20k+、 物理保管):
  ↓ 月1回 Hot補充
MetaMask Hot ($5k、 GCP Secret Manager):
  ↓ Cloud Run自動アクセス
Hyperliquid 運用残高
```

## 7. トラブルシューティング

### Q1. MetaMask シードフレーズを忘れた
A. GCP Secret Manager に保管済なら復元可能。 Claude に連絡。

### Q2. Wise から USDC が届かない (24時間以上経過)
A. Wise サポート + Arbitrum scan (https://arbiscan.io/) でトランザクション確認。 Claude 並行調査。

### Q3. Hyperliquid に接続できない
A. MetaMask の Network設定で Arbitrum One を選択しているか確認。 Claude が解決サポート。

### Q4. Phase 4 Cap 1 到達してないけど Ledger欲しい
A. 早めの購入もOK、 ただし Cap 1 (約3-5ヶ月後) まで使う場面なし。 配達収益の使い道として柔軟に判断。

## 8. Phase 0 で困ったら

**Claude Code チャット** で 24時間質問可能。 Claude は Phase 0 期間中 Shujiさんの作業を全面サポート。
(Shujiは Slack 不使用、 連絡経路は Claude Code 対話 + KITT音声 + Email)

---

## 付録A: 用語集 (非エンジニア向け、 v8簡略版)

| 用語 | 意味 |
|---|---|
| MetaMask | 一番有名なソフトウェア Wallet。 Chrome 拡張で動く、 無料 |
| GCP Secret Manager | Google Cloud の暗号化保管庫。 秘密鍵を安全に保存 |
| シードフレーズ | Wallet 復元用の12-24単語。 これがあれば Wallet 復活可能 |
| Hyperliquid | 我々が選んだ DEX。 BTC perpetual (永続契約) を扱う |
| Arbitrum | Ethereum の Layer 2。 手数料が安い。 USDC はここを使って送金 |
| USDC | 米ドルと連動する仮想通貨 (ステーブルコイン)。 1 USDC = $1 |
| Wise | 国際送金サービス。 JPY → USDC を 0.5% 手数料で直接変換 |
| Ledger | USB型のハードウェアWallet。 Phase 4 Cap 1 直前に購入 |

## 付録B: v7 → v8 で変わった部分 (Round 38)

| 項目 | v7 (旧) | v8 (新) |
|---|---|---|
| Phase 0 期間 | 3週間 | **1週間** |
| Phase 2 着手日 | Day 22 | **Day 8** |
| ハード購入 | Phase 0 (即時 ¥35,000) | **Phase 4 Cap 1 直前 (3-5ヶ月後)** |
| Phase 0 Shuji作業時間 | 4-5時間 | **45分** |
| 即時コスト | ¥35,000 | **¥0** |
