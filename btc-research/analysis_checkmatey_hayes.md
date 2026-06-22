# BTC分析手法調査: @_Checkmatey_ & @CryptoHayes

---

## 1. @_Checkmatey_ (James Check, Glassnode Lead Analyst)

### 1-1. 使用するオンチェーン指標と閾値

| 指標 | 閾値・ルール | 用途 |
|------|-------------|------|
| **STH-SOPR** (Short-Term Holder SOPR) | **< 1.0 = 買い場** (短期保有者が損失で売却中 = ローカルボトム) | 最頻出指標。ブルマーケット中のディップ検知 |
| **STH-MVRV** | **< 1.0 = ディスカウント買い**, 155日移動平均を上抜け = ラリー開始 | STH-SOPRとセットで使用 |
| **MVRV Ratio** | **+1sd到達 = 警戒/天井圏** (初回は通常突破できない), **全コホート(総合/LTH/STH)が水面下 = ベアボトム** | サイクル天井・底の判定 |
| **Realized Price** | **スポット価格 < Realized Price = 極度の割安** (歴史上0.2%の日数でしか発生しない) | 究極の底値判定。2022年$24kで該当 |
| **Realized Cap** | ドローダウン-18.8% = 2011年に次ぐ2番目の歴史的規模 (2022-23ベア) | 資本流入/流出の絶対量を測定 |
| **Puell Multiple** | +/- 1sd = 極値シグナル (Confluence Toolの4指標の1つ) | マイナー収益のサイクル判定 |
| **aSOPR** (Adjusted SOPR) | +/- 1sd = 極値シグナル | Confluence Toolの4指標の1つ |
| **Reserve Risk** | +/- 1sd = 極値シグナル | Confluence Toolの4指標の1つ |
| **Value Days Destroyed Multiple** | 高値 = 古いコインが大量移動 (mania), 低値 = クールダウン (買い場) | 古参ホルダーの行動測定 |
| **Sell-Side Risk Ratio** | **低水準 = 次の大きな値動きが近い** (ボラティリティ先行指標) | トレンド疲弊/均衡状態の検知 |
| **Illiquid Supply** | 増加 = 強気 (コールドストレージへの蓄積) | 供給サイドの長期トレンド |
| **Exchange Balance** | 減少 = 強気 (ただし「枯渇」はしない。価格上昇=新規売り手が活性化) | 短期的な需給 |
| **Liveliness** | ATH = 極度の古いコイン移動 (分配フェーズ) | 長期ホルダーの行動 |
| **200DMA** | 下回り = 確率的に下方向リスク増大、上抜け = 強いシグナル | テクニカルとの融合 |
| **0.6x Mayer Multiple** | Realized Priceと200W MAと同時に下回り = 歴史上0.2%の日 | 極度の割安判定 |
| **Supply < 1 month old** | 7%未満 = ATL = 極度のHODL状態 = 強気 | HODL波動分析 |
| **STH Unrealised P/L Bollinger Bands** | 上限バンド = FOMOしない、下限バンド = 積極的にスタック | 独自開発メトリック |

### 1-2. 「Confluence Tool」 -- 代表的分析パターン

Checkmateyが開発した最重要ツールの1つ:
- **4指標**: MVRV, Puell Multiple, aSOPR, Reserve Risk
- **ルール**: 各指標の+/- 1標準偏差を監視。**4つ中3つ以上が極値 = シグナル発火**
- 過熱時(+1sd以上が3/4) = 売り/利確ゾーン
- 冷却時(-1sd以下が3/4) = 買い/蓄積ゾーン

### 1-3. Workbench/CheckOnChainの主要チャートパターン

1. **Onchain Originals Pricing Bands**: MVRV+1sd, Vaulted Price等の歴史的価格帯を重ね表示
2. **Bear Recovery Dashboard**: 8つのオンチェーンシグナル(価格モデル/アクティビティ/損益/供給ダイナミクス)が全点灯 = ベア脱出
3. **STH Bollinger Bands**: 短期ホルダーの未実現損益にBollinger Bandsを適用
4. **Top Heavy Market Framework**: コストベース集積をビジュアル化し、損失転落リスクのあるBTC量を分析
5. **Choppiness Index**: レンジ縮小(高水準) = 次のトレンド発生が近い
6. **LTH Realized Cap Z-Score**: 長期ホルダーの月次損失規模をZ-Score化

