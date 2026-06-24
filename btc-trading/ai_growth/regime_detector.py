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
