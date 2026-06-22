# danjer (@smile_danjer) Chart Analysis 2024-2026

## Analysis Summary

Analyzed 2,604 images (615 in 2024, 1,253 in 2025, 736 in 2026).
Sampled every 5th image (521 total), with priority analysis of 128 high-value images.
Visually inspected 50+ images covering all major categories.

---

## 1. Indicator Settings (Confirmed from Screenshots)

### TradingView Indicators

| Indicator | Settings | Timeframes Used | Notes |
|-----------|----------|-----------------|-------|
| **Ichimoku Cloud (一目雲)** | Default (v9), some charts show v7 | 4H, 8H, D, 3D | Most used indicator. 187 mentions. |
| **SMA** | SMA100, SMA200 | 4H, 8H, D | Often used with Ichimoku. SMA200 as major S/R. |
| **MACD** | Default | 3D, D | Used for GC/DC signals. 3D MACD is a key tool. |
| **IVBand (Implied Volatility Band)** | Daily 68%, Weekly 68% | 2H, 4H | Shows step-function bands. Upper/lower as targets. |
| **Parabolic SAR** | Default | 4H, D | Used for trend confirmation. GC/DC (green/red) signals. |
| **GMMA改 (GMMA Modified)** | "GMMA 改 by GENSUI & dkn" | 5m (scalping) | Custom modified GMMA. Color-coded bands (green=up, orange/red=down). Convergence=range, Divergence=trend. |
| **TARS (Breakout Indicator)** | Custom (overlays as v3/v4) | 4H, 8H, D, W | Detects consolidation squeeze. Green arrows = breakout imminent. Sub-pane shows oscillator (0-100 scale). First appeared 2024/10, heavily used 2025+. |
| **APS (Auto Position System)** | "APS Ver.12 3 TOTAL 0 0 20" | D | Custom indicator visible in 2025. Shows position signals. Settings: "A A 3 3 下 左 2 60 EMA 80 EMA 80 0.6" + "水平線... 1,000 30 20 0.5 ヒゲ 起点から右 40 40" |
| **ZigZag++** | Default | 1H | Used in 2024 only. Dropped by 2025. |
| **Fibonacci Retracement** | 0, 0.236, 0.382, 0.5, 1.0 | D, W, M | Standard levels. 0.236 used as initial bounce target. |
| **BOT (Buy Order Threshold?)** | Visible in toolbar | 8H | Appears in layout names. |

### TradingView Layout Names (from screenshots)

- `7_TOTAL` - Main multi-indicator layout
- `8_BTC_TARS` - TARS-focused layout for BTC
- `1.BTUSD_co` / `1.BTUSD_coin` - Coinbase charts
- `Smileク...` - Custom Smile layout
- `9_通貨ペア用` - Multi-currency pair layout
- `無題` - Unnamed (quick analysis)

### Sub-pane Indicators (Bottom Panels)

| Panel | Description |
|-------|-------------|
| **Sell/Buy Volume** | Green/red/blue bars showing buy vs sell volume with delta |
| **MACD** | Standard MACD histogram + signal lines |
| **Custom Volume Indicator** | Color-coded volume bars (green/blue/red zones) with GC/DC markers |

---

## 2. CoinGlass LEGEND Layout (Critical Tool)

### Full Panel Configuration (from screenshots)

CoinGlass LEGEND is danjer's primary derivatives analysis tool. Layout (top to bottom):

| Panel | Data | Key Settings |
|-------|------|-------------|
| 1. **Price + Liquidity Heatmap** | Binance BTC USDT Perp, 30m/1H/2H/6H | Overlaid heatmap showing liquidation clusters |
| 2. **Footprint** | Volume footprint chart | Shows bid/ask imbalance |
| 3. **Orderbook Liquidity** | Buy/Sell/Depth/Ratio | e.g., "Buy 1.89K, Sell -2.47K, Depth -573.70, Ratio -0.13" |
| 4. **Aggregated Liquidations** | Long/Short liquidations | Shows extreme liquidation events (>100M = significant) |
| 5. **Open Interest** | OI in BTC terms (e.g., 98.05K) | Main decision tool. OI increase + price up = normal. OI increase + price down = danger. |
| 6. **Funding Rate** | Current FR % | Positive = longs pay. Negative = shorts pay. FR(-) = longers advantaged. |
| 7. **Long/Short Ratio (Accounts)** | Account-based ratio | e.g., 1.04, 2.82, 0.91 |
| 8. **Coinbase BTC Premium Index** | Spot premium vs Binance | Positive = institutional buying |

