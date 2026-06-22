#!/usr/bin/env python3
"""9モデル実機ベンチ (₿部屋発注 / Shuji許可A 2026-06-13)

同一入力 (danjer 3枚画像投稿 + 本文 + 市場データ + 同一プロンプト) を全モデルへ
投げ、出力/入出力トークン/レイテンシ/費用を実測。正解リファレンスと突き合わせる。

対象: OpenAI(gpt-4.1-nano/mini/4.1) + Gemini(2.5 flash-lite/flash/pro)
      + Anthropic(haiku-4.5/sonnet-4.6)。「二重チェック」は高精度2モデルの合成
      なので追加API呼び出しなし (sonnet+pro出力を後段で統合判定)。

キーは .env から読む (gitignore済)。max_tokens抑制で費用最小化。
"""
import base64
import json
import mimetypes
import os
import ssl
import time
import urllib.request
from pathlib import Path

import certifi

BASE = Path(__file__).resolve().parent.parent
ENV = BASE.parent / ".env"
SAMPLE = BASE / "danjer_sample_001_1610281077565980673.json"
MEDIA = BASE / "media" / "smile_danjer"
OUT = Path(__file__).parent / "model_bench_result.json"
SSL_CTX = ssl.create_default_context(cafile=certifi.where())
MAX_OUT = 3000  # danjer_reading_v1スキーマは冗長なため余裕を持たせJSON切れ防止


def load_env():
    env = {}
    for line in ENV.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"')
    return env


# 価格表 (USD / 1M tokens, 2026-06 概算 — 費用は推定)
PRICE = {
    "gpt-4.1-nano":          (0.10, 0.40),
    "gpt-4.1-mini":          (0.40, 1.60),
    "gpt-4.1":               (2.00, 8.00),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.5-flash":      (0.30, 2.50),
    "gemini-2.5-pro":        (1.25, 10.00),
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    "claude-sonnet-4-6":     (3.00, 15.00),
}
JPY = 155.0

# ₿部屋3者true×2巡で確定 (2026-06-13 20:40)。全モデル完全同一。
PROMPT = (
    "あなたはBTC相場分析者です。\n"
    "提示された「投稿本文」「添付画像3枚」「投稿時点の市場データ」の3つを統合し、"
    "投稿者danjerが発している相場認識・条件・警戒点・否定条件を漏れなく客観的に"
    "復元してください。\n\n"
    "【厳格な解析ルール】\n"
    "1. 単一要素(本文のみ/画像のみ/市場データのみ)で結論を出さず、3者を必ず"
    "クロスチェック(突合)すること。\n"
    "2. 添付画像3枚は、チャートのインジケーター・テクニカル・ライン・価格帯・時間足・"
    "OI・FR・出来高・清算マップ・矢印・囲み・注釈など、視覚的に認識できる数値/要素を可能な"
    "限り具体的に書き出すこと。文字が潰れて読めない/データが無い場合は推測せず"
    "「unknown」と明記すること(視覚認識限界の測定のため)。\n"
    "3. 投稿者が想定する目線の否定条件(どうなったらシナリオが崩れるか)を必ず抽出。\n"
    "4. 画像や市場データに無い情報を作らない(幻覚禁止)。\n"
    "5. 自身の売買推奨や主観的予想は含めず、投稿者の相場認識の復元に徹する。\n\n"
    "出力はJSONのみ (前後に文章を付けない)。次の danjer_reading_v1 スキーマに従う:\n"
    "{\n"
    '  "images": [{"id":"画像ファイル名", "kind":"chart|meme等", '
    '"reading":"視認要素を具体的に。読めない所はunknown"}],  // 3枚分\n'
    '  "market_snapshot": "渡された市場データの統合読解",\n'
    '  "fundamental_context": "ファンダ背景(本文/市場から復元、無ければ空)",\n'
    '  "anomaly_context": "アノマリー/特殊状況(無ければ空)",\n'
    '  "danjer_thesis": "danjerの相場認識の要約",\n'
    '  "danjer_action": {"direction":"long|short|neutral|未断定", '
    '"stance":"スタンス説明", "explicit_entry":true/false, '
    '"lot":null, "leverage":null},\n'
    '  "invalidation": "否定条件(シナリオが崩れる条件)",\n'
    '  "confidence": "high|medium|low と理由"\n'
    "}\n"
)


def build_user_text(sample):
    ms = sample["market_snapshot"]
    daily = ms.get("daily", {})
    return (
        f"【本文】\n{sample['text']}\n\n"
        f"【投稿時刻(JST)】{sample['posted_at_jst']}\n"
        f"【市場データ(確定足 {ms.get('confirmed_daily_candle_date')})】\n"
        f"日足 O:{daily.get('open')} H:{daily.get('high')} L:{daily.get('low')} "
        f"C:{daily.get('close')} V:{daily.get('volume')}\n"
        f"投稿時点概算価格: {ms.get('price_at_post_time_approx')}\n"
        f"その他: {json.dumps({k: v for k, v in ms.items() if k not in ('daily',)}, ensure_ascii=False)}"
    )


def load_images():
    imgs = []
    for fn in ("1610281077565980673_1506.jpg",
               "1610281077565980673_1507.jpg",
               "1610281077565980673_1508.png"):
        p = MEDIA / fn
        data = p.read_bytes()
        mime = mimetypes.guess_type(fn)[0] or "image/jpeg"
        imgs.append((mime, base64.b64encode(data).decode(), data))
    return imgs


def post_json(url, payload, headers, timeout=120):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as r:
        return json.loads(r.read().decode())


