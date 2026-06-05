# 🚨 Round 30 — 取引所再選定 緊急会議 (Shuji指示、 2026-06-03 深夜)

## Round 30 — Shujiさんからの起点発言 (verbatim)

> 「bybitは日本市場から撤退したから今後使うことはないと思うし資金も引き上げ済」
> 「全ての条件を鑑みて最適な取引所をぐるぐる３者会議で議論してください」

## Round 30 — 司会GPT (議題提示+Claudeミス自白受領+整合性監査)

### 司会の任務開始: 緊急議題

Phase 2-5+ 設計の **全ての前提が崩壊**。

**事実1**: Bybit が日本居住者向けサービスを2026年1月段階的終了 (確定済)
**事実2**: Shujiさんは Bybit に資金なし、 今後使用予定なし
**事実3**: Round 0-28 で「Bybit主+Hyperliquid副+OKX待機」を全Phase 設計の柱に置いていた
**事実4**: 私 (GPT・司会) も Gemini も Claude も、 Shujiさんが既に伝えていた **memory の取引所一覧 (bitbank/GMOコイン/bitget/zoomex/exness/vantage trading)** を確認せず、 Bybit を勝手に主軸として28ラウンド議論していた

これは **feedback_information_brokerage 違反** (Shujiさんが既に伝えた情報を読まずに前提を構築した「結果嘘」状態)。 Claude が正直に自白したのは feedback_never_lie 準拠で評価できるが、 **司会の私 (GPT) も同罪**。 Phase 2-5+ の全前提を取引所選定からやり直す。

### Round 30 議題

> **「Shujiさんの全条件を鑑みて、 BTC自動売買 (Phase 2-5+) の主軸取引所を再選定する」**

### 検証する全条件 (memory + 既存設計 から抽出)

#### 条件群A: 機能要件
- A1. BTC永続契約 or BTC現物レバ取引 (アルゴ自動売買の対象)
- A2. **REST API + WebSocket** 完備 (CCXTで言うと implements_publicAPI=true, implements_privateAPI=true)
- A3. **Python SDK** 公式 or サードパーティ (Phase 2.2 で `bybit_client.py` を実装する箇所を取引所変更前提でリファクタする)
- A4. **板厚と流動性** (1注文サイズ上限「板厚 × 5%以下」R48継続。 Shujiさん $15-50→$500,000 の段階キャップで流動性影響しない)
- A5. **手数料** (Phase 4以降は3取引所×多アセット手数料が $30-100/月レンジ)
- A6. **レバレッジ最大値** (Phase 2 で 2x、 Phase 3 で 3x、 Phase 5+ で最大何倍まで使うかは段階キャップで制御)
- A7. **reduce_only stop 同時発注** 対応 (Order Gate Step 3 の必須要件)
- A8. **Mark Price 取引所別配線** (清算回避、 R47)

#### 条件群B: 法的・規制
- B1. 日本居住者の利用が **個人責任の範囲で合法** か (R6 法規制リスク)
- B2. 金融庁からの **完全撤退要請の有無** (Bybit、 OKX等の動向)
- B3. **税務対応** (取引履歴CSV エクスポート → MoneyForward / Tax-Engine 連携、 R67)
- B4. **KYC/AML 必須か** (個人運用なので問題ないが、 規模拡大時の凍結リスク R55)

#### 条件群C: 既登録・運用継続性
- C1. Shujiさん **既登録済みアカウントがあるか** (申請+KYC期間ゼロ、 Phase 2 着手即可能)
- C2. **資金移動の容易性** (国内取引所→海外取引所、 円ベース運用)
- C3. **過去の障害履歴・出金トラブル**

#### 条件群D: Shujiさん優先順位
- D1. **レスポンス速度 > 費用 > 構築の速さ** (CLAUDE.md 明記)
- D2. **完全自動売買** (Shujiさん は「手を出さない、 口だけ出す」の方針)
- D3. **配達収益 月10万円投入 (2026年7月〜)** → Phase 2 〜 Phase 3 で実弾 $1,500/月 ペース
- D4. **段階キャップ** ($25k→$500k、 都度承認、 Phase 5+ v2)

### 候補リスト (Shuji既登録 + 新規DEX)

