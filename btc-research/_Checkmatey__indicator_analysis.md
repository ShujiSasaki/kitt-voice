BTCトレーダーronpochiのチャート画像から抽出されたインジケーターデータを分析し、以下の情報をまとめました。

---

### 1. 使用している全インジケーターのリスト (名前、パラメータ/期間、用途)

ronpochi氏が使用しているインジケーターは多岐にわたります。以下に重複を整理し、主なパラメータと一般的な用途をまとめました。

**オンチェーン指標 & 価値評価モデル:**

*   **Stock-to-Flow (S2F) モデル**
    *   **パラメータ**: `BTC Price = exp(3.3195*ln(S2F)+14.6227)/Supply` (特定の計算式)、`Actual`, `Theoretical`, `Standard Deviations from S2F Model`
    *   **用途**: ビットコインの希少性に基づいた長期的な価格予測と、モデルからの乖離を測る。Decred (DCR) にも適用。
*   **Realised Price / Realised Cap**
    *   **パラメータ**: N/A
    *   **用途**: コインが最後に移動した時点の価格の平均（実現価格）や、それに基づく時価総額（実現時価総額）。市場参加者の平均取得コストを推定し、市場全体の心理状態や割安・割高を判断。
*   **Market Cap**
    *   **パラメータ**: N/A
    *   **用途**: 仮想通貨の総市場価値。
*   **NVT Ratio (Network Value to Transaction Ratio)**
    *   **パラメータ**: `28-day`, `90-day`, `NVTS` (シグナル)
    *   **用途**: 市場価値とオンチェーン取引量の比率。ネットワークの活動量に対して市場が割安か割高かを評価。
*   **RVT Ratio (Realised Value to Transaction Ratio)**
    *   **パラメータ**: `28-day`, `90-day`, `RVTS` (シグナル)
    *   **用途**: 実現時価総額とオンチェーン取引量の比率。NVTと同様にネットワークの活動量に対する評価を行うが、ホドラーの動きをより反映。
*   **MVRV Ratio (Market Value to Realised Value Ratio)**
    *   **パラメータ**: N/A
    *   **用途**: 市場価値と実現時価総額の比率。市場の過熱感や底値を判断する。
*   **Mayer Multiple**
    *   **パラメータ**: `ヒストグラムおよび累積分布`, `200DMAとの比率`, `STRONG BUY (0.6), BUY (0.8), CAUTION (1.6), SELL (2.4), STRONG SELL (3.4) for BTC; 0.4 (STRONG BUY), 0.5 (BUY), 1.6 (SELL), 2.8 (STRONG SELL) for DCR`
    *   **用途**: 現在価格と200日移動平均線の比率。歴史的なデータに基づき、市場の割安・割高、買い・売り水準を判断。
*   **Puell Multiple**
    *   **パラメータ**: `年間の移動平均に基づく`, `Ratio of Daily Issuance in USD to the 365day average of Daily Issuance`
    *   **用途**: 日次発行量と365日移動平均の比率。マイナーの収益性と市場の底値を判断。
*   **Difficulty Ribbon**
    *   **パラメータ**: `MA`, `D_9, D_14, D_25, D_40, D_60, D_90, D_128, D_200` (移動平均)
    *   **用途**: ハッシュレートの移動平均線群。マイナーの投売りや市場の底打ちを示すシグナルとして機能。
*   **Energy Density (Daily $ Settled / kWh), (Realised Cap / Daily kWh)**
    *   **パラメータ**: N/A
    *   **用途**: エネルギー消費量に対するネットワークの経済的活動の効率性。
*   **Min Energy spent (kWh)**
    *   **パラメータ**: N/A
    *   **用途**: 最低エネルギー消費量。
*   **Delta Price, Average Price, Top Price, Price Miner Inflow**
    *   **パラメータ**: N/A
    *   **用途**: デルタ価格 (実現価格 - 平均価格)、平均価格、歴史的なトップ価格、マイナーの流入価格など、市場の節目や基準価格を特定。
*   **S2F Multiple, Difficulty Multiple**
    *   **パラメータ**: `ヒストグラムおよび累積分布`
    *   **用途**: それぞれS2Fモデル価格、難易度に対する価格の乖離を測る。
