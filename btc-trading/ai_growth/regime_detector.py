"""BTC局面検出: trend / range / rally / crash

3者合意 (2026-06-24) のdanjer手法に近い局面判定。
ロジック:
- rally: 直近4hの変動率が大きく、 価格が +5%以上 / 6h
- crash: 同条件で -5%以下 / 6h
- trend: 4h EMA20 > 4h EMA50 (上昇) or 逆 (下降)
- range: 上記以外
"""
from __future__ import annotations


def _ema(values: list[float], period: int) -> float:
    """指数移動平均 (Exponential Moving Average)"""
    if len(values) < period:
        return sum(values) / len(values) if values else 0.0
    alpha = 2.0 / (period + 1)
    ema = values[0]
    for v in values[1:]:
        ema = alpha * v + (1 - alpha) * ema
    return ema


def _atr(candles: list[dict], period: int = 14) -> float:
    """Average True Range (ボラティリティ)"""
    if len(candles) < 2:
        return 0.0
    trs = []
    for i in range(1, len(candles)):
        h = candles[i]['high']
        l = candles[i]['low']
        prev_close = candles[i-1]['close']
        tr = max(h - l, abs(h - prev_close), abs(l - prev_close))
        trs.append(tr)
    if not trs:
        return 0.0
    n = min(period, len(trs))
    return sum(trs[-n:]) / n


def _price_change_pct(candles: list[dict], hours: int) -> float:
    """直近 N時間 の価格変動率 (%)"""
    if len(candles) < hours + 1:
        hours = len(candles) - 1
    if hours <= 0:
        return 0.0
    start = candles[-hours - 1]['close']
    end = candles[-1]['close']
    return (end - start) / start * 100


def detect_regime(candles: list[dict]) -> str:
    """局面検出

    Args:
        candles: list[dict] (最低30本以上推奨、 1時間足)

    Returns:
        'trend' | 'range' | 'rally' | 'crash'
    """
    if len(candles) < 20:
        return 'range'  # データ不足は range 扱い

    # 直近の価格変動率 (6h)
    change_6h = _price_change_pct(candles, hours=6)

    # ATR (直近4h vs 全体)
    recent_atr = _atr(candles[-4:], period=4)
    long_atr = _atr(candles, period=min(30 * 24, len(candles)))  # 30日相当 or 全体
    atr_ratio = recent_atr / long_atr if long_atr > 0 else 1.0

    # rally: 急騰 (+5%以上 / 6h、 ATR増大)
    if change_6h >= 5.0 and atr_ratio > 2.0:
        return 'rally'
    # crash: 急落 (-5%以下 / 6h、 ATR増大)
    if change_6h <= -5.0 and atr_ratio > 2.0:
        return 'crash'

    # EMA20 vs EMA50 (トレンド判定)
    closes = [c['close'] for c in candles]
    ema20 = _ema(closes, 20)
    ema50 = _ema(closes, 50) if len(closes) >= 50 else ema20
    diff_pct = (ema20 - ema50) / ema50 * 100 if ema50 > 0 else 0

    if abs(diff_pct) >= 1.0:
        return 'trend'  # 上昇 or 下降トレンド (どちらも trend として扱う)

    return 'range'


def _rsi(closes: list[float], period: int = 14) -> float:
    """Wilder's RSI"""
    if len(closes) < period + 1:
        return 50.0
    gains = []
    losses = []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
        gains.append(max(0, diff))
        losses.append(max(0, -diff))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


