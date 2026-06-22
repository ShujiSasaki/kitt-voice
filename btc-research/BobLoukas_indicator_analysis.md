BTCトレーダーronpochiのチャート画像データから、以下の分析結果をまとめました。

---

### 1. 使用している全インジケーターのリスト(名前、パラメータ/期間、用途)

ronpochiトレーダーが使用しているインジケーターは以下の通りです。

*   **Bollinger Bands (ボリンジャーバンド)**
    *   **パラメータ/期間:**
        *   期間: 20, 標準偏差: 2
        *   期間: 20, 標準偏差: 不明
        *   期間: 1日足
        *   期間: 不明, 標準偏差: 不明
        *   期間: 不明, 標準偏差: 不明 (値がパラメータとして誤認識された可能性)
    *   **用途:** 価格のボラティリティ（変動幅）を示すバンド。価格がバンドの上下に達すると逆張りシグナルとされたり、バンドの収縮・拡大でボラティリティの変化を予測する。中心線は移動平均線。

*   **Bollinger Bands Width**
    *   **パラメータ/期間:** 期間: 20, 標準偏差: 2
    *   **用途:** ボリンジャーバンドの幅（アッパーバンドとロワーバンドの差）を示し、ボラティリティの拡大・収縮を数値化する。スクイーズやエクスパンションの判断に用いる。

*   **Detrended Price Oscillator (DPO)**
    *   **パラメータ/期間:** 期間: 30
    *   **用途:** 価格からトレンドを取り除き、サイクルやオシレーションを視覚化する。買われすぎ・売られすぎの状態や、サイクル転換点を捉えるのに役立つ。

*   **Double Smoothed Stochastic (DSS)**
    *   **パラメータ/期間:**
        *   期間K: 10, 期間D: 9, 平滑化期間: 5, 買われすぎ: 80, 売られすぎ: 20
        *   パラメータ: 不明
    *   **用途:** Stochastic Oscillatorをさらに平滑化したもので、買われすぎ・売られすぎの状態をより滑らかに表示し、騙しを減らすことを意図する。

*   **Exponential Moving Average (EMA)**
    *   **パラメータ/期間:** 期間: 短期
    *   **用途:** 指数平滑移動平均線。単純移動平均線よりも直近の価格に重きを置いて計算されるため、価格変動への反応が速い。

*   **MACD (移動平均収束拡散)**
    *   **パラメータ/期間:**
        *   短期EMA期間: 12, 長期EMA期間: 26, シグナル期間: 9
        *   パラメータ: 不明
    *   **用途:** 短期と長期の移動平均線の差からトレンドの勢いと転換点を示す。MACDラインとシグナルラインのクロスやヒストグラムの変化を分析する。

*   **Moving Average (移動平均線)**
    *   **パラメータ/期間:**
        *   期間: 9
        *   期間: 10
        *   期間: 20
        *   期間: 26
        *   期間: 40
        *   期間: 100
        *   期間: 200
        *   期間: 1日足
        *   期間: 10週足
        *   期間: 20 SMA (推定)
        *   期間: 50 SMA (推定)
        *   期間: 不明
        *   期間: 不明 (短期と中期MA)
    *   **用途:** 価格の平滑化を行い、トレンドの方向性や強さを把握するために使用。期間が短いほど直近の価格変動に敏感に反応し、長いほど長期的なトレンドを示す。

*   **Moving Average Cross (MAクロス)**
    *   **パラメータ/期間:** パラメータ: 不明 (通常は2本のMA期間)
    *   **用途:** 2本以上の移動平均線（通常は短期と長期）のゴールデンクロス（短期が長期を上抜く）やデッドクロス（短期が長期を下抜く）を売買シグナルとする。

*   **RSI (Relative Strength Index)**
    *   **パラメータ/期間:**
        *   期間: 5
        *   期間: 7
        *   期間: 14
        *   期間: 不明
    *   **用途:** 買われすぎ・売られすぎの状態を示すオシレーター。0から100の範囲で、一般的に70以上で買われすぎ、30以下で売られすぎと判断される。

*   **Stochastic RSI**
    *   **パラメータ/期間:** RSI期間: 10, %K期間: 9, %D期間: 5
    *   **用途:** RSIの値をストキャスティクスでさらに平滑化したもので、RSI単体よりも敏感に買われすぎ・売られすぎを捉え、トレンド転換の初期シグナルとして機能する。

*   **Volume (出来高)**
    *   **パラメータ/期間:**
        *   期間: 20
        *   期間: 不明
    *   **用途:** 取引量の多さを示し、価格変動の信頼性を測る。出来高を伴う値動きは信頼性が高いとされる。

### 2. 時間足ごとのインジケーター使い分け

データには時間足の明示的な記述が少ないですが、以下のパターンが確認できます。

*   **日足 (1D):**
    *   Moving Average (2回)
    *   Bollinger Bands (2回)
*   **週足 (10-week):**
    *   Moving Average (2回)
    *   RSI (1回)
*   **不明:**
    *   最も多くのインジケーターが「不明」な時間足で使用されています。これは、チャート画像から時間足が特定できなかったか、または日足以下の短期足での利用が多い可能性を示唆します。
    *   Moving Average (130回)
    *   Bollinger Bands (87回)
    *   Volume (58回)
    *   RSI (36回)
    *   Double Smoothed Stochastic (25回)
    *   MACD (3回)
    *   Moving Average Cross (2回)
    *   Detrended Price Oscillator (1回)
    *   Bollinger Bands Width (1回)
    *   Stochastic RSI (1回)
    *   Exponential Moving Average (1回)