*   **Market-Realised Gradient Oscillator**
    *   **パラメータ**: `30day gradient of Price and Realised price`, `142-Day`
    *   **用途**: 市場価格と実現価格の勾配変化を捉え、トレンドの転換点や勢いを判断。
*   **Mining Pulse (+ve, -ve)**
    *   **パラメータ**: N/A
    *   **用途**: マイニング活動の勢いを示す。

**移動平均 & オシレーター:**

*   **Triple MA (Moving Average)**
    *   **パラメータ**: `50, 128, 200`
    *   **用途**: 短期、中期、長期のトレンドを判断。
*   **DMA (Daily Moving Average)**
    *   **パラメータ**: `128`, `200`, `730`
    *   **用途**: 日足チャートにおけるトレンドライン。
*   **WMA (Weekly Moving Average)**
    *   **パラメータ**: `128`, `200`
    *   **用途**: 週足チャートにおけるトレンドライン。
*   **EMA (Exponential Moving Average)**
    *   **パラメータ**: `20 close`
    *   **用途**: 指数移動平均、短期トレンドを素早く捉える。
*   **MA**
    *   **パラメータ**: `26 close`
    *   **用途**: 単純移動平均、短期トレンドを捉える。
*   **RSI (Relative Strength Index)**
    *   **パラメータ**: `14, close`
    *   **用途**: 市場の買われすぎ・売られすぎを判断するオシレーター。
*   **CHOP (Chaikin Money Flow Oscillator)**
    *   **パラメータ**: `14`
    *   **用途**: トレンドの方向性と強さを判断する。

**出来高 & ネットワーク活動:**

*   **Volume**
    *   **パラメータ**: `20` (期間)
    *   **用途**: 取引量、価格変動の信頼性や勢いを測る。
*   **On-chain Volume (Transfer Vol), (Ticket Vol)**
    *   **パラメータ**: `Ticket Vol (DCR), Transfer Vol (DCR)`
    *   **用途**: ブロックチェーン上での実際の取引量。Decredにおいてはチケット取引量も重要。
*   **DCR Onchain Volume, DCR Exchange Vol**
    *   **パラメータ**: N/A
    *   **用途**: DCRのオンチェーン取引量と取引所での取引量。
*   **Active Address (Coinmetrics)**
    *   **パラメータ**: `DCR.AdrActCnt`
    *   **用途**: 活動中のアドレス数、ネットワークの利用状況を示す。
*   **Decred Transaction Volumes**
    *   **パラメータ**: `Regular, Tickets, Privacy Mixing`
    *   **用途**: DCRの通常の取引、チケット取引、プライバシーミキシングのボリューム。
*   **Unspent Anonymity Set**
    *   **パラメータ**: N/A
    *   **用途**: プライバシー機能の利用状況を示す。
*   **Stake Participation**
    *   **パラメータ**: N/A
    *   **用途**: DCRのPoS参加率。

**マイニング & 手数料:**

*   **Bitcoin Difficulty, Bitcoin Hashrate**
    *   **パラメータ**: N/A
    *   **用途**: ビットコインのマイニング難易度とハッシュレート。ネットワークのセキュリティとマイナーの動向を示す。
*   **Mean Fee, Median Fee, Fee Ratio**
    *   **パラメータ**: N/A
    *   **用途**: 平均手数料、中央値手数料、手数料と報酬の比率。ネットワークの混雑度や利用コストを示す。

**Decred (DCR) 固有指標:**

*   **POW, POS, Treasury**
    *   **パラメータ**: N/A
    *   **用途**: Decredの報酬配分モデル (プルーフ・オブ・ワーク、プルーフ・オブ・ステーク、トレジャリー)。
*   **Total DCR in Tickets, Ticket Pool Value**
    *   **パラメータ**: N/A
    *   **用途**: Decredのステーキングメカニズムにおけるチケットの状態。
*   **Decred Block Subsidy Valuation Models**
    *   **パラメータ**: `POW-USD, POS-USD, Treasury-USD, Total-USD, Supply Issued Cap (USD), Market Cap, Difficulty Ribbon`
    *   **用途**: Decredのブロック補助金に基づいた評価モデル。
