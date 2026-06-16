#!/usr/bin/env python3
"""プランA 本番処理パイプライン (₿部屋3者合意 2026-06-16)

主処理=gemini-2.5-flash / 難例だけ gemini-2.5-pro へ自動ルート。
入力=danjer本文 + 投稿時点市場データ(leak-safe) + ローカル画像(あれば最大4枚)。
出力=danjer_reading_v1スキーマ を danjer_reading_prod テーブルへ。

usage:
  python3 production_run.py --limit 30 --sample   # 確認バッチ(層化30件)
  python3 production_run.py --all                 # 本番全件 (要明示)
"""
import argparse
import base64
import json
import mimetypes
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_prototype_v2 as v2  # noqa: E402  市場スナップ+母集団分類を再利用
import model_bench as mb         # noqa: E402  PROMPT(確定版)+call_gemini を再利用

MEDIA = HERE.parent / "media" / "smile_danjer"
AI_DB = HERE.parent / "btc_trading_ai.db"
TABLE = "danjer_reading_prod"
FLASH = "gemini-2.5-flash"
PRO = "gemini-2.5-pro"

# 本番プロンプト v2 (₿部屋 3者合意 2026-06-16 の修正5点反映)
# ①画像なし→画像読取は空 ②市場/価格を画像読取に混ぜない ③根拠の出どころを分離
# ④未断定→neutral正規化 ⑤雑談/皮肉は trade_signal=false
PROD_PROMPT = (
    "あなたはBTC相場分析者です。投稿者danjerの1投稿について、本文・添付画像・"
    "投稿時点の市場データを統合し、danjerの相場認識・条件・警戒点・否定条件を"
    "客観的に復元してください。\n\n"
    "【厳格ルール】\n"
    "1. 画像読取(images[].reading)には『画像に視覚的に写っているもの』だけを書く。"
    "市場データや価格などテキスト/数値由来の情報をここに混ぜない。\n"
    "2. 添付画像が0枚のときは images を必ず空配列 [] とし、チャート内容を一切"
    "推測・記述しないこと(捏造厳禁)。\n"
    "3. 各根拠は出どころを分ける: 画像由来→images、市場データ由来→market_snapshot、"
    "本文由来→danjer_thesis。混同しない。\n"
    "4. 読めない数値・潰れた文字・不明指標は unknown と明記(推測しない)。\n"
    "5. 売買助言はしない。danjerの認識の復元に徹する。\n"
    "6. 方向(direction)は long / short / neutral のいずれかに正規化する"
    "(『未断定』『様子見』『watch』等は neutral とする)。\n"
    "7. 相場分析でない雑談・皮肉・宣伝・近況報告は trade_signal=false、"
    "相場認識を含む投稿は trade_signal=true とする。\n\n"
    "出力はJSONのみ。スキーマ:\n"
    "{\n"
    '  "trade_signal": true/false,\n'
    '  "images": [{"id":"", "kind":"chart|meme等", "reading":"視覚要素のみ。'
    'なければこの配列は空"}],\n'
    '  "market_snapshot": "渡された市場データの統合読解(価格/OI/FR等)",\n'
    '  "danjer_thesis": "本文+画像+市場を統合したdanjerの相場認識",\n'
    '  "danjer_action": {"direction":"long|short|neutral", "stance":"", '
    '"explicit_entry":true/false, "lot":null, "leverage":null},\n'
    '  "invalidation": "否定条件",\n'
    '  "confidence": "high|medium|low と理由",\n'
    '  "evidence_provenance": {"from_image":[], "from_text":[], "from_market":[]}\n'
    "}\n"
)


def find_images(tweet_id: str, limit: int = 4):
    """ローカル画像を {tweet_id}_* で探す (最大limit枚、jpg/png/jpeg)"""
    if not MEDIA.exists():
        return []
    out = []
    for p in sorted(MEDIA.glob(f"{tweet_id}_*")):
        if p.suffix.lower() not in (".jpg", ".jpeg", ".png"):
            continue
        data = p.read_bytes()
        if len(data) < 1000:
            continue
        mime = mimetypes.guess_type(p.name)[0] or "image/jpeg"
        out.append((mime, base64.b64encode(data).decode(), p.name))
        if len(out) >= limit:
            break
    return out