def _macd(closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
    """MACD = EMA(fast) - EMA(slow), Signal = EMA(MACD, signal)"""
    def _ema_series(values, period):
        if not values:
            return []
        alpha = 2.0 / (period + 1)
        result = [values[0]]
        for v in values[1:]:
            result.append(alpha * v + (1 - alpha) * result[-1])
        return result
    if len(closes) < slow + signal:
        return {'macd': 0.0, 'signal': 0.0, 'hist': 0.0}
    ema_fast = _ema_series(closes, fast)
    ema_slow = _ema_series(closes, slow)
    macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
    sig_line = _ema_series(macd_line, signal)
    return {
        'macd': macd_line[-1],
        'signal': sig_line[-1],
        'hist': macd_line[-1] - sig_line[-1],
    }


def _ichimoku(candles: list[dict]) -> dict:
    """一目均衡表 (転換線 / 基準線 / 先行スパンA/B / 遅行スパン)"""
    if len(candles) < 52:
        return {}
    def hl_avg(cs, n):
        if len(cs) < n:
            return 0.0
        recent = cs[-n:]
        return (max(c['high'] for c in recent) + min(c['low'] for c in recent)) / 2
    tenkan = hl_avg(candles, 9)
    kijun = hl_avg(candles, 26)
    senkou_a = (tenkan + kijun) / 2
    senkou_b = hl_avg(candles, 52)
    chikou = candles[-26]['close'] if len(candles) >= 26 else 0.0
    return {
        'tenkan': tenkan,
        'kijun': kijun,
        'senkou_a': senkou_a,
        'senkou_b': senkou_b,
        'chikou': chikou,
    }


def _fibonacci_levels(candles: list[dict], lookback: int = 100) -> dict:
    """直近 lookback本 の スイング高値/安値 から フィボ retracement"""
    if len(candles) < 2:
        return {}
    window = candles[-min(lookback, len(candles)):]
    high = max(c['high'] for c in window)
    low = min(c['low'] for c in window)
    diff = high - low
    return {
        'swing_high': high,
        'swing_low': low,
        'fib_0_382': high - diff * 0.382,
        'fib_0_5':   high - diff * 0.5,
        'fib_0_618': high - diff * 0.618,
    }


def extract_chart_vision_materials(vision_result: dict) -> list[str]:
    """Phase 3-② vision結果 → materials 言語化"""
    mats: list[str] = []
    if not vision_result:
        return mats
    if 'error' in vision_result:
        mats.append(f'チャートvision 取得失敗: {vision_result.get("error", "")[:60]}')
        return mats
    patterns = vision_result.get('patterns', []) or []
    direction = vision_result.get('trend_direction', '')
    summary = vision_result.get('summary_jp', '')
    dir_jp = {'up': '上昇', 'down': '下降', 'sideways': '横ばい'}.get(direction, direction)
    if patterns:
        mats.append(f'チャートパターン: {" / ".join(patterns)} (トレンド={dir_jp})')
    if summary:
        mats.append(f'チャートvision: {summary}')
    return mats


def extract_technical_materials(candles: list[dict]) -> list[str]:
    """Phase 3-① テクニカル指標 (SMA200/RSI/MACD/一目雲/フィボ) を 自前計算+言語化

    danjer 言及材料 TOP30 で カバーすべき: 一目雲(87) / SMA200(61) / RSI / MACD / フィボ(276カテゴリ) /
    高値更新(76) / 安値切り上げ(44) / レジサポ転換(80) / ボラティリティ(53)
    """
    mats: list[str] = []
    if len(candles) < 50:
        return mats

    closes = [c['close'] for c in candles]
    last_close = closes[-1]

    # SMA200
    sma_window = min(200, len(closes))
    sma200 = sum(closes[-sma_window:]) / sma_window
    diff_pct = (last_close - sma200) / sma200 * 100
    sma_jp = '上' if last_close >= sma200 else '下'
    mats.append(f'SMA{sma_window} ${sma200:.0f} (現値{last_close:.0f}、 SMA{sma_jp} {diff_pct:+.2f}%)')

    # RSI 14
    rsi14 = _rsi(closes, 14)
    if rsi14 >= 70:
        rsi_jp = '過熱(オーバーボート)'
    elif rsi14 <= 30:
        rsi_jp = 'オーバーソールド(押し目候補)'
    elif rsi14 >= 55:
        rsi_jp = '強気寄り'
    elif rsi14 <= 45:
        rsi_jp = '弱気寄り'
    else:
        rsi_jp = '中立'
    mats.append(f'RSI14 {rsi14:.1f} ({rsi_jp})')

    # MACD
    macd = _macd(closes)
    macd_v = macd.get('macd', 0)
    sig_v = macd.get('signal', 0)
    hist = macd.get('hist', 0)
    if hist > 0 and macd_v > sig_v:
        macd_jp = 'ゴールデンクロス側(強気)'
    elif hist < 0 and macd_v < sig_v:
        macd_jp = 'デッドクロス側(弱気)'
    else:
        macd_jp = '中立'
    mats.append(f'MACD={macd_v:+.1f} Signal={sig_v:+.1f} Hist={hist:+.1f} ({macd_jp})')

    # 一目均衡表
    ichi = _ichimoku(candles)
    if ichi:
        tenkan = ichi.get('tenkan', 0)
        kijun = ichi.get('kijun', 0)
        senkou_a = ichi.get('senkou_a', 0)
        senkou_b = ichi.get('senkou_b', 0)
        cloud_top = max(senkou_a, senkou_b)
        cloud_bottom = min(senkou_a, senkou_b)
        if last_close > cloud_top:
            ichi_jp = '雲上(強気)'
        elif last_close < cloud_bottom:
            ichi_jp = '雲下(弱気)'
        else:
            ichi_jp = '雲中(レンジ)'
        tk_jp = '上' if tenkan >= kijun else '下'
        mats.append(
            f'一目均衡表 転換{tenkan:.0f}/基準{kijun:.0f}/雲(A{senkou_a:.0f},B{senkou_b:.0f}) '
            f'(価格{ichi_jp}、 転換線基準線の{tk_jp})'
        )

    # フィボ retracement
    fib = _fibonacci_levels(candles, lookback=100)
    if fib:
        f382 = fib.get('fib_0_382', 0)
        f50 = fib.get('fib_0_5', 0)
        f618 = fib.get('fib_0_618', 0)
        sh = fib.get('swing_high', 0)
        sl = fib.get('swing_low', 0)
        # 現値が どの レベル に 一番近い か
        levels = [
            ('スイング高値', sh), ('0.382', f382),
            ('0.5', f50), ('0.618', f618), ('スイング安値', sl),
        ]
        nearest = min(levels, key=lambda x: abs(last_close - x[1]))
        dist_pct = (last_close - nearest[1]) / nearest[1] * 100 if nearest[1] else 0
        mats.append(
            f'フィボ100本: 高{sh:.0f}/0.382=${f382:.0f}/0.5=${f50:.0f}/0.618=${f618:.0f}/安{sl:.0f} '
            f'(現値は{nearest[0]}に最近、 {dist_pct:+.2f}%)'
        )

    return mats


def extract_market_materials(snapshot: dict, candles: list[dict] | None = None) -> list[str]:
    """loop2合意: public市場データ snapshot を materials 文字列に言語化

    snapshot = data_source.fetch_market_snapshot() の戻り値。
    OI/FR/L:S/板 を 日本語サマリ で 1つずつ materials に 追加。

    danjer 風 言語化:
    - OI: 「OI = N万BTC (現在値)」
    - FR: 「FR +0.012% (やや過熱)」 / 「FR -0.003% (中立)」
    - L:S: 「トップ建玉L:S = 1.83 (買い偏り)」
    - 板: 「板imbalance +0.15 (買い厚め)」 / 「best bid/ask スプレッド N$」
    """
    mats: list[str] = []
    if not snapshot:
        return mats

    # === OI ===
    oi = snapshot.get('oi') or {}
    if 'error' not in oi:
        oi_btc = oi.get('oi_btc', 0)
        if oi_btc > 0:
            mats.append(f'OI = {oi_btc:,.0f}BTC')
    else:
        mats.append('OI 取得失敗')

    # === Funding Rate ===
    fr = snapshot.get('funding') or {}
    if 'error' not in fr:
        rate = fr.get('funding_rate', 0)
        rate_bps = rate * 100  # %表示
        if rate_bps >= 0.05:
            judge = '過熱(売り受取)'
        elif rate_bps >= 0.01:
            judge = 'やや過熱'
        elif rate_bps <= -0.01:
            judge = '冷え(買い受取)'
        else:
            judge = '中立'
        mats.append(f'FR {rate_bps:+.3f}% ({judge})')
    else:
        mats.append('FR 取得失敗')

    # === Long/Short Ratio ===
    ls = snapshot.get('ls') or {}
    if 'error' not in ls:
        top_pos = ls.get('top_position_ls', 1.0)
        glb = ls.get('global_ls', 1.0)
        if top_pos >= 1.5:
            jp = 'トップ建玉ロング偏り'
        elif top_pos <= 0.7:
            jp = 'トップ建玉ショート偏り'
        else:
            jp = 'トップ建玉中立'
        mats.append(f'L:S top_pos={top_pos:.2f} global={glb:.2f} ({jp})')
    else:
        mats.append('L:S 取得失敗')

    # === Econ Calendar (Phase 2-③ 2026-06-24) ===
    cal = snapshot.get('econ_calendar') or {}
    if cal and 'error' not in cal:
        nearest = cal.get('nearest_event', '')
        days = cal.get('nearest_business_days', 999)
        fomc_d = (cal.get('next_fomc') or {}).get('business_days', 999)
        cpi_d = (cal.get('next_cpi') or {}).get('business_days', 999)
        nfp_d = (cal.get('next_nfp') or {}).get('business_days', 999)
        # ボラ警戒
        if days <= 1:
            jp = '直前(ボラ警戒、 ポジ抑制)'
        elif days <= 3:
            jp = '近い(週内警戒)'
        elif days <= 5:
            jp = '今週中'
        else:
            jp = '当面なし'
        mats.append(
            f'経済指標 直近={nearest}({days}営業日後)、 '
            f'FOMC={fomc_d}日 / CPI={cpi_d}日 / NFP={nfp_d}日 ({jp})'
        )
    elif cal:
        mats.append('経済指標カレンダー 取得失敗')

    # === ETF Flow (Phase 2-② 2026-06-24) ===
    etf = snapshot.get('etf_flow') or {}
    if etf and 'error' not in etf and etf.get('tickers'):
        total_usd = etf.get('total_usd_volume_5d', 0)
        avg_chg = etf.get('price_change_avg_pct', 0)
        # 5日平均 価格変化で 機関 需要 を 推測
        if avg_chg >= 2.0:
            jp = '機関買い増し示唆'
        elif avg_chg <= -2.0:
            jp = '機関売り示唆'
        else:
            jp = '中立'
        # 主要ETF (IBIT) を 代表表示
        ibit = (etf.get('tickers') or {}).get('IBIT') or {}
        ibit_str = ''
        if ibit:
            ibit_str = f'IBIT終値=${ibit.get("last", 0):.2f}'
        mats.append(
            f'BTC ETF 5d出来高合計=${total_usd/1e9:.2f}B 価格5d平均{avg_chg:+.2f}% '
            f'{ibit_str} ({jp})'
        )
    elif etf:
        mats.append('ETF 取得失敗')

    # === IV (Phase 2-① 2026-06-24) ===
    iv = snapshot.get('iv') or {}
    if iv and 'error' not in iv:
        dvol = iv.get('dvol_now', 0)
        chg = iv.get('change_pct', 0)
        level = iv.get('level', '')
        level_jp = {'low': '低ボラ(慎重なブレイク警戒)', 'high': '高ボラ(動意過熱)', 'mid': '中ボラ'}.get(level, level)
        sign = '+' if chg >= 0 else ''
        mats.append(
            f'IV (DVOL) {dvol:.1f}% (24h {sign}{chg:.2f}%、 {level_jp})'
        )
    elif iv:
        mats.append('IV 取得失敗')

    # === Fear & Greed (Phase 1-⑤ 2026-06-24) ===
    fg = snapshot.get('fear_greed') or {}
    if fg and 'error' not in fg:
        value = fg.get('value', 50)
        cls = fg.get('classification', '')
        val_5d = fg.get('value_5d_ago', value)
        chg = fg.get('change_5d', 0)
        # 日本語化
        cls_jp = {
            'Extreme Fear': '極度の恐怖',
            'Fear': '恐怖',
            'Neutral': '中立',
            'Greed': '貪欲',
            'Extreme Greed': '極度の貪欲',
        }.get(cls, cls)
        sign = '+' if chg >= 0 else ''
        if value <= 25:
            jp = 'BTC押し目候補(逆張り検討)'
        elif value >= 75:
            jp = 'BTC過熱(利確検討)'
        else:
            jp = '中立水準'
        mats.append(
            f'Fear & Greed {value} ({cls_jp}、 5日前{val_5d}→{sign}{chg}、 {jp})'
        )
    elif fg:
        mats.append('Fear & Greed 取得失敗')

    # === Macro (Phase 1-④ 2026-06-24) ===
    macro = snapshot.get('macro') or {}
    if macro and 'error' not in macro:
        def _row(key, label):
            d = macro.get(key) or {}
            if 'error' in d or not d:
                return None
            last = d.get('last', 0)
            chg = d.get('change_pct', 0)
            sign = '+' if chg >= 0 else ''
            return f'{label}={last:.2f}({sign}{chg:.2f}%)'
        parts = [s for s in (
            _row('dxy', 'DXY'),
            _row('spx', 'SPX'),
            _row('gold', 'Gold'),
            _row('us10y', '米10年金利'),
        ) if s]
        if parts:
            # BTC との 含意
            dxy_chg = (macro.get('dxy') or {}).get('change_pct', 0)
            us10y_chg = (macro.get('us10y') or {}).get('change_pct', 0)
            spx_chg = (macro.get('spx') or {}).get('change_pct', 0)
            risk_on = (spx_chg > 0.3) and (dxy_chg < 0)
            risk_off = (spx_chg < -0.3) or (dxy_chg > 0.5)
            if risk_on:
                jp = 'リスクオン環境 (BTC追い風)'
            elif risk_off:
                jp = 'リスクオフ環境 (BTC逆風)'
            else:
                jp = 'マクロ中立'
            mats.append('マクロ ' + ' / '.join(parts) + f' ({jp})')
    elif macro:
        mats.append('マクロ 取得失敗')

    # === Dominance (Phase 1-③ 2026-06-24) ===
    dom = snapshot.get('dominance') or {}
    if dom and 'error' not in dom:
        btc_d = dom.get('btc_d', 0)
        eth_d = dom.get('eth_d', 0)
        stable_d = dom.get('stable_d', 0)
        # BTC.D の 水準感
        if btc_d >= 60:
            jp = 'BTC優位(アルト弱含み)'
        elif btc_d <= 45:
            jp = 'アルト優位(BTC弱含み)'
        else:
            jp = '中立'
        mats.append(
            f'ドミナンス BTC.D={btc_d:.1f}% / ETH.D={eth_d:.1f}% / Stable.D={stable_d:.1f}% ({jp})'
        )
    elif dom:
        mats.append('ドミナンス 取得失敗')

    # === CVD (Phase 1-② 2026-06-24) ===
    cvd = snapshot.get('cvd') or {}
    if cvd and 'error' not in cvd:
        delta_usd = cvd.get('delta_usd', 0)
        count = cvd.get('count', 0)
        window = cvd.get('window_sec', 0)
        buy_usd = cvd.get('buy_usd', 0)
        sell_usd = cvd.get('sell_usd', 0)
        total = buy_usd + sell_usd
        if total > 0:
            ratio = buy_usd / total
            if ratio >= 0.55:
                jp = '買い優勢'
            elif ratio <= 0.45:
                jp = '売り優勢'
            else:
                jp = '均衡'
        else:
            jp = '出来高微小'
        # 言語化: window が秒単位、 1000件で 通常 数分
        win_str = f'{window/60:.1f}分' if window >= 60 else f'{window:.0f}秒'
        sign = '+' if delta_usd >= 0 else ''
        mats.append(
            f'CVD 直近{count}件({win_str}): {sign}${delta_usd/1e6:.2f}M ({jp})'
        )
    elif cvd:
        mats.append('CVD 取得失敗')

    # === Liquidations (Phase 1 開始 2026-06-24) ===
    liq = snapshot.get('liquidations') or {}
    if liq and 'error' not in liq:
        long_usd = liq.get('long_usd', 0)
        short_usd = liq.get('short_usd', 0)
        count = liq.get('count', 0)
        dur = liq.get('duration_sec', 30)
        largest_long = liq.get('largest_long_usd', 0)
        largest_short = liq.get('largest_short_usd', 0)
        if count == 0:
            mats.append(f'清算 直近{dur}秒: 0件 (清算静穏)')
        else:
            # 偏り判定
            total = long_usd + short_usd
            if total > 0:
                ratio = long_usd / total
                if ratio >= 0.7:
                    jp = 'ロング清算優勢(下落圧)'
                elif ratio <= 0.3:
                    jp = 'ショート清算優勢(上昇圧)'
                else:
                    jp = '両建て清算混在'
            else:
                jp = '清算微小'
            largest = max(largest_long, largest_short)
            big = ''
            if largest >= 1_000_000:
                big = f' 最大${largest/1e6:.1f}M(大口)'
            elif largest >= 100_000:
                big = f' 最大${largest/1e3:.0f}k'
            mats.append(
                f'清算 直近{dur}秒: ロング${long_usd:,.0f} / ショート${short_usd:,.0f} '
                f'({count}件、 {jp}){big}'
            )
    elif liq:
        mats.append('清算 取得失敗')

    # === Order Book ===
    ob = snapshot.get('orderbook') or {}
    if 'error' not in ob:
        imb = ob.get('imbalance', 0)
        best_bid = ob.get('best_bid', 0)
        best_ask = ob.get('best_ask', 0)
        spread = best_ask - best_bid
        if imb >= 0.10:
            jp = '板買い厚め'
        elif imb <= -0.10:
            jp = '板売り厚め'
        else:
            jp = '板バランス'
        mats.append(f'板imbalance {imb:+.2f} ({jp}) spread=${spread:.2f}')
    else:
        mats.append('板 取得失敗')

    return mats


def extract_materials(candles: list[dict], regime: str) -> list[str]:
    """局面に応じた「材料」リスト生成 (LoRA入力用)

    danjer学習データの format に合わせる:
    「【今わたし(danjer)が見ている材料】 - <m1> - <m2> ...」
    """
    if len(candles) < 5:
        return ['データ不足']

    latest = candles[-1]
    close = latest['close']
    high = latest['high']
    low = latest['low']
    volume = latest['volume']

    # 過去24h平均volume
    n = min(24, len(candles))
    avg_volume = sum(c['volume'] for c in candles[-n:]) / n
    volume_ratio = volume / avg_volume if avg_volume > 0 else 1.0

    # 過去 ATR
    atr = _atr(candles, period=14)

    materials = []

    if regime == 'rally':
        materials.append('急騰中')
        if volume_ratio > 1.5:
            materials.append('出来高伴う')
        else:
            materials.append('出来高伴わず')
        materials.append('損切根拠の探索')
    elif regime == 'crash':
        materials.append('暴落中')
        if volume_ratio > 1.5:
            materials.append('出来高急増')
        materials.append('反発取れる背の検討')
    elif regime == 'trend':
        materials.append('トレンド継続')
        change_6h = _price_change_pct(candles, hours=6)
        if change_6h > 0:
            materials.append('上昇継続')
        else:
            materials.append('下降継続')
        materials.append('押し目/戻り高値の確認')
    else:  # range
        materials.append('レンジ相場')
        materials.append('上下限の確認')
        materials.append('ブレイクの根拠待ち')

    return materials


if __name__ == "__main__":
    # 動作確認 (yfinance使う)
    print("=== regime_detector.py 動作確認 ===")
    try:
        from data_source import fetch_btc_ohlcv, get_recent_candles
        df = fetch_btc_ohlcv(period="60d", interval="1h")
        candles = get_recent_candles(df, n=240)  # 10日分
        regime = detect_regime(candles)
        materials = extract_materials(candles, regime)
        print(f"判定: regime={regime}")
        print(f"材料: {materials}")
        print(f"最新close: ${candles[-1]['close']:.2f}")
    except Exception as e:
        print(f"失敗: {type(e).__name__}: {e}")