### CoinGlass Standalone Tools

| Tool | Usage | Frequency |
|------|-------|-----------|
| **Liquidation Heatmap (精算ヒートマップ)** | 3-day view, BTC, 流動性しきい値=0.83 | Heavy use in 2024-2026 |
| **Max Pain (最大の痛み)** | Deribit options, BTC/ETH | Growing use in 2025-2026 |
| **Coinbase Bitcoin Premium Index** | 30m timeframe | New adoption mid-2025 |

---

## 3. Cycle Theory Settings (Confirmed from Charts)

### Cycle Hierarchy

| Cycle | Period | Bars/Bars-Timeframe | Typical Range |
|-------|--------|---------------------|---------------|
| **3-Month Cycle (3ヶ月サイクル)** | 70-90 days | 24-30 bars on 3D chart | Bottom dates marked (e.g., 8/5, 11/4, 2/13, 6/22, 9/1) |
| **90-Day Cycle (90日サイクル)** | ~90 days | 90-91 bars on D chart | Overlaps with 3-month cycle |
| **30-Day Cycle (約30日サイクル)** | 25-32 days | 25-32 bars on D chart | Sub-cycles within 90-day |
| **4H Cycle (4Hサイクル)** | 60-86 bars on 4H | ~10-14 days | Most actively traded cycle. Used for entry timing. |

### Cycle Annotations on Charts

- **Yellow curve line**: Idealized cycle arc (half-sine wave)
- **White curve line**: Alternative cycle path
- **Red/Pink curve**: Bearish cycle path
- **Rectangle boxes**: Cycle measurement zones showing "XX バー, YY日 ZZ時間" (bars, days, hours)
- **Date labels in circles**: Predicted cycle bottoms (e.g., "11/21", "12/19", "1/20 前後?")
- **Left/Right Translation**: サイクルトップが左寄り(LT=bearish) or 右寄り(RT=bullish)

### Cycle Amplitude Measurements (from charts)

Typical amplitudes observed:
- 4H cycle: 8-16% swings (e.g., "10,901.12 (12.47%) 1,090,112, 65バー")
- 3-month cycle: 28-72% swings (e.g., "47,667.59 (58.17%) 4,766,759, 81バー")

---

## 4. Chart Pattern Frequency by Year

| Pattern | 2024 | 2025 | 2026 | Trend |
|---------|------|------|------|-------|
| **レンジ (Range)** | 61 | 170 | 91 | Core concept, always dominant |
| **サイクル理論** | 19 | 58 | 53 | Massive increase. Primary framework by 2025+ |
| **チャネル (Channel)** | 3 | 55 | 33 | Huge increase 2025+ (下降/上昇チャネル) |
| **OI分析** | 26 | 64 | 37 | Consistent heavy use |
| **精算/ロスカット** | 46 | 32 | 36 | Always important |
| **半値 (Half-value)** | 6 | 38 | 22 | Major increase. "前日半値" as key S/R |
| **フラクタル** | 9 | 34 | 8 | Peaked in 2025 |
| **インサイド (Inside bar)** | 1 | 7 | 23 | Major new pattern in 2026 |
| **ピンバー** | 0 | 0 | 11 | Brand new in 2026 |
| **包足 (Engulfing)** | 0 | 24 | 1 | 2025 peak |
| **前日安値/高値** | 10 | 33 | 29 | Growing importance |
| **CME窓** | 23 | 22 | 13 | Consistent |
| **アノマリー** | 14 | 14 | 14 | Perfectly consistent |
| **ウェッジ** | 7 | 0 | 0 | Dropped completely |
| **エリオット** | 2 | 6 | 0 | Dropped in 2026 |
| **ZigZag++** | 3 | 0 | 0 | Dropped after 2024 |

---

## 5. New Tools Adopted in 2024-2026

### 2024 New Adoptions
- **CoinGlass Liquidation Heatmap (精算ヒートマップ)**: Heavy use from Q1 2024
- **TARS Breakout Indicator**: First appeared Oct 2024. Custom indicator detecting consolidation squeezes.

