"""Phase 3-② チャート画像 vision (2026-06-24 14:29 合意 最終段階)

直近 OHLCV から ローソク足チャート画像を 描画 → Gemini Flash で パターン認識。
danjer 言及 TOP30 の パターン系 (三尊/ダイア/ネックライン/レンジ/トレンドライン) を 拾う。

合意の念押し: 重い (画像描画 + Gemini API 5-10秒)、 一段ずつ検収。
費用感: Gemini 2.5 Flash 約$0.0002/判定、 1日3回 で 月 ~¥30。
"""
from __future__ import annotations

import base64
import io
import os
import sys
from pathlib import Path

HERE = Path(__file__).parent


def _load_env_key() -> str:
    """GEMINI_API_KEY を ENV か プロジェクト ルート の .env から取得"""
    k = os.environ.get('GEMINI_API_KEY', '').strip()
    if k:
        return k
    # ルートの .env を 探す (kitt-voice / btc-trading / ai_growth)
    for path in (HERE.parent.parent.parent / '.env', HERE.parent.parent / '.env', HERE.parent / '.env'):
        if path.exists():
            try:
                for line in path.read_text(encoding='utf-8').splitlines():
                    if line.startswith('GEMINI_API_KEY='):
                        return line.split('=', 1)[1].strip()
            except Exception:
                continue
    return ''


def render_btc_chart_png(candles: list[dict], n: int = 100) -> bytes:
    """直近 n本 の ローソク足 + SMA50 + 出来高を 描画 → PNG bytes

    candles: data_source.get_recent_candles() の戻り値
    """
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    use = candles[-n:] if len(candles) > n else candles
    if not use:
        raise ValueError('no candles')

    fig, (ax_p, ax_v) = plt.subplots(
        2, 1, figsize=(10, 6), sharex=True,
        gridspec_kw={'height_ratios': [3, 1]}
    )

    # 値段プロット
    for i, c in enumerate(use):
        body_low = min(c['open'], c['close'])
        body_h = abs(c['close'] - c['open'])
        color = '#26a69a' if c['close'] >= c['open'] else '#ef5350'
        ax_p.add_patch(Rectangle((i - 0.4, body_low), 0.8, body_h, color=color, alpha=0.95))
        ax_p.plot([i, i], [c['low'], c['high']], color=color, linewidth=0.8)
    # SMA50 overlay
    closes = [c['close'] for c in use]
    if len(closes) >= 50:
        sma50 = []
        for i in range(len(closes)):
            window = closes[max(0, i - 49): i + 1]
            sma50.append(sum(window) / len(window))
        ax_p.plot(range(len(closes)), sma50, color='#ffa500', linewidth=1.2, label='SMA50')
    ax_p.set_title(f'BTC/USD recent {len(use)} candles', fontsize=10)
    ax_p.set_xlim(-1, len(use))
    ax_p.grid(True, alpha=0.25)
    ax_p.legend(loc='upper left', fontsize=8)

    # 出来高
    for i, c in enumerate(use):
        color = '#26a69a' if c['close'] >= c['open'] else '#ef5350'
        ax_v.bar(i, c['volume'], color=color, alpha=0.7, width=0.8)
    ax_v.set_xlabel('candle index (latest right)')
    ax_v.grid(True, alpha=0.25)

    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=88)
    plt.close(fig)
    return buf.getvalue()


def analyze_chart_pattern(png_bytes: bytes, timeout: float = 20.0) -> dict:
    """Gemini Flash で チャート画像 → パターン認識

    新 google-genai SDK 使用 (CLAUDE.md メモ: 2.5 Flash の thinkingBudget が
    maxOutputTokens を消費して空応答 → thinking_budget=0 で 解決)。

    出力:
        {'patterns': [str, ...], 'trend_direction': 'up'|'down'|'sideways',
         'summary_jp': str (50字程度), 'raw': str}
    """
    key = _load_env_key()
    if not key:
        return {'error': 'GEMINI_API_KEY not found'}
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return {'error': 'google-genai not installed'}

    prompt = (
        "添付のBTC/USDローソク足チャート(直近100本、 オレンジ線=SMA50、 下段=出来高)を "
        "danjer風 (サイクル/フラクタル/OI意識のトレーダー) の目線で 観察してください。 "
        "以下のJSONフォーマットで 出力 (JSONのみ、 markdown不要):\n"
        '{\n'
        '  "patterns": [観察された形状を 短い日本語で 0-5個 列挙。 '
        '例: "三尊", "逆三尊", "ダブルトップ", "ダイア", "ネックライン", '
        '"レンジ上限テスト", "レンジ下限テスト", "ブレイクアウト", "押し目", "戻り高値"],\n'
        '  "trend_direction": "up" or "down" or "sideways",\n'
        '  "summary_jp": "日本語60字以内で 直近の動きを 1行サマリ"\n'
        '}'
    )

    try:
        client = genai.Client(api_key=key)
        resp = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[
                prompt,
                types.Part.from_bytes(data=png_bytes, mime_type='image/png'),
            ],
            config=types.GenerateContentConfig(
                temperature=0.2,
                max_output_tokens=600,
                response_mime_type='application/json',
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        raw = (resp.text or '').strip()
    except Exception as e:
        return {'error': f'{type(e).__name__}: {e}'}

    import json as _json
    try:
        o = _json.loads(raw)
        return {
            'patterns': o.get('patterns', []) or [],
            'trend_direction': o.get('trend_direction', ''),
            'summary_jp': o.get('summary_jp', ''),
            'raw': raw,
        }
    except Exception:
        return {'error': 'parse_failed', 'raw': raw[:500]}


def fetch_chart_vision_materials(candles: list[dict]) -> dict:
    """runner.py から呼ぶ エントリ — Phase 3-② vision snapshot

    1. 直近100本のチャート画像 描画
    2. Gemini Flash で パターン認識
    3. dict返却 (extract_chart_vision_materials で 言語化)
    """
    try:
        png = render_btc_chart_png(candles, n=100)
        return analyze_chart_pattern(png, timeout=20.0)
    except Exception as e:
        return {'error': f'{type(e).__name__}: {e}'}


if __name__ == "__main__":
    # 単体テスト: data_source から OHLCV取得 → 描画 → Gemini
    from data_source import fetch_btc_ohlcv, get_recent_candles
    df = fetch_btc_ohlcv(period="30d", interval="1h")
    candles = get_recent_candles(df, n=200)
    print(f"candles取得: {len(candles)}本")
    print(f"GEMINI_API_KEY: {'set' if _load_env_key() else 'NOT FOUND'}")
    result = fetch_chart_vision_materials(candles)
    import json as _json
    print(_json.dumps(result, ensure_ascii=False, indent=2)[:1500])