def build_user_text(tw, cd, oi, oi24, fr):
    oi_chg = (round((oi["oi_btc"] - oi24["oi_btc"]) / oi24["oi_btc"] * 100, 2)
              if oi and oi24 and oi24["oi_btc"] else None)
    market = {
        "confirmed_daily_candle_date": cd["date"],
        "daily_OHLCV": {"o": cd["o"], "h": cd["h"], "l": cd["l"],
                        "c": cd["c"], "v": cd["v"]},
        "ret5_pct": cd.get("ret5_pct"), "range20_pct": cd.get("range20_pct"),
        "open_interest_btc": oi["oi_btc"] if oi else None,
        "oi_chg_24h_pct": oi_chg,
        "ls_ratio": oi["ls"] if oi else None,
        "funding_rate": fr["fr"] if fr else None,
        "note": "LS比率/清算はローカル未保有の場合null。leak-safe(確定足のみ)。",
    }
    return (f"投稿本文: {tw['text']}\n"
            f"投稿時刻(UTC): {tw['dt_utc'].strftime('%Y-%m-%d %H:%M')}\n"
            f"市場データ: {json.dumps(market, ensure_ascii=False)}")


def call_gemini_prod(model, user_text, imgs3, key):
    """PROD_PROMPT を使う画像対応Gemini呼び出し。
    画像0枚のときはプロンプトに『画像なし』を明示して捏造を防ぐ。
    """
    import ssl as _ssl, urllib.request as _u, json as _j
    prompt = PROD_PROMPT
    if not imgs3:
        prompt += ("\n■この投稿には画像が添付されていません。"
                   "images は必ず [] とし、チャート内容を書かないこと。")
    parts = [{"text": prompt + "\n\n" + user_text}]
    for mime, b64, _ in imgs3:
        parts.append({"inline_data": {"mime_type": mime, "data": b64}})
    gen = ({"maxOutputTokens": mb.MAX_OUT + 2600} if "pro" in model
           else {"maxOutputTokens": mb.MAX_OUT,
                 "thinkingConfig": {"thinkingBudget": 0}})
    payload = {"contents": [{"parts": parts}], "generationConfig": gen}
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent?key={key}")
    ctx = _ssl.create_default_context(cafile=__import__("certifi").where())
    req = _u.Request(url, data=_j.dumps(payload).encode(),
                     headers={"Content-Type": "application/json"}, method="POST")
    with _u.urlopen(req, timeout=120, context=ctx) as r:
        d = _j.loads(r.read().decode())
    cand = (d.get("candidates") or [{}])[0]
    txt = "".join(p.get("text", "")
                  for p in (cand.get("content", {}).get("parts") or []))
    u = d.get("usageMetadata", {})
    return txt, u.get("promptTokenCount", 0), u.get("candidatesTokenCount", 0)


def enforce_rules(parsed, has_images):
    """後処理強制: 画像なし→images空 / 未断定→neutral (プロンプト違反の保険)"""
    if not isinstance(parsed, dict):
        return parsed
    if not has_images:
        parsed["images"] = []  # 捏造を物理的に除去
    a = parsed.get("danjer_action")
    if isinstance(a, dict):
        dv = str(a.get("direction", "")).lower()
        if any(k in dv for k in ("未断定", "様子見", "watch", "unresolved", "neutral")):
            a["direction"] = "neutral"
        elif "long" in dv:
            a["direction"] = "long"
        elif "short" in dv:
            a["direction"] = "short"
    return parsed