*   **142-Day Ticket USD Sum**
    *   **パラメータ**: `142-day sum`, `x23.6%`, `x38.2%`, `x61.8%`, `x50.0%` (フィボナッチレベル)
    *   **用途**: DCRのチケットロックアップに関連する価格指標。
*   **142-Day TVWAP (Time-Weighted Average Price)**
    *   **パラメータ**: `142-day`
    *   **用途**: DCRの142日間の時間加重平均価格。
*   **Hodler Conversion Rate (+ve, -ve)**
    *   **パラメータ**: N/A
    *   **用途**: DCRのホドラーが売却行動に転じるか、買い増しに転じるかの比率。
*   **Ticket Funding Rate Z-Score Sum**
    *   **パラメータ**: `56-day metric`
    *   **用途**: DCRのチケット購入動向に基づくシグナル。
*   **DCR/BTC Price (Coinmetrics)**
    *   **パラメータ**: `DCR.PriceUSD/BTC.PriceUSD`
    *   **用途**: DCRの対BTC価格比。

**その他:**

*   **BTC.PriceUSD, USDT.CapMrktCurUSD + USDT_ETH.CapMrktCurUSD**
    *   **パラメータ**: N/A
    *   **用途**: ビットコイン価格とテザー（USDT）の時価総額。市場の流動性や資金流入を評価。
*   **相関係数 (Correlation Coefficient)**
    *   **パラメータ**: `90d, 180d, 360d, Spearman, Pearson, Arithmetic, Log`
    *   **用途**: 異なる資産間の相関関係を分析。

### 2. 時間足ごとのインジケーター使い分け

データから明示的な時間足の記載は少ないですが、パラメータや一般的な用途から以下のように推測されます。

*   **日足 (Daily) チャートでの利用が主と推測されるインジケーター:**
    *   **移動平均**: `DMA (128, 200, 730)`, `Triple MA (50, 128, 200)`（日足での使用も多い）
    *   **オシレーター**: `RSI (14)`, `CHOP (14)`
    *   **オンチェーン指標**: `NVT Ratio (28-day, 90-day)`, `RVT Ratio (28-day, 90-day)`, `Puell Multiple` (365日平均を基にするが日次で更新)、`Market-Realised Gradient Oscillator (30day, 142-Day)`
    *   **出来高**: `Volume (20)`
    *   **難易度関連**: `Difficulty Ribbon` (日次難易度に基づくMA群)
    *   **Decred固有**: `142-Day TVWAP`, `Ticket Funding Rate Z-Score Sum (56-day)`, `DCR Price 30DMA`
*   **週足 (Weekly) チャートでの利用が主と推測されるインジケーター:**
    *   **移動平均**: `WMA (128, 200)`, `200WMA`, `128WMA`
*   **長期トレンド分析 (時間足にとらわれない、または月足等も含む):**
    *   **価値評価モデル**: `Stock-to-Flow Model`, `Realised Price`, `Realised Cap`, `MVRV Ratio`, `Mayer Multiple` (200DMA/WMAなど長期MAが基準)
    *   **キャップ類**: `Market Cap`, `Top Cap`
    *   **累積指標**: `Cumulative PoW Block Reward`, `Cumulative Ticket Lockup`
    *   **その他**: `Delta Price`, `Energy Density`, `Hodler Conversion Rate`

### 3. インジケーターの組み合わせパターン

データ内の日付ごとのインジケーターリストから、頻繁に見られる組み合わせパターンを抽出しました。

*   **キャップとオンチェーン指標の基本セット**:
    *   `Market Cap`, `Realised Cap`, `NVT Ratio (28-day)`, `RVT Ratio (28-day)` (Mon Sep 23, Tue Jun 02など多数)
    *   `Market Cap`, `Realised Cap`, `MVRV Ratio` (Tue Feb 25, Thu Apr 23, Fri Jun 05など多数)
*   **S2Fモデルとその派生**:
    *   `BTC Stock-to-Flow (Actual)`, `DCR Stock-to-Flow (Actual)`, `BTC Stock-to-Flow (Theoretical)`, `DCR Stock-to-Flow (Theoretical)` (Wed Oct 02)
    *   `Bitcoin S2F Model`, `Decred S2F Model` (Mon Oct 07, Fri Oct 18)