# ---------- vendor別 呼び出し ----------
def call_openai(model, user_text, imgs, key):
    content = [{"type": "text", "text": PROMPT + "\n\n" + user_text}]
    for mime, b64, _ in imgs:
        content.append({"type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{b64}"}})
    payload = {"model": model, "max_tokens": MAX_OUT,
               "messages": [{"role": "user", "content": content}]}
    j = post_json("https://api.openai.com/v1/chat/completions", payload,
                  {"Authorization": f"Bearer {key}",
                   "Content-Type": "application/json"})
    txt = j["choices"][0]["message"]["content"]
    u = j.get("usage", {})
    return txt, u.get("prompt_tokens", 0), u.get("completion_tokens", 0)


def call_gemini(model, user_text, imgs, key):
    parts = [{"text": PROMPT + "\n\n" + user_text}]
    for mime, b64, _ in imgs:
        parts.append({"inline_data": {"mime_type": mime, "data": b64}})
    # 2.5 Proは思考オフ(thinkingBudget=0)非対応で400になる→flash系のみ抑制。
    # Proは思考でトークンを消費するため出力上限を広げJSON切れを防ぐ
    if "pro" in model:
        gen = {"maxOutputTokens": MAX_OUT + 2600}
    else:
        gen = {"maxOutputTokens": MAX_OUT, "thinkingConfig": {"thinkingBudget": 0}}
    payload = {"contents": [{"parts": parts}], "generationConfig": gen}
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent?key={key}")
    j = post_json(url, payload, {"Content-Type": "application/json"})
    cand = (j.get("candidates") or [{}])[0]
    txt = "".join(p.get("text", "")
                  for p in (cand.get("content", {}).get("parts") or []))
    u = j.get("usageMetadata", {})
    return txt, u.get("promptTokenCount", 0), u.get("candidatesTokenCount", 0)


def call_anthropic(model, user_text, imgs, key):
    content = [{"type": "text", "text": PROMPT + "\n\n" + user_text}]
    for mime, b64, _ in imgs:
        content.append({"type": "image", "source": {
            "type": "base64", "media_type": mime, "data": b64}})
    payload = {"model": model, "max_tokens": MAX_OUT,
               "messages": [{"role": "user", "content": content}]}
    j = post_json("https://api.anthropic.com/v1/messages", payload,
                  {"x-api-key": key, "anthropic-version": "2023-06-01",
                   "Content-Type": "application/json"})
    txt = "".join(b.get("text", "") for b in j.get("content", []))
    u = j.get("usage", {})
    return txt, u.get("input_tokens", 0), u.get("output_tokens", 0)


MODELS = [
    ("openai", "gpt-4.1-nano"),
    ("openai", "gpt-4.1-mini"),
    ("openai", "gpt-4.1"),
    ("gemini", "gemini-2.5-flash-lite"),
    ("gemini", "gemini-2.5-flash"),
    ("gemini", "gemini-2.5-pro"),
    ("anthropic", "claude-haiku-4-5-20251001"),
    ("anthropic", "claude-sonnet-4-6"),
]
CALLERS = {"openai": call_openai, "gemini": call_gemini,
           "anthropic": call_anthropic}
KEY_ENV = {"openai": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY",
           "anthropic": "ANTHROPIC_API_KEY"}


def main():
    env = load_env()
    sample = json.loads(SAMPLE.read_text())
    user_text = build_user_text(sample)
    imgs = load_images()
    img_kb = sum(len(d) for _, _, d in imgs) // 1024
    print(f"入力: 投稿1610281077565980673 本文{len(sample['text'])}字 "
          f"+ 画像3枚({img_kb}KB)")
    reference = {
        "thesis": sample["danjer_thesis"],
        "action": sample["danjer_action"],
        "confidence": sample["confidence"],
        "image_reading_ref": [im["reading"] for im in sample["images"]],
    }

    results = []
    total_cost_jpy = 0.0
    for vendor, model in MODELS:
        key = env.get(KEY_ENV[vendor])
        if not key:
            print(f"  ✗ {model}: キー無し スキップ")
            continue
        t0 = time.time()
        try:
            txt, tin, tout = CALLERS[vendor](model, user_text, imgs, key)
            dt = time.time() - t0
            pin, pout = PRICE.get(model, (0, 0))
            cost_usd = tin / 1e6 * pin + tout / 1e6 * pout
            cost_jpy = cost_usd * JPY
            total_cost_jpy += cost_jpy
            results.append({
                "vendor": vendor, "model": model, "ok": True,
                "latency_sec": round(dt, 1),
                "tokens_in": tin, "tokens_out": tout,
                "cost_jpy": round(cost_jpy, 3),
                "output": txt,
            })
            print(f"  ✓ {model}: {dt:.1f}s in{tin}/out{tout} "
                  f"¥{cost_jpy:.2f}")
        except Exception as e:
            results.append({"vendor": vendor, "model": model,
                            "ok": False, "error": str(e)[:300]})
            print(f"  ✗ {model}: {str(e)[:160]}")

    report = {
        "tweet_id": sample["tweet_id"],
        "input_summary": {"text": sample["text"], "images_kb": img_kb,
                          "market": sample["market_snapshot"]},
        "reference": reference,
        "results": results,
        "total_cost_jpy_est": round(total_cost_jpy, 2),
        "note": ("費用は公開価格ベース推定。1件あたりの実測。全件換算は"
                 "母集団件数×この値で概算可能"),
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"\n合計推定費用: ¥{total_cost_jpy:.2f}")
    print(f"WROTE {OUT}")


if __name__ == "__main__":
    main()