| # | 取引所 | 種別 | Shuji登録 | レバ上限 | API | 日本可 |
|---|---|---|---|---|---|---|
| ① | bitget | 海外CEX | ✅ | 125x | ✅ CCXT | ⚠️ 警告あり、 個人利用可 |
| ② | zoomex | 海外CEX | ✅ | 100x | ✅ Bybit互換 | ✅ 日本語フル |
| ③ | Hyperliquid | DEX | (未) | 50x | ✅ 公式Python SDK | ✅ KYC不要 |
| ④ | GMOコイン | 国内CEX | ✅ | 2x | ✅ 公式API | ✅ 国内登録 |
| ⑤ | bitbank | 国内CEX | ✅ | 現物のみ | ✅ | ✅ 国内登録 |
| ⑥ | Exness | 海外FX | ✅ | 400x (CFD) | ❌ MT4/MT5のみ | ⚠️ FX/CFD |
| ⑦ | Vantage Trading | 海外FX | ✅ | (BTC CFD) | ❌ MT4/MT5のみ | ⚠️ FX/CFD |
| 参考 | GMX/dYdX | DEX | (未) | 50/20x | ✅ | ✅ |

### Round 30 司会判断 (GPTの整合性チェック)

**まず候補から脱落させる4つ** (整合性監査):
- ⑥ Exness: **REST APIなし** (MT4/MT5のみ) → 条件A2 違反、 アルゴ自動売買インフラから外れる
- ⑦ Vantage: 同上、 MT4/MT5のみ → A2 違反
- ⑤ bitbank: BTCFX/レバ取引なし、 **現物のみ** → 条件A1 違反 (Stage 2 以降のレバ運用に使えない)
- 参考GMX/dYdX: Shuji 未登録、 アカウント開設+KYC期間が発生、 **既登録3候補で十分** → 後回し

**残る4候補で議論を集中させる**:
- ① **bitget** (海外CEX 高レバ、 既登録、 規制警告あり)
- ② **zoomex** (海外CEX 高レバ、 既登録、 日本語フル対応)
- ③ **Hyperliquid** (DEX 高レバ、 未登録、 KYC不要)
- ④ **GMOコイン** (国内CEX、 既登録、 2x制限、 法的安全)

### Sycophancy検出ポイント (GPT 自己批判)

- 「Shuji の既登録が多い」 = 楽だが、 **適切な選定 ≠ 既登録の中から選ぶ** だけではない。 Phase 5+ 永続フェーズで使う取引所は今ない選択肢 (例: BinanceJapan の新サービス開始等) も考慮すべき
- 「日本語対応」 = 便利だが、 アルゴ自動売買では日本語UI不要、 API英語ドキュメントだけで十分
- 「高レバ可能」 = Stage 2 で3xしか使わない設計なので、 100x/400x は **過剰スペック**

→ 監査基準は **「Phase 2-5+ 全体に最小リスクで投資効率を最大化できるか」** に絞る。

バトンをGemini (技術深掘り) へ。

---

## Round 30 — Gemini監査 (技術深掘り+物理限界)

### 結論先出し: **Hyperliquid (主) + bitget (副) の 2系統構成を提案**

GPTの脱落基準は妥当 (Exness/Vantage/bitbankは技術的に Phase 2 設計と合わない)。 ただし、 GPT が残した4候補 (bitget/zoomex/Hyperliquid/GMOコイン) の評価は **技術観点で深掘り** が必要。

### α. CCXT/SDK の実装難易度マトリクス

| 取引所 | CCXT対応 | 公式Python SDK | reduce_only stop | WS可用性 | Phase 2.2 工数見積 |
|---|---|---|---|---|---|
| bitget | ✅ | ✅ | ✅ | ✅ | 3-5日 (CCXT経由) |
| zoomex | ⚠️ (Bybit互換だがCCXT非対応) | ❌ | ⚠️ | ✅ | 7-10日 (REST直叩き必要) |
| Hyperliquid | ⚠️ (CCXTサポート2026 βで限定的) | ✅ 公式 | ✅ | ✅ | 5-7日 (公式SDK経由) |
| GMOコイン | ✅ | ❌ (REST直叩き) | ⚠️ | ✅ | 3-5日 (国内SDK豊富) |

**Gemini指摘**: zoomex は CCXT非対応 + 公式Python SDK なし → 自作 REST client が必要。 これは **Phase 2.2 で 倍の工数**。 zoomex は **副選定からも除外** すべき。

### β. 手数料の物理計算 (Phase 3 Stage 2 想定: $2,250×3xレバ = $6,750ポジ、 月30トレード)

| 取引所 | maker | taker | 月手数料試算 | 備考 |
|---|---|---|---|---|
| bitget | 0.02% | 0.06% | $20-60 | BGB保有で -80% (= $4-12)、 大幅節約可能 |
| Hyperliquid | -0.001%リベート | 0.035% | $7-30 | maker rebate 取れれば実質マイナス |
| GMOコイン | 0% (Maker) | 0.05% | $15-35 | 国内最安、 ただし2x制限で運用規模半減 |
| zoomex | 0.02% | 0.06% | $20-60 | Bitget同等 |