*   **各種価格モデルとオンチェーン指標の包括的表示**:
    *   `Price USD`, `Realised Price`, `Average Price`, `Delta Price`, `Top Price`, `S2F Model (Actual/Theoretical)`, `NVT (28D, 90D, S)`, `RVT (28D, 90D, S)` (Wed Oct 02)
*   **移動平均と出来高のトレンド分析**:
    *   `Triple MA (50, 128, 200)`, `Volume (20)` (Fri Nov 15, Sat Dec 14, Wed Apr 29, Fri Jul 24など頻出)
    *   `DMA (128, 200)`, `WMA (128, 200)`, `Realised Price`, `Mayer Multiple`, `S2F Multiple`, `Diff Multiple` (Tue Dec 17)
*   **Mayer Multipleと長期移動平均**:
    *   `Mayer Multiple (バンドやBuy/Sell水準)`, `200DMA` (Sat Mar 28, Wed Apr 29, Tue Apr 07, Wed Jul 15)
*   **難易度とハッシュレート、難易度リボン**:
    *   `Bitcoin Difficulty`, `Bitcoin Hashrate`, `Difficulty Ribbon` (Mon Oct 07, Sun Feb 23など)
    *   `Difficulty Ribbon`, `Market Cap`, `Realised Cap`, `POW-USD`, `POS-USD`, `Treasury-USD`, `Total-USD`, `Difficulty` (Sat Jul 11, Mon Jul 13)
*   **Decred固有の報酬配分とオンチェーンボリューム**:
    *   `Market Cap`, `Total Subsidy`, `Treasury Subsidy`, `POS Subsidy`, `POW Subsidy`, `On-chain Volume (Transfer Vol), (Ticket Vol)` (Wed Nov 13)
*   **Market-Realised Gradient Oscillatorとキャップ、勾配**:
    *   `Decred Market-Realised Gradient Oscillator`, `Market Cap`, `Realised Cap`, `Market Gradient`, `Realised Gradient`, `Delta Gradient` (Wed May 06, Mon Jun 08, Mon Jul 13)

### 4. 年ごとの変化 (追加/廃止されたインジケーター)

このデータは2019年9月〜2020年7月までの観測をまとめたものであり、この期間におけるインジケーターの使用動向を示します。

*   **2019年 (9月〜12月):**
    *   **初期導入期**: S2Fモデル（BTCおよびDCR）、Realised Price/Cap、NVT/RVT Ratio、エネルギー関連指標、難易度/ハッシュレートなど、オンチェーン指標の基礎が導入されました。特にDCR固有の指標（Ticket Price, POW/POS/Treasuryのデータなど）もこの時期から見られます。
    *   **トレンド分析ツールの追加**: `Triple MA (50, 128, 200)`と`Volume (20)`が追加され、テクニカル分析の基礎も強化されました。
    *   **マルチプルの導入**: `Mayer Multiple`, `S2F Multiple`, `Difficulty Multiple`といった、200DMAやS2Fモデル価格からの乖離を測る指標が導入され、それらのヒストグラムや累積分布も分析対象となりました。DMA (128, 200), WMA (128, 200)もこの時期に登場。
*   **2020年 (1月〜7月):**
    *   **長期的な視点の強化**: `730DMA`とその派生 (`x5`)、`200WMA`などのさらに長期的な移動平均が導入されました。
    *   **より詳細なオンチェーン分析**: `MVRV Ratio`が本格的に使用され始め、`Cumulative Ticket Lockup`, `Cumulative PoW Block Reward`、手数料関連 (`Mean Fee`, `Median Fee`, `Fee Ratio`) など、ネットワークの経済活動をさらに深く分析する指標が追加されました。
    *   **特定の取引戦略の具体化**: `Mayer Multiple Bands`として、BTCとDCRそれぞれに具体的な買い・売りシグナルの水準 (`0.6 (STRONG BUY) `, `0.8 (BUY) `, `2.4 (SELL)`, `3.4 (STRONG SELL)` for BTC) が明示されました。
    *   **DCR固有の複雑な指標**: `Puell Multiple`、`Decred Block Subsidy Valuation Models`、`Decred Stock-to-Flow Network Valuation`、`142-Day Ticket USD Sum`とそのフィボナッチレベル、`Hodler Conversion Rate`、`Market-Realised Gradient Oscillator`、`Ticket Funding Rate Z-Score Sum`など、DecredのハイブリッドPoW/PoSモデルを深く掘り下げた指標が多数追加されました。
    *   **相関分析の導入**: `相関係数 (Correlation Coefficient)`が追加され、他の資産との関係性も分析対象となりました。