def parse_reading(txt):
    t = (txt or "").strip()
    for pre in ("```json", "```"):
        if t.startswith(pre):
            t = t[len(pre):]
    t = t.rstrip("`").strip()
    try:
        return json.loads(t), None
    except Exception as e:
        return None, str(e)[:80]


def is_hard_case(parsed, perr):
    """難例(=pro行き)判定: parse失敗 / 確信度low / 幻覚リスクhigh"""
    if perr or not isinstance(parsed, dict):
        return "parse_fail"
    conf = json.dumps(parsed.get("confidence", ""), ensure_ascii=False).lower()
    if "low" in conf:
        return "confidence_low"
    msc = parsed.get("model_self_check") or {}
    hr = str(msc.get("hallucination_risk", "")).lower() if isinstance(msc, dict) else ""
    if "high" in hr:
        return "halluc_high"
    return None


def ensure_table(con):
    con.execute(f"""CREATE TABLE IF NOT EXISTS {TABLE} (
        tweet_id TEXT PRIMARY KEY,
        posted_at_utc TEXT, regime TEXT, has_images INTEGER,
        model_used TEXT, routed_to_pro INTEGER, route_reason TEXT,
        flash_cost_jpy REAL, pro_cost_jpy REAL,
        reading_json TEXT, raw_output TEXT,
        tokens_in INTEGER, tokens_out INTEGER,
        created_at TEXT DEFAULT (datetime('now')))""")