### 1-4. BTCサイクルの判定基準

Checkmateyは **ハービングではなく、採用と市場構造のトレンド**でサイクルを定義:

| サイクル | 特徴 | 転換点 |
|---------|------|--------|
| **Cycle 1: リテール初期採用** | 小規模、個人投資家中心 | 2017年天井で終了 |
| **Cycle 2: Wild West / Boom & Bust** | FTX/LUNA等の暴走と崩壊 | 2022年底で終了 |
| **Cycle 3: 機関投資家時代** | ETF、Treasury Company、$2T MCap | 現在進行中 |

**キーポイント**:
- ハービングの4年周期は偶然の一致。真の駆動力は採用波動
- 「ディミニッシング・リターン」理論は今サイクルで死ぬ(2年連続100%+のリターン)
- 過去のベアの-90%ドローダウンは今後BTC本体ではなくTreasury Company株で発生する

### 1-5. 的中/外れの事例

#### 的中
| 時期 | コール | 結果 |
|------|-------|------|
| 2021/11 ($58k付近) | STH-SOPRが1を下回り、バウンスを予想 | $51kまで回復 (12月) |
| 2021/11 ($54k) | STH Realized Priceリテストはブルマーケットのサポート。「2017に似てきた」 | 正しい読み(ただし最終的に2022ベアへ) |
| 2022/05 ($24k) | Realized Price($24k)にキス=割安。「BTC is cheap」 | $17kまで更に下落後、底を形成 |
| 2022/08 ($20k以下) | 「Realized Priceの下=歴史的に最高の買い場」として購入報告 | 的中。2023年に大幅回復 |
| 2023/02 | ベア回復ダッシュボード8/8シグナル点灯 | ベアの終わりを正確に示唆 |
| 2024/06 ($61k) | 30日レンジ8.3%=歴史的低ボラ→次にボラティリティ爆発 | 的中。その後大きく動く |
| 2024/07 ($58k) | 独政府の5万BTC売りを吸収。「LUNAと違う」と明言 | 的中。回復してATHへ |
| 2024/11 ($69k ATH突破) | MVRV冷却済み、Euphoria zoneに入るが健全。「チョプソリデーションが土台」 | 的中。$100k超えへ |
| 2025/02 | 底形成水準。Realised Lossが歴史的規模 | 進行中 |

#### 外れ/タイミングずれ
| 時期 | コール | 結果 |
|------|-------|------|
| 2021/09 ($45k) | 200DMA奪還で強気シグナル。同月中に$40kのサポート言及 | 結果的に$69kまでラリー後、大暴落 |
| 2022/04 ($40k) | 「ベアはまだ安値を更新できていない」 | その後$17kまで暴落 |
| 2022/05 | Realized Priceタッチで「安い」→更に-30%下落 | 底を正しく識別したが、最終底($17k)まで時間がかかった |

**総評**: Checkmateyは「ここが底だ」とピンポイント予測するのではなく、**確率的にどの領域にいるか**を示すスタイル。バリュー投資的なアプローチで、タイミングよりゾーンを重視。

### 1-6. ki_young_juとの分析手法の差異

| 項目 | Checkmatey | ki_young_ju |
|------|-----------|-------------|
| **所属** | Glassnode Lead Analyst → CheckOnChain独立 | CryptoQuant CEO |
| **主要指標** | MVRV, SOPR, Realized Cap, Sell-Side Risk Ratio | Exchange Reserve, Whale Ratio, Fund Flow, UTXO Age Band |
| **分析スタイル** | 教育的・フレームワーク構築型。「行動パターン」重視 | データドリブン・アラート型。「異常値」重視 |
| **売り手分析** | 「HODLerが売った」=需要が吸収したなら強気 | Exchange流入量=即座に弱気シグナル |
| **サイクル観** | 3サイクル論(採用波動ベース) | 4年ハービングサイクル踏襲傾向 |
| **予測スタンス** | 「ゾーン」を示す。ピンポイント予測を明示的に否定 | 具体的な方向性を示す傾向が強い |
| **データソース** | Glassnode Workbench, checkonchain.com | CryptoQuant独自データ |