**Gemini 重要発見**: **Hyperliquid maker rebate** (-0.001%) は HFT/逆指値運用で **手数料がリベートに転換** する仕組み。 Phase 2 のアルゴ運用で maker 比率 70%+ なら **手数料ゼロ以下** になる可能性。 これは bitget の BGB割引 (条件: BGB保有, 価格変動リスク) より構造的に堅い。

### γ. 板厚と流動性 (R48: 1注文上限 = 板厚×5%以下)

| 取引所 | BTC/USD perp 板厚 (top 5 levels) | Stage 2 ($6,750) 影響 | Cap 5 ($500k×3x = $1.5M) 影響 |
|---|---|---|---|
| Hyperliquid | $50M+ (2026春時点、 USDC建て) | 無影響 (0.00135%) | 板影響 3% (許容) |
| bitget | $200M+ (USDT建て) | 無影響 | 板影響 0.75% (余裕) |
| GMOコイン | $5-15M (円建て、 国内最大) | 無影響 (0.045%) | 板影響 10% (許容外) |
| zoomex | $10-30M (推定) | 無影響 (0.022%) | 板影響 5% (ぎりぎり) |

**Gemini 結論**: 規模拡大 (Cap 5 $500k) を見据えると **bitget の板厚が最大**。 ただし、 Hyperliquid も 2026年に板厚 $50M+ に成長しており Cap 3 ($100k) までは無問題。 GMOコイン は Cap 2 ($50k) で限界。

### δ. 障害リスクと取引所死亡確率

3者会議 Round 10 で議論した「取引所事故」の歴史:

| 取引所 | 過去5年の大障害 | 顧客資金保護 | 倒産・出金停止リスク |
|---|---|---|---|
| Hyperliquid | DEX (取引所死亡概念なし、 スマートコントラクトハック < 1% TVL) | オンチェーン (自分のwallet) | **ゼロ** (DEXなので) |
| bitget | 2024年 部分障害 (約2時間)、 保護基金 $300M | カストディ | 低 (大手CEX) |
| GMOコイン | 大障害なし、 法定通貨と分別管理 | 国内法定保護 | **ゼロ** (国内登録、 法的保護) |
| zoomex | 設立2022年で歴史浅い | 不明 | 中〜高 (実績不足) |

**Gemini 重要指摘**: **Hyperliquid は「自分のwallet」が資産** → 取引所が死んでも資産が消えない (オンチェーン)。 これは CEX に対する構造的アドバンテージ。 ただし「自分の秘密鍵管理」のリスクはある (R64 取引所障害、 R56 鍵漏洩 で別途対策必要)。

### ε. 推奨アーキテクチャ: 2系統 (主+副)

**Gemini最終提案**:

```
[主] Hyperliquid (DEX、 高レバ、 手数料リベート、 倒産リスクゼロ)
  ├─ Phase 2 から実弾運用 (KYC不要、 Walletに USDC送るだけ)
  ├─ Stage 2 まで主軸 (Cap 3 = $100k まで板厚OK)
  └─ Wallet秘密鍵管理は Cobo MPC or Ledger (Phase 2.5 で別途実装)

[副] bitget (CEX、 板厚最大、 BGB保有で手数料節約、 規模拡大対応)
  ├─ Phase 4以降の Cap 3 → Cap 5 で板厚優位
  ├─ Hyperliquid 障害時の退避先
  └─ 既登録なので Phase 2.2 で即実装可能

[待機] GMOコイン (国内法的安全、 円建て、 Tax-Engine連携最強)
  ├─ Phase 5+ 永続フェーズで Maintain Mode 時の縮小避難先
  ├─ 円→USDC変換不要
  └─ MoneyForward 直連携、 確定申告自動化最強
```

### ζ. リスク追加 R70-R72

- **R70 (DEX 秘密鍵管理)**: Hyperliquid を主にすると、 Wallet 秘密鍵 を Shujiさんが管理する必要 → Cobo MPC や Ledger 等のハードウォレット必須。 Cloud Runのservice account に秘密鍵を持たせるのは **絶対禁止**
- **R71 (Bitget金融庁規制リスク)**: 個人利用は合法だが、 もし日本で完全撤退要請が出たら退避必要 → 規制動向の月次監視+退避シナリオを Phase 5+ Vacation Mode と統合
- **R72 (Hyperliquid 流動性集中リスク)**: Hyperliquid TVL の急減・急増による板厚変動 → 板厚監視の閾値アラート、 BTC perp の depth が $30M を下回ったら Bitget へ自動切替