このデータを見る限り、廃止されたと明確に特定できるインジケーターはありません。むしろ、初期に導入された基本的なオンチェーン指標（S2F, Realised Price/Cap, NVT/RVT, Difficulty Ribbonなど）は継続して使用されつつ、時間の経過とともにさらに多角的で詳細な指標、特にDecredの特性を深く分析する指標が追加されていった傾向が見られます。

### 5. 最も依存度が高いインジケーターTOP5とその根拠

観測された頻度、パラメータの詳細度、BTCとDCR両方への適用、そして市場分析における一般的な重要度を考慮し、最も依存度が高いと考えられるインジケーターTOP5は以下の通りです。

1.  **Stock-to-Flow (S2F) モデルとその派生 (S2F Multiple, Actual/Theoretical S2F)**
    *   **根拠**:
        *   非常に多くのチャートで言及されており、BTCとDCRの両方に適用されています。
        *   具体的な計算式 (`BTC Price = exp(3.3195*ln(S2F)+14.6227)/Supply`) が明記されており、独自のモデルに基づいた分析を行っていることが伺えます。
        *   S2Fモデルからの乖離を測る`Standard Deviations from S2F Model`や`S2F Multiple`も頻繁に利用され、長期的な価格予測のベンチマークとして強く依存していると考えられます。
2.  **Mayer Multiple (および関連するBuy/Sell Bands)**
    *   **根拠**:
        *   多数のチャートに登場し、特に2020年以降はBTCとDCRそれぞれに具体的な買い・売り水準 (`0.6 (STRONG BUY), 0.8 (BUY), 2.4 (SELL), 3.4 (STRONG SELL) for BTC`など) が設定されていることから、具体的な取引戦略に直結する重要な指標として活用されていると推測されます。
        *   ヒストグラムや累積分布での分析も行っており、統計的な裏付けも重視していることが伺えます。
3.  **Realised Price / Realised Cap (および MVRV Ratio)**
    *   **根拠**:
        *   `Market Cap`とセットで非常に頻繁に登場し、特に`MVRV Ratio` (Market Value to Realised Value Ratio) の計算基盤となっています。
        *   MVRV Ratioは市場の過熱感や割安感を測る主要なオンチェーン指標であり、トレーダーの行動心理を分析し、市場の天井や底を判断するために不可欠な指標として重視されています。
4.  **Difficulty Ribbon (および Difficulty, Hashrate, Difficulty Multiple)**
    *   **根拠**:
        *   BTCとDCRの両方で`Difficulty Ribbon`が頻繁に言及され、具体的な移動平均の期間 (`D_9, D_14, D_25, D_40, D_60, D_90, D_128, D_200`) が列挙されています。
        *   ハッシュレートや難易度の変化はマイナーの健全性や市場への影響を直接的に示すため、ネットワークの基礎的な健全性と市場の転換点（特にマイナーによる投売り圧力が終わる時期）を判断する上で重視されていると考えられます。`Difficulty Multiple`の使用もこの依存度を補強します。
5.  **Triple MA (50, 128, 200) / 各種移動平均 (DMA/WMA)**
    *   **根拠**:
        *   `Triple MA`として`50, 128, 200`の期間が繰り返し登場し、具体的な数値も記載されています。また、`DMA (128, 200, 730)`や`WMA (128, 200)`など、様々な期間の移動平均が広く使用されています。
        *   これらは短期から超長期にわたるトレンド分析の基本的なツールであり、価格アクションの理解、サポート/レジスタンスレベルの特定、トレンドの強さや方向性の判断に汎用的に使われていることが、その頻度から強く示唆されます。

これらのインジケーターは、ronpochi氏が長期的な価値評価モデルとオンチェーンデータを重視し、それらを移動平均や派生指標と組み合わせて具体的な取引戦略に落とし込んでいることを示しています。