### 1-7. 教育的投稿から抽出したルール

1. **STH-SOPR < 1.0 + STH-MVRV < 1.0 = 買い場** (「意味のあるディスカウント」を探す)
2. **STH-SOPR のブルマーケット挙動**:
   - 1.0への急落+回復 = Good (買い)
   - 1.0以下の持続的ブレイク = Not Good (売り)
   - 1.0で跳ね返される = シートベルト着用 (ベアトレンド移行リスク)
3. **STH-SOPR高い時 = 買わない** (利確売り圧力が高い)
4. **Confluence 3/4以上 = 行動シグナル** (MVRV, Puell, aSOPR, Reserve Risk)
5. **Sell-Side Risk Ratio低下 = 次の大きな値動きが近い** (オプション IV と同じチャートに重ねると更に精度向上)
6. **80%以上のSTHが水面下 = 2018/2019/mid-2021と同等のパニックリスク**
7. **ベアマーケットは資産を「せっかちな人」から「辛抱強い人」に移転する**
8. **LTHがATH突破後に売り始めるのは正常** (スマートマネーが高値で利確)
9. **Realized Capの成長 = 真の資本流入** (MCap変動の$1に対する実際の資金流入量はRCから推定)
10. **「モデルは将来の価格を予測できない」** -- 投資家の行動パターンを読め
11. **Exchange残高は枯渇しない** -- 価格上昇=新たな売り手が活性化する

---

## 2. @CryptoHayes (Arthur Hayes, BitMEX創業者)

### 2-1. マクロ経済分析の枠組み

Hayesの核心テーゼ: **BTC = フィアット流動性のスモークアラーム**

#### 流動性方程式 (Hayes流)
```
Net Liquidity = Fed Balance Sheet - TGA - RRP
```

**監視する変数と閾値**:

| 変数 | 強気シグナル | 弱気シグナル |
|------|------------|------------|
| **RRP (Reverse Repo)** | 減少 = 流動性が市場に戻る | 増加 = 流動性吸収 |
| **TGA (Treasury General Account)** | 残高を減らす(=ゼロに向かう) = $1tn規模の流動性注入 | 税収で増加 = 流動性吸収 |
| **QT/QE** | QT終了/QE再開 = Brrr | QT継続 = 流動性縮小 |
| **MOVE Index (債券ボラ)** | **>140 = Fed介入がほぼ確実 = Yachtzee time** | 低位安定 = Fedは動かない |
| **10年債利回り+株価** | 株下落+利回り下落 = Good / 株下落+利回り上昇 = Bad(資金逃避) | 後者はFed即時行動の引き金 |
| **SLR (Supplementary Leverage Ratio)** | 免除 = BTC orbital | - |
| **SOFR vs Fed Funds Rate** | SOFR > FF = Fed がSRFで密かにマネープリント | - |
| **US Bank Credit (独自指標)** | トレンド上昇 = 強気オッズ上昇 | - |
| **Fed H.4.1 レポート** | Foreign currency denominated assetsの増加 = 為替介入 = マネープリント | - |
| **Standing Repo Facility (SRF)** | 利用増 = ステルスQE | - |

#### Hayesのマクロフレームワーク (因果連鎖)
```
関税/財政赤字 → 外国人のドル収入減少 → 国債を買えない
→ 国債市場混乱 → 利回り上昇 → Fed/銀行が買い支え必須
→ マネープリント → BTC上昇
```

### 2-2. BTCの長期見通しと根拠

| 時期 | 見通し | ロジック |
|------|-------|---------|
| 2022/01 | ベア ("Maelstrom") | プリンターがBrrrしていない=暴落 |
| 2022/07 | $1M長期ターゲット | USD=EUR (DoomLoop) → YCC不可避 |
| 2022/11 | $17,500リスク (FTX後) | FTX=Lehman。2009年のSPX 666に相当する更なる下落 |
| 2023/03 | $1M ("Kaiseki") | BTFP=YCC by another name。無限マネープリント |
| 2023/11 | ブル開始 | RRP$200bn減少。流動性注入明確 |
| 2024/01 | $30k-$35kへの下落 ("Yellen or Talkin'") | TGA/QRAが短期的に逆風 |
| 2024/08 | BTFD。$300bn-$1.05tn注入 ("Spirited Away") | BOJ利上げ撤回+Yellen QRA |
| 2025/01 | $70k-$75kへの調整→$250k年末 | ミニ金融危機→マネープリント再開 |
| 2025/03 | $77kが底の可能性。ただし株にはまだ痛み | QT終了4/1。SLR免除orQE再開待ち |
| 2025/04 | $76.5kが防衛ライン→Tax Day (4/15)まで持てば安全 | 関税→国債市場混乱→Fed介入 |
| 2026/01 | $1M。Run it hot | 長期テーゼ継続 |