### Gemini判定

**主 Hyperliquid + 副 bitget + 待機 GMOコイン の3系統構成**で、 全Phase 2-5+ を再設計すべき。

zoomex は **CCXT非対応で工数倍 + 歴史浅く事故リスク不明** で除外。 Exness/Vantage/bitbank は GPTの脱落基準で確定除外。

Claudeへ実装可能性レビューと反対意見を求める。

---

## Round 30 — Claude監査 (実装担当+反対意見)

### α. 自白の続き

私 (Claude) は memory の `project_btc_auto_trading.md` を読まずに Bybit を主軸として実装着手していた。 これは feedback_information_brokerage / feedback_read_before_analyze の重大違反。 既に GPT・Gemini は司会・技術深掘りで動いてくれている。 私は **「実装担当」 として 技術的反対意見と実装現場の制約** を出す。

### β. Gemini「Hyperliquid主」案への反対意見

**Claude反対意見1: Phase 2 着手時点でのKYC・Wallet調達コスト**

Hyperliquid は KYC不要だが、 **Wallet 準備が必要**。 これは Shujiさんが Phase 2 (Day 15-) から実弾投入する時に:
- Cobo MPC アカウント開設 + KYC (個人向けで可)
- ハードウェアウォレット (Ledger等) 購入 ($100-200)
- USDC → ETH gas代 用意 (Arbitrum bridge)
- Hyperliquid の wallet 接続+ USDC 入金

**問題**: Shujiさん は CLAUDE.md で「**非エンジニア、 自分で全部やる Claude に任せる**」スタンス。 Wallet秘密鍵管理は Shujiさんの作業負荷を増やす。 Cap 1 ($25k) 未満の Phase 2-3 で DEX の利点 (倒産リスクゼロ) を取りに行く必要が本当にあるか?

**Claude反対意見2: 「板厚 Cap 5 で 3%影響」は許容外**

Gemini計算で Hyperliquid Cap 5 ($1.5M) で板影響 3%。 これは **R48 (1注文 板厚×5%以下)** に近すぎる。 段階キャップが Cap 5 を超える将来 (Phase 5.4 永続) を考えると、 Hyperliquid は規模上限が見える。

**Claude反対意見3: maker rebate に頼ったコスト試算は楽観的**

Phase 2-3 のアルゴ運用で maker 比率 70%+ を達成できるかは未検証。 急変時 (R32 Black Swan) は taker 注文が必要で、 そこで手数料が跳ねる。 maker rebate を前提とした「実質手数料ゼロ」は **realistic baseline ではない**。

### γ. Claude独自案: **bitget 主 + Hyperliquid 副** (主副逆転)

```
[主] bitget (CEX、 板厚最大、 BGB割引、 既登録、 CCXT完全対応)
  ├─ Phase 2 から実弾運用 (既登録 + USDT入金即可能)
  ├─ Stage 2 〜 Cap 5 ($500k) まで板厚耐性あり
  ├─ Python SDK / CCXT で 3-5日実装、 工数最小
  └─ 手数料 BGB保有で月 $4-12 (試算)

[副] Hyperliquid (DEX、 倒産リスクゼロ、 障害退避)
  ├─ Phase 3 後半 (Cap 1 到達後) に追加導入
  ├─ bitget 障害時の自動退避先
  ├─ Wallet秘密鍵管理は Phase 3 着手前に Shujiさんに準備依頼
  └─ KYC不要なのでアカウント開設不要、 Wallet 準備のみ

[待機] GMOコイン (国内法的安全、 確定申告連携)
  ├─ Tax-Engine 接続先として Phase 5.1 で実装
  ├─ Maintain/Protect Mode 時の縮小避難先 (法的最強)
  └─ 円建て出金で MoneyForward 直連携
```

### δ. Claude vs Gemini の対立点まとめ

| 論点 | Gemini | Claude | 対立理由 |
|---|---|---|---|
| 主取引所 | Hyperliquid (DEX) | bitget (CEX) | Wallet秘密鍵管理の負荷 |
| Phase 2 着手即可能性 | △ (Wallet準備必要) | ◎ (既登録、 即可能) | Shuji作業負荷 |
| 規模拡大 Cap 5 | △ (板影響3%) | ◎ (板影響0.75%) | Phase 5.4 永続性 |
| 倒産リスク | ◎ (ゼロ) | △ (低だが存在) | リスク優先度 |
| 法規制リスク | ◎ (DEX規制対象外) | ⚠️ (FSA警告継続中) | 規制トレンド予測 |
| 実装工数 | △ (5-7日) | ◎ (3-5日) | Phase 2.2 着手スピード |