### 2025 New Adoptions
- **CoinGlass LEGEND (Full Dashboard)**: Multi-panel with OI, FR, Liquidation, Orderbook, Premium Index
- **Coinbase Bitcoin Premium Index**: Mid-2025 adoption. Used to gauge institutional flow direction.
- **GMMA改 (Modified GMMA)**: "GMMA 改 by GENSUI & dkn" for 5m scalping
- **フラクタル分析 (Fractal Analysis)**: Comparing current pattern to historical periods (e.g., 2023/10 breakout)
- **Parabolic SAR**: Increased from rare to regular use (2 -> 20 mentions)
- **IVBand**: More systematic use with Daily/Weekly 68% levels
- **Options MaxPain**: CoinGlass Deribit options data for price targets
- **BlackRock Flow Tracking**: Monitoring BlackRock Coinbase deposits (started late 2025)
- **USDT Supply Tracking**: Monitoring USDT market dynamics
- **APS Ver.12**: Custom auto-position indicator with complex settings
- **Velo (曜日別リターン)**: Platform for BTC 1y average return by day of week

### 2026 New Adoptions
- **ピンバー (Pin Bar) Analysis**: 11 mentions, 0 in prior years
- **インサイド (Inside Bar)**: Jumped from 7 to 23 mentions
- **Bybit vs Binance OI Comparison**: Comparing OI changes between exchanges
- **大口成売り/買板 (Large Order Book Flows)**: Specific tracking of whale orders (300枚x9連=3000枚 etc.)
- **コールウォール (Call Wall)**: Options-based resistance tracking
- **「レ」パターン**: Custom pattern name - sharp drop then mild rise = bearish

---

## 6. Key Differences from 2022-2023

### Framework Evolution
| Aspect | 2022-2023 | 2024-2026 |
|--------|-----------|-----------|
| **Primary Framework** | Elliott Wave + ZigZag | Cycle Theory + OI/FR + Fractal |
| **Elliott Wave** | Core (mentioned frequently) | Nearly abandoned (2 -> 6 -> 0) |
| **ZigZag++** | Regular use | Completely dropped |
| **Cycle Theory** | Mentioned but secondary | **Primary decision framework** |
| **OI/Liquidation** | Basic awareness | **Core execution tool** - every trade checks OI |
| **Fractal** | Rare | Heavy use 2025 (34 mentions) |
| **CME Gap** | Known but less systematic | Systematic tracking with exact $ levels |

### Tool Stack Evolution
| Aspect | 2022-2023 | 2024-2026 |
|--------|-----------|-----------|
| **Chart Platform** | TradingView (basic) | TradingView (multiple custom layouts) |
| **Derivatives Data** | Basic exchange tools | CoinGlass LEGEND (full dashboard) |
| **Indicators** | SMA, Ichimoku, MACD | + IVBand, TARS, GMMA改, Parabolic, APS |
| **Options** | Not used | MaxPain, Call Wall, OP expiry dates |
| **On-chain** | Not tracked | Coinbase Premium, USDT, BlackRock flows |
| **Anomaly** | Occasional mention | Systematic (曜日別, 月末, OP期限, FOMC) |

### Trading Style Evolution
| Aspect | 2022-2023 | 2024-2026 |
|--------|-----------|-----------|
| **Scalping** | Basic | 秒スキャ with GMMA改 on 5m chart |
| **Swing** | Basic support/resistance | Cycle-based (buy at cycle bottom, sell at top) |
| **Position Sizing** | Not visible | Multiple brokers: FXGT, XM, Exness. Small lots (0.01-0.5 BTC) |
| **Risk Management** | Basic stops | 建値ストップ (breakeven stop) as standard practice |
| **Multi-timeframe** | 2-3 timeframes | Systematic: M -> W -> 3D -> D -> 8H -> 4H -> 30m -> 5m |

---

## 7. Trading Platform Details

### Brokers Used (from position screenshots)
- **FXGT**: JPY account, BTCUSD. Small account (~10,000 JPY base). 0.05 lot visible.
- **XM**: Referenced multiple times
- **Exness**: Referenced for scalping
- **Binance**: Derivatives (OI/FR analysis)
- **Bybit**: Derivatives (OI comparison)

### Account Sizes (from performance screenshots)
- 2024/01: -37万 day swing visible
- 2025/08: 244,539 JPY balance, multiple BTCUSD positions (0.08 buy + 0.5+0.5+0.3+0.3 sell)
- 2026/01: +62万 daily, +70万 unrealized = ~130万 day. Monthly 550万.
- 2026/03: Account down to 92,961 JPY (after drawdown period)
- 2026/03: 10,000 JPY balance with 0.05 sell position (small account)

### Leverage
- High leverage used (証拠金率 692-761%)
- Small lot sizes relative to account (risk management)

---

## 8. Cycle Theory Detailed Settings

### 3-Month Cycle Bottoms (Tracked Dates)
**Confirmed pattern from charts**:
- 2024/08/05 -> 2024/11/04 -> 2025/02/13 -> 2025/04/07 -> 2025/06/22 -> 2025/09/01 -> 2025/11/21 -> 2026/02/06 -> (next: ~2026/04/25)