### 2-3. デリバティブ市場の構造理解

| コンセプト | Hayesの知見 |
|-----------|-----------|
| **Cash & Carry Trade** | ETFスポット買い+先物/Perpショートでベーシス稼ぎ。デルタニュートラルだが「BTC価格を押し上げているわけではない」 |
| **Cross Margin 自動清算** | CEXのクロスマージン自動清算がアルト暴落の主因(2025/10の急落時) |
| **Options OI集中帯** | $70k-$75kにOI集中 → そこまで下がると「violent」(Hayes 2025/03) |
| **MOVE Index >140** | 債券ベーシストレードの強制清算 → Fed介入トリガー |
| **FTX時のプットヘッジ** | FTX崩壊時に$15kストライクプット購入 (実際のポジション開示) |
| **短期ショート** | 2024/09に$50k以下狙いのショート。3%利益で食事代回収して手仕舞い |
| **Perp Funding** | 持続的高ファンディング=過熱 (直接言及は少ないが構造理解は深い) |

### 2-4. 具体的なトレード判断の言及

| 日付 | アクション | 結果 |
|------|----------|------|
| 2022/01 | "Maelstrom"でベア予告 | 的中。$69k→$17k |
| 2022/11 | $15kプット購入 (FTX崩壊時) | BTCは$15.5kまで下落。ほぼ的中 |
| 2023/03 | "Kaiseki"で超強気転換 | 的中。$20k→$70k+ |
| 2023/11 | "YOLO now" | 的中。2024年ブル加速 |
| 2024/01 | $30k-$35k下落予想+$35kプット購入 | **外れ**。$38kまでしか下がらず反転 |
| 2024/08 | BOJ撤回でBTFD | 的中。V字回復 |
| 2024/09 | $50k以下狙いショート→3%で利確 | 小さく成功 |
| 2025/01 | $70k-$75k調整→$250k年末 | $77kまで下落(ほぼ的中)。年末は未確定 |
| 2025/03 | $77kが底=probable | 進行中 |
| 2025/04 | $76.5k防衛ライン。「BUY THE FUCKING DIP」 | 進行中 |

**的中率の特徴**: 大局的な方向性(ブル/ベア)は高精度。具体的な底値は20-30%のずれがある。

### 2-5. Lyn Aldenとのマクロ分析の共通点/相違点

| 項目 | Hayes | Lyn Alden |
|------|-------|----------|
| **共通: BTC=流動性の関数** | Net Liquidity = Fed BS - TGA - RRP | Global Net Liquidity (より広範。M2全体を含む) |
| **共通: フィアット劣化テーゼ** | 「Fuck Fiat」。法定通貨は死ぬ | 「Long-term fiscal dominance」。財政赤字の構造的問題 |
| **相違: リスク許容度** | 超攻撃的。ショートもロングもガンガン | 保守的。ロング中心。ショートは推奨しない |
| **相違: 分析対象の幅** | 米国中心 + 日本(BOJ) + 中国(PBOC) | よりグローバル。新興国の債務構造も分析 |
| **相違: コミュニケーション** | エッセイ + 煽り + ポジション開示 | 学術的・データ重視。煽りゼロ |
| **相違: デリバティブ** | 深い理解。オプション/Perp/ベーシスの実戦知識 | デリバティブにはほぼ言及しない |
| **相違: 隠れた流動性** | FDIC、SRF、SLR免除など「ステルスQE」を追跡 | Fed B/S直接 + 財務省の操作を追跡 |
| **共通: QT終了=ブル** | QT over = buy everything | QT end = net liquidity inflection |

### 2-6. エッセイから抽出した手法