**Claude見解**: Gemini が言う「DEX 倒産ゼロ」は正論だが、 **Phase 2 (Day 15-45) の Stage 0/1 ($15-50) では倒産リスク が現実問題にならない**。 一方、 Wallet秘密鍵管理は Phase 2 着手即発生する負荷。 「優先度が異なる」と言える。

### ε. 折衷案 (Claude提案)

**Phase 2-3 (Day 15-160)**: **bitget 主、 GMOコイン待機** で開始
- 理由: 既登録のみで即着手、 Phase 2.2 実装工数最小、 板厚最大
- Hyperliquid は **Phase 3 後半 (Day 120-160)** で追加導入 (Cap 1 到達後、 規模拡大に備える)

**Phase 4以降 (Day 161-)**: **bitget 主 + Hyperliquid 副** に2系統化
- 障害退避を構築 (R64 3取引所同時障害)
- Hyperliquid は Cap 2 ($50k) 以下で運用、 Cap 3+ では bitget メイン

**Phase 5+ (Day 240-)**: **3系統 (bitget主 + Hyperliquid副 + GMOコイン待機)** で完成形
- GMOコインは Maintain Mode / 緊急退避 / 確定申告連携の3用途

### ζ. リスク R73-R74 追加 (Claude独自)

- **R73 (Wallet秘密鍵管理 ヒューマンエラー)**: Hyperliquid 主にすると Shuji が秘密鍵を紛失・流出させるリスク → Ledger 物理ハードウォレット必須 + バックアップシードフレーズの金属保管 + Shuji教育コスト発生
- **R74 (Bitget日本完全撤退シナリオ)**: 2026年中に FSA から完全撤退要請が出る可能性 (Bybit同様) → 月次規制監視ジョブ実装、 撤退発表から 90日以内に Hyperliquid 主軸へ移行する避難計画書作成

### η. Geminiにぶつけたい論点 (Round 31 用)

1. Phase 2 着手時点で Hyperliquid Wallet秘密鍵管理を Shujiさんに依頼するのは妥当か (Claude反対)
2. bitget BGB保有でコスト最小化 vs Hyperliquid maker rebate、 どちらが現実的か
3. bitget の FSA 警告 → 完全撤退リスク評価 (Bybit前例ありで楽観視できない)
4. GMOコインの「2x制限」 を Phase 5+ Maintain Mode の縮小避難先と位置付けるのは妥当か
5. zoomex 除外は正しいか (既登録の優位性を捨てる根拠は CCXT非対応のみで十分か)

### θ. Shujiさんに確認したい大枠2つ

1. **Wallet秘密鍵管理を Shujiさん自身が担う意思があるか** (Hyperliquid 採用の前提条件、 Ledger等の物理デバイス管理が発生)
2. **Phase 2 即着手 (bitget主) vs Phase 3 まで延期して理想構成構築 (Hyperliquid主) どちらを選ぶか**

### ι. Round 30 Claude結論

Gemini「Hyperliquid主」 vs Claude「bitget主」 で対立。 **折衷案 (Phase別の主軸ローテーション)** を提示。 Round 31 で GPT 司会監査と Gemini 反論、 さらに Round 32+ で Shujiさん 大枠確認後に最終確定。

GPT 司会へバトン。

---


### Round 30-37 完結宣言

8ラウンドの 3者会議 (取引所再選定) を **完結**。 これ以上の議論は不要。 実装着手フェーズへ移行。

| ラウンド | 内容 | 結論 |
|---|---|---|
| Round 30 | Bybit撤退判明、 4候補絞り込み | 候補3+待機3 |
| Round 31 | 未開設取引所も網羅 | bitFlyer Lightning Vacation用追加 |
| Round 32 | クロージング v3→v4 | Wallet階層化 + 送金経路 |
| Round 33 | Shuji大枠確認用 v4確定 | 3者合意 |
| Round 34 | taritari + MT5/Exness 反映 v5→v6 | 並走戦略 |
| Round 35 | 3者合意宣言 v6 | 確定 |
| Round 36 | Shuji鋭い指摘 (網羅性) | v6→v7 微調整 |
| Round 37 | Shuji 最終決定 (FXGT削除) | **v7 確定** |


---