def cost_jpy(model, tin, tout):
    pin, pout = mb.PRICE.get(model, (0, 0))
    return (tin / 1e6 * pin + tout / 1e6 * pout) * mb.JPY


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--sample", action="store_true",
                    help="層化サンプリング(確認バッチ用)")
    ap.add_argument("--all", action="store_true", help="本番全件")
    ap.add_argument("--retest-noimg", action="store_true",
                    help="確認バッチの画像なし15件を再テスト(捏造ゼロ確認)")
    ap.add_argument("--out", default=str(HERE / "production_run_report.json"))
    args = ap.parse_args()

    env = mb.load_env()
    key = env["GEMINI_API_KEY"]

    tbl, cls, population = v2.load_and_classify()
    candles = v2.load_market()
    oi_rows = v2.load_oi()
    fr_rows = v2.load_fr()
    v2.log(f"母集団={len(population)} / 価格{len(candles)} OI{len(oi_rows)} FR{len(fr_rows)}")

    # スナップ(leak-safe) + 画像有無付与
    enriched = []
    for tw in population:
        cd = v2.snap_daily(candles, tw["dt_utc"])
        if not cd or cd.get("regime") in (None, "warmup"):
            continue
        oi, oi24 = v2.snap_oi(oi_rows, tw["dt_utc"])
        fr = v2.snap_series(fr_rows, tw["dt_utc"]) if fr_rows else None
        tw.update(candle=cd, oi=oi, oi24=oi24, fr=fr)
        enriched.append(tw)

    if args.retest_noimg:
        # 確認バッチで画像なしだったtweet_idを再処理対象に
        rc = sqlite3.connect(AI_DB)
        ids = {r[0] for r in rc.execute(
            f"SELECT tweet_id FROM {TABLE} WHERE has_images=0")}
        rc.close()
        targets = [t for t in enriched if t["tweet_id"] in ids]
        v2.log(f"再テスト対象(画像なし): {len(targets)}件")
    elif args.all:
        targets = enriched
    elif args.sample:
        # 層化: 画像あり/なし × 局面 で散らす
        with_img = [t for t in enriched if find_images(t["tweet_id"], 1)]
        no_img = [t for t in enriched if not find_images(t["tweet_id"], 1)]
        half = args.limit // 2
        def spread(lst, n):
            step = max(1, len(lst) // n)
            return lst[::step][:n]
        targets = spread(with_img, half) + spread(no_img, args.limit - half)
    else:
        targets = enriched[:args.limit]
    v2.log(f"処理対象: {len(targets)}件")

    con = sqlite3.connect(AI_DB)
    ensure_table(con)

    n_pro = 0
    total_flash = total_pro = 0.0
    done = 0
    for tw in targets:
        cd, oi, oi24, fr = tw["candle"], tw["oi"], tw["oi24"], tw["fr"]
        ut = build_user_text(tw, cd, oi, oi24, fr)
        imgs = find_images(tw["tweet_id"])
        imgs_for_api = [(m, b) for m, b, _ in imgs]
        # call_gemini は (mime,b64,_) 3要素を期待 → 合わせる
        imgs3 = [(m, b, "") for m, b in imgs_for_api]
        try:
            txt, tin, tout = call_gemini_prod(FLASH, ut, imgs3, key)
        except Exception as e:
            v2.log(f"  ✗ {tw['tweet_id']} flash失敗: {str(e)[:80]}")
            continue
        fcost = cost_jpy(FLASH, tin, tout)
        total_flash += fcost
        parsed, perr = parse_reading(txt)
        if parsed:
            parsed = enforce_rules(parsed, bool(imgs))
        reason = is_hard_case(parsed, perr)
        model_used, pcost, routed = FLASH, 0.0, 0
        raw_out, final_tin, final_tout = txt, tin, tout
        if reason:
            try:
                ptxt, ptin, ptout = call_gemini_prod(PRO, ut, imgs3, key)
                pparsed, pperr = parse_reading(ptxt)
                if pparsed:
                    pparsed = enforce_rules(pparsed, bool(imgs))
                pcost = cost_jpy(PRO, ptin, ptout)
                total_pro += pcost
                n_pro += 1
                routed = 1
                model_used = PRO
                if pparsed:
                    parsed, raw_out = pparsed, ptxt
                final_tin, final_tout = ptin, ptout
            except Exception as e:
                v2.log(f"  ⚠ {tw['tweet_id']} pro失敗(flash結果保持): {str(e)[:60]}")
        con.execute(
            f"INSERT OR REPLACE INTO {TABLE} (tweet_id, posted_at_utc, regime, "
            "has_images, model_used, routed_to_pro, route_reason, "
            "flash_cost_jpy, pro_cost_jpy, reading_json, raw_output, "
            "tokens_in, tokens_out) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (tw["tweet_id"], tw["dt_utc"].strftime("%Y-%m-%d %H:%M:%S"),
             cd["regime"], 1 if imgs else 0, model_used, routed, reason or "",
             round(fcost, 4), round(pcost, 4),
             json.dumps(parsed, ensure_ascii=False) if parsed else None,
             raw_out[:4000], final_tin, final_tout))
        done += 1
        if done % 10 == 0:
            con.commit()
            v2.log(f"  ...{done}/{len(targets)} pro率{n_pro/done*100:.0f}% "
                   f"累計¥{total_flash+total_pro:.1f}")
    con.commit()
    con.close()

    pro_rate = n_pro / done if done else 0
    total = total_flash + total_pro
    # 全件(13,671)への外挿: 1件あたり実コスト × 母集団
    per_item = total / done if done else 0
    proj_full = per_item * len(population)
    report = {
        "mode": "all" if args.all else ("sample_batch" if args.sample else "head"),
        "processed": done, "pro_routed": n_pro,
        "pro_rate_pct": round(pro_rate * 100, 1),
        "cost_jpy": {"flash": round(total_flash, 1), "pro": round(total_pro, 1),
                     "total": round(total, 1), "per_item": round(per_item, 3)},
        "population": len(population),
        "projected_full_jpy": round(proj_full, 0),
        "table": TABLE,
    }
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1),
                              encoding="utf-8")
    v2.log(f"\n=== 完了 {done}件 / pro率{pro_rate*100:.1f}% / "
           f"実費¥{total:.1f} (flash¥{total_flash:.1f}+pro¥{total_pro:.1f}) ===")
    v2.log(f"全件{len(population)}換算: 約¥{proj_full:,.0f}")
    v2.log(f"WROTE {args.out}")


if __name__ == "__main__":
    main()