| エッセイ名 | 時期 | 核心テーゼ |
|-----------|------|-----------|
| **"Maelstrom"** | 2022/01 | プリンターがBrrrしていない→クリプト暴落。流動性が全て |
| **"Energy Cancelled"** | 2022/03 | ペトロダラー体制の終焉→Gold $10k, BTC $1M |
| **"Kaiseki"** | 2023/03 | BTFP = YCC by another name。銀行危機→無限印刷 |
| **"The Denominator"** | 2023/05 | 米銀行システム国有化。コストは預金者が負担 |
| **"Spirited Away"** | 2024/08 | BOJ利上げ撤回+Yellen QRA=BTC BTFD |
| **"Yellen or Talkin'"** | 2024/01 | QRA次第で短期弱気。$30-35k risk |
| **"ETF Wif Hat"** | 2024/01 | ETF承認の市場インパクト分析 |
| **"Black or White"** | 2024/11 | Trump=ドル毀損+マネープリント。BTC先行指標 |
| **"KISS of Death"** | 2025/02 | TrumpがPowell追い込み→利下げ+QE不可避 |
| **"BBC Bazooka"** | 2025/04 | Treasury buybacks=ステルスQE |
| **"Frowny Cloud"** | 2026/01 | MSTR/Metaplanetレバレッジロング推奨 |
| **SRFエッセイ** | 2025/11 | Standing Repo Facility=新たなステルス印刷 |

---

## 3. Checkmatey vs Hayes: 手法比較

| 項目 | Checkmatey | Hayes |
|------|-----------|-------|
| **分析レイヤー** | オンチェーン(ホルダー行動) | マクロ(流動性・金融政策) |
| **時間軸** | 中期(数週間-数ヶ月) | 中長期(数ヶ月-数年) |
| **強み** | 「誰が売り、誰が買っているか」を可視化 | 「なぜ流動性が増減するか」の因果を特定 |
| **弱み** | マクロイベント(Fed、BOJ)の急変に対応しにくい | オンチェーンの需給バランスを見ない |
| **相互補完** | オンチェーンで「現在の需給」を確認 | マクロで「今後の流動性方向」を予測 |
| **トレードスタイル** | バリュー投資的DCA | 流動性トレンドに乗るスウィング |
| **予測精度** | ゾーン(上/中/下)は高精度 | 方向は高精度、価格は20-30%ずれ |

---

## 4. 自動売買への実装可能な具体ルール

### Checkmateyから
1. `IF STH_SOPR < 1.0 AND STH_MVRV < 1.0 THEN buy_signal = true`
2. `IF MVRV_ratio > mean + 1sd THEN reduce_exposure()`
3. `IF confluence_extreme_count >= 3 of 4 (MVRV, Puell, aSOPR, Reserve Risk at -1sd) THEN strong_buy`
4. `IF confluence_extreme_count >= 3 of 4 (all at +1sd) THEN strong_sell`
5. `IF sell_side_risk_ratio < low_threshold THEN expect_volatility_soon`
6. `IF spot_price < realized_price THEN max_accumulation()`
7. `IF sth_supply_in_loss > 80% THEN panic_risk = high (contrarian buy if bull intact)`

### Hayesから
1. `IF MOVE_index > 140 THEN fed_intervention_imminent = true; buy_btc()`
2. `IF QT_ends OR QE_restarts THEN full_long()`
3. `IF RRP_declining AND TGA_stable THEN liquidity_injection = true`
4. `IF stocks_down AND 10yr_yield_up THEN crisis_mode = true; fed_must_act()`
5. `IF TGA_drawdown_to_zero THEN expect_1tn_injection()`
6. `IF SLR_exemption_granted THEN btc_orbital()`
7. `Net_liquidity = fed_bs - tga - rrp; IF trend_up THEN bull`

### 両者を組み合わせた複合シグナル
```
STRONG_BUY:
  Hayes: MOVE>140 OR QT終了 OR net_liquidity上昇トレンド
  AND
  Checkmatey: STH-SOPR<1.0 AND STH-MVRV<1.0 AND Confluence 3/4

STRONG_SELL:
  Hayes: QT加速 OR net_liquidity下降トレンド
  AND
  Checkmatey: MVRV>+1sd AND VDD Multiple高値 AND Confluence 3/4(上方向)
```