### 4H Cycle Typical Length
- 60-86 bars (10-14 days)
- Recent pattern: 65 bars becoming standard

### Key Cycle Rules (from tweets)
1. サイクル理論 = 安値～安値の時間間隔
2. 横軸（時間軸）の考察 - 縦軸（価格）ではない
3. ライトトランスレーション = 上昇トレンド（高値が右寄り）
4. レフトトランスレーション = 下降トレンド（高値が左寄り）
5. 起点割れ = レフトトランスレーション確定 = ロング待機
6. 3回高値更新 = エリオット的な「3」で反転しやすい

---

## 9. Decision Framework (Distilled from 2025-2026)

### Entry Criteria (Long)
1. サイクルボトム付近（横軸で判断）
2. OI減少 = ロンガー諦め + ショートカバー完了
3. 極大ロング精算発生後（リバ期待）
4. FR(-) = ロンガー有利
5. Coinbase Premier (+) = 現物強い
6. 前日安値 / 半値 をサポート確認

### Entry Criteria (Short)
1. サイクルトップ付近
2. OI増加 + 価格上昇後の停滞
3. FR高止まり + ショート減少
4. Coinbase Premier (-) = 現物弱い
5. IVバンド上限到達

### Exit Rules
1. 建値ストップ必須（breakeven stop）
2. 損益ドヤ = 99% 天井 -> 半分利確
3. IVバンド上限/下限で利確検討
4. サイクルトップ予定時期で利確

### Key Time-Based Rules
- 水曜日 = 最強（曜日アノマリー）
- 木曜日 = 最弱
- 月末 = 調整入りやすい
- OP期限 = 価格吸引（MaxPain方向へ）
- CME窓 = 必ず埋まる（時間かかることも）
- アメリカ時間開始（22:30 JST）= 方向性出やすい
- FR確定時間（25:00）= リバポイント

---

## 10. Performance Screenshots Summary

| Date | Daily P&L | Notes |
|------|-----------|-------|
| 2024/01/10 | -37万 -> プラ転 | Volatile swing |
| 2024/03/01 | Large profit | "バブってる" |
| 2025/08/23 | +24.4万 (account) | Multiple positions |
| 2026/01/09 | +50万 daily, +70万 unrealized | Monthly 550万 |
| 2026/01/12 | +62万 daily, +70万 unrealized | 130万 day |
| 2026/03/04 | 92,961 JPY balance | After drawdown |

---

## 11. Timeframe Usage (from tweet text)

| Timeframe | 2024 | 2025 | 2026 | Primary Use |
|-----------|------|------|------|-------------|
| 月足 | 5 | 12 | 13 | Long-term trend + cycle |
| 週足 | 13 | 52 | 23 | TARS, cycle confirmation |
| 3日足 | 10 | 42 | 38 | MACD, cycle, Ichimoku |
| 日足 | 45 | 144 | 97 | Primary analysis timeframe |
| 8時間足 | - | - | - | TARS, Ichimoku, GMMA (seen in charts) |
| 4時間足 | 24 | 108 | 34 | 4H cycle, entry timing |
| 1時間足 | 10 | 14 | 6 | Short-term structure |
| 30分足 | - | - | - | Execution (GMMA改 area) |
| 5分足 | 12 | 7 | 6 | Scalping with GMMA改 |
| 1分足 | 8 | 3 | 3 | Precise entry |

**Key shift**: 3日足 usage exploded (10 -> 42 -> 38), reflecting increased cycle theory focus.

---

## 12. Annotation Style

danjer uses a consistent visual annotation style on charts:

| Element | Color | Meaning |
|---------|-------|---------|
| **Yellow arrows/lines** | Yellow | Price movement prediction |
| **Pink/Magenta arrows** | Pink | Warning / bearish signal |
| **Green arrows** | Green | Bullish signal / target |
| **Orange arrows** | Orange | Major trend direction |
| **Pink rectangles** | Pink | Key price zones / S&R |
| **Yellow rectangles** | Yellow | Important zones |
| **Numbered circles (1,2,3)** | Pink/Magenta | Sequential analysis points |
| **Date labels in circles** | Pink/Red | Cycle bottom predictions |
| **Yellow curve** | Yellow | Cycle arc (idealized) |
| **White dashed lines** | White | Trendlines / channels |
| **Pink solid lines** | Pink | Descending channel boundaries |

All annotations are hand-drawn using TradingView's drawing tools on mobile and desktop.