### 3. インジケーターの組み合わせパターン (出現頻度が高い順)

最も頻繁に見られるインジケーターの組み合わせは以下の通りです。

1.  **Bollinger Bands, Moving Average, Volume** (31回)
2.  **Bollinger Bands, Moving Average** (30回)
3.  **Moving Average, Volume** (14回)
4.  **Bollinger Bands, Moving Average, RSI, Double Smoothed Stochastic** (4回)
5.  **Moving Average** (4回)
6.  **Bollinger Bands, Moving Average, Volume, RSI** (3回)
7.  **Moving Average, RSI, Double Smoothed Stochastic** (3回)
8.  **Bollinger Bands, Moving Average, RSI** (2回)
9.  **MACD, Moving Average, RSI, Volume** (2回)
10. **Bollinger Bands, Moving Average, Volume, Double Smoothed Stochastic** (2回)

**考察:** 「Moving Average」と「Bollinger Bands」は非常に高い確率でセットで用いられており、これに「Volume」を加えた3点セットが最も基本的な監視パターンであると考えられます。RSIやDSSなどのオシレーター系は、これらトレンド・ボラティリティ系のインジケーターと併用され、売買タイミングの判断に用いられているようです。

### 4. 年ごとの変化

*   **2018年:**
    *   **使用インジケーター:** Bollinger Bands, Detrended Price Oscillator, Double Smoothed Stochastic, MACD, Moving Average, Moving Average Cross, RSI, Volume
    *   **追加されたインジケーター:** なし
    *   **廃止されたインジケーター:** なし
*   **2019年:**
    *   **使用インジケーター:** Bollinger Bands, Bollinger Bands Width, Double Smoothed Stochastic, Exponential Moving Average, MACD, Moving Average, Moving Average Cross, RSI, Stochastic RSI, Volume
    *   **追加されたインジケーター:** Bollinger Bands Width, Exponential Moving Average, Stochastic RSI
    *   **廃止されたインジケーター:** Detrended Price Oscillator, MACD
*   **2020年:**
    *   **使用インジケーター:** Bollinger Bands, Double Smoothed Stochastic, Moving Average, RSI, Volume
    *   **追加されたインジケーター:** なし
    *   **廃止されたインジケーター:** Bollinger Bands Width, Exponential Moving Average, Moving Average Cross, Stochastic RSI

**考察:**
*   **2019年**には、ボラティリティ分析に特化した「Bollinger Bands Width」や、RSIの感度を高める「Stochastic RSI」、トレンド分析の「Exponential Moving Average」が追加され、より多角的な分析を試みていた可能性があります。一方で「DPO」や「MACD」は使用されなくなりました。
*   **2020年**になると、MACDを除く多くの新規インジケーターが再び廃止され、「Moving Average」「Bollinger Bands」「Volume」「RSI」「Double Smoothed Stochastic」という核となる5つのインジケーターに収束している傾向が見られます。これは、よりシンプルで効率的な手法に回帰したことを示唆するかもしれません。

### 5. 最も依存度が高いインジケーターTOP5とその根拠

全データを通じて最も頻繁に出現するインジケーターは以下の通りです。

1.  **Moving Average (139回)**
    *   **根拠:** 最も出現頻度が高く、ほぼ全ての期間で利用されています。単独での使用から他のインジケーターとの組み合わせまで幅広く活用されており、トレンドの把握やサポート・レジスタンスの確認など、分析の基礎として不可欠な存在であることが示唆されます。様々な期間設定（10, 20, 100, 200, 1D, 10-weekなど）が試されています。

2.  **Bollinger Bands (92回)**
    *   **根拠:** Moving Averageに次いで高い出現頻度を誇ります。特に「Moving Average」とセットで使われることが多く、価格のボラティリティとバンドの収縮・拡大によるブレイクアウトの予測、またはバンドタッチでの反発狙いなど、トレンドとボラティリティの両面から相場を分析する上で重視されていると考えられます。主な設定は「期間: 20, 標準偏差: 2」です。

3.  **Volume (61回)**
    *   **根拠:** 価格変動の信頼性を測る上で不可欠な要素として、多くのチャートで表示されています。特に重要なトレンドの転換点やブレイクアウトの際に、その動きの裏付けとして出来高を重視していることが伺えます。

4.  **RSI (36回)**
    *   **根拠:** 買われすぎ・売られすぎの判断に用いられる代表的なオシレーターです。特に「期間: 5」という短期設定が多く見られ、素早い売買シグナルを捉えるために活用されている可能性があります。トレンド系のインジケーターと併用されることで、より精度の高いエントリー・エグジットポイントを探っていると考えられます。

5.  **Double Smoothed Stochastic (25回)**
    *   **根拠:** RSIと同様に買われすぎ・売られすぎを示すオシレーターですが、より平滑化されたDSSを好んで使用しているようです。RSIとDSSの両方を表示しているケースもあり、異なるオシレーターからのシグナルをクロスチェックしている可能性も考えられます。主要な設定は「期間K: 10, 期間D: 9, 平滑化期間: 5, 買われすぎ: 80, 売られすぎ: 20」です。

---