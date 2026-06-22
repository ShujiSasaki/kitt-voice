#!/usr/bin/env python3
"""完全ボトムアップ抽出 (₿部屋 鉄の指示書 2026-06-17・コスト0は不可=AI再読)

Shujiの意図: 先に抽出カテゴリを決めず、全投稿を読み直して『何の材料(テクニカル/
ファンダ/アノマリー/レバ)を・どう・どの組み合わせで見ていたか』を各投稿から
引用付きで全抽出する。

鉄の指示(会議合意・禁止/必須):
- 禁止: 先にカテゴリ/setup名を決める / 既存ラベルや語彙で機械分類 / EV計算 /
        足切り / 代表例だけ提出
- 必須: 1投稿1レコード(抽出ゼロも理由を記録) / 各材料に本文or画像読取からの
        verbatim引用(使い回し禁止の証拠) / danjer自身の枠組みで素のまま

引用元(課金節約のため既存資産を使用): 本文(x_tweets) + 既存画像読取(reading_prod,
支払済) + market_snapshot。画像は再送しない=テキスト処理で安価。

usage: python3 bottomup_extract.py --limit 30 --sample   # 検収用
       python3 bottomup_extract.py --all                 # 本番(要GO)
"""
import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import model_bench as mb  # load_env / PRICE / JPY

AI_DB = HERE.parent / "btc_trading_ai.db"
XT_DB = HERE.parent / "x_tweets.db"
TABLE = "danjer_bottomup"
OUT = HERE / "bottomup_sample.json"
FLASH = "gemini-2.5-flash"

IRON_PROMPT = (
    "あなたはトレーダーdanjerの投稿を1件ずつ精読し、彼が相場をどう読んでいたかを"
    "『素のまま』抽出する記録係です。先入観のカテゴリ分けをせず、この投稿に実際に"
    "書かれている内容だけから抽出します。\n\n"
    "【鉄の規則】\n"
    "1. 先にカテゴリやセットアップ名を決めない。danjerが実際に使った材料を、彼の"
    "言葉のまま拾う。\n"
    "2. 各『材料』について、それが本文または画像読取のどこに書かれているかを"
    "verbatim(原文そのまま)で引用する。引用できないものは書かない(捏造禁止)。\n"
    "3. テクニカル/ファンダ/アノマリー/レバ・資金管理 等の区分は、danjerの記述から"
    "自然に当てはまるものを後から付けるだけ。無理に枠に入れない。該当しなければ"
    "type=other。\n"
    "4. 材料が複数あれば、それらが『どう組み合わさって』danjerの判断に至ったかを"
    "combination に書く(組み合わせ=核心)。\n"
    "5. 相場分析でない投稿(雑談/宣伝/挨拶/結果報告のみ)は extracted=false とし、"
    "reason に理由を一言。ただし結果報告でも手法や材料の言及があれば抽出する。\n"
    "6. 売買助言や将来予測はしない。danjerが書いたことの復元に徹する。\n\n"
    "出力はJSONのみ:\n"
    "{\n"
    '  "extracted": true/false,\n'
    '  "reason_if_false": "抽出ゼロの理由(falseのとき)",\n'
    '  "materials": [\n'
    '    {"type":"technical|fundamental|anomaly|leverage_risk|sentiment|other",\n'
    '     "what":"danjerが見ていた材料(彼の言葉で具体的に)",\n'
    '     "how":"それをどう解釈/評価していたか",\n'
    '     "citation":"本文or画像読取からの該当原文(verbatim)"}\n'
    "  ],\n"
    '  "combination":"材料がどう組み合わさって判断に至ったか(単一材料ならその旨)",\n'
    '  "stance":"danjerの結論的な構え(あれば。例:押し目買い狙い/様子見/利確報告)"\n'
    "}\n"
)


def ensure_table(con):
    con.execute(f"""CREATE TABLE IF NOT EXISTS {TABLE} (
        tweet_id TEXT PRIMARY KEY, posted_at_utc TEXT, regime TEXT,
        extracted INTEGER, n_materials INTEGER,
        extract_json TEXT, raw_output TEXT,
        cost_jpy REAL, created_at TEXT DEFAULT (datetime('now')))""")


def call_text(model, prompt, user, key):
    import ssl, urllib.request, certifi
    ctx = ssl.create_default_context(cafile=certifi.where())
    payload = {"contents": [{"parts": [{"text": prompt + "\n\n" + user}]}],
               "generationConfig": {"maxOutputTokens": 2000,
                                    "thinkingConfig": {"thinkingBudget": 0}}}
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent?key={key}")
    for attempt in range(5):
        try:
            req = urllib.request.Request(
                url, data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=120, context=ctx) as r:
                d = json.loads(r.read().decode())
            break
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 503) and attempt < 4:
                time.sleep(min(2 ** attempt * 3, 40))
                continue
            raise
    cand = (d.get("candidates") or [{}])[0]
    txt = "".join(p.get("text", "")
                  for p in (cand.get("content", {}).get("parts") or []))
    u = d.get("usageMetadata", {})
    return txt, u.get("promptTokenCount", 0), u.get("candidatesTokenCount", 0)


def parse(txt):
    t = txt.strip()
    for p in ("```json", "```"):
        if t.startswith(p):
            t = t[len(p):]
    t = t.rstrip("`").strip()
    try:
        return json.loads(t)
    except Exception:
        return None


def build_user(full_text, image_reading, market):
    imgtxt = " / ".join(
        (im.get("reading", "") if isinstance(im, dict) else str(im))[:400]
        for im in (image_reading or [])) or "(画像なし)"
    return (f"【投稿本文】\n{full_text}\n\n"
            f"【画像読取(既存・引用元)】\n{imgtxt}\n\n"
            f"【投稿時点の市場データ】\n{str(market)[:400]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--sample", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    env = mb.load_env()
    key = env["GEMINI_API_KEY"]

    con = sqlite3.connect(AI_DB)
    ensure_table(con)
    xt = sqlite3.connect(f"file:{XT_DB}?mode=ro", uri=True)

    rows = con.execute(
        "SELECT tweet_id, posted_at_utc, regime, has_images, reading_json "
        "FROM danjer_reading_prod WHERE reading_json IS NOT NULL "
        "ORDER BY posted_at_utc").fetchall()
    if args.all:
        done = {r[0] for r in con.execute(f"SELECT tweet_id FROM {TABLE}")}
        targets = [r for r in rows if r[0] not in done]
    elif args.sample:
        # 多様性: 画像あり/なし×局面で散らした30件
        wi = [r for r in rows if r[3]]
        ni = [r for r in rows if not r[3]]
        def sp(l, n):
            s = max(1, len(l) // n)
            return l[::s][:n]
        targets = sp(wi, args.limit // 2) + sp(ni, args.limit - args.limit // 2)
    else:
        targets = rows[:args.limit]

    print(f"対象 {len(targets)}件 (引用元=本文+既存画像読取+市場、テキスト処理)")
    # 本文を事前にまとめて取得 (sqliteはスレッド間共有を避けるためメインで先読み)
    text_map = {}
    for tid, _, _, _, _ in targets:
        t = xt.execute("SELECT full_text FROM tweets WHERE tweet_id=?",
                       (str(tid),)).fetchone()
        text_map[str(tid)] = (t[0] if t else "") or ""

    def worker(row):
        tid, posted, regime, himg, rj = row
        d = json.loads(rj)
        full_text = text_map.get(str(tid), "")
        user = build_user(full_text, d.get("images"), d.get("market_snapshot"))
        try:
            txt, tin, tout = call_text(FLASH, IRON_PROMPT, user, key)
        except Exception as e:
            return {"tweet_id": str(tid), "error": str(e)[:80]}
        cost = (tin / 1e6 * mb.PRICE[FLASH][0]
                + tout / 1e6 * mb.PRICE[FLASH][1]) * mb.JPY
        p = parse(txt)
        return {"tweet_id": str(tid), "posted": posted, "regime": regime,
                "extracted": 1 if (isinstance(p, dict) and p.get("extracted")) else 0,
                "nmat": len(p.get("materials", [])) if isinstance(p, dict) else 0,
                "parsed": p, "raw": txt[:4000], "cost": round(cost, 4),
                "full_text": full_text[:200]}

    from concurrent.futures import ThreadPoolExecutor, as_completed
    results = []
    total = 0.0
    done = errs = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(worker, r) for r in targets]
        for fut in as_completed(futs):
            r = fut.result()
            if r.get("error"):
                errs += 1
                continue
            total += r["cost"]
            con.execute(
                f"INSERT OR REPLACE INTO {TABLE} (tweet_id,posted_at_utc,regime,"
                "extracted,n_materials,extract_json,raw_output,cost_jpy) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (r["tweet_id"], r["posted"], r["regime"], r["extracted"],
                 r["nmat"], json.dumps(r["parsed"], ensure_ascii=False)
                 if r["parsed"] else None, r["raw"], r["cost"]))
            results.append({"tweet_id": r["tweet_id"],
                            "full_text": r["full_text"], "extract": r["parsed"]})
            done += 1
            if done % 50 == 0:
                con.commit()
                el = time.time() - t0
                rate = done / el * 60 if el else 0
                eta = (len(targets) - done) / (rate / 60) / 60 if rate else 0
                print(f"  ...{done}/{len(targets)} err{errs} ¥{total:.0f} "
                      f"{rate:.0f}件/分 ETA{eta:.0f}分", flush=True)
    con.commit()
    OUT.write_text(json.dumps(results[:200], ensure_ascii=False, indent=1),
                   encoding="utf-8")
    con.close(); xt.close()
    per = total / done if done else 0
    print(f"\n=== 完了 {done}件 (err{errs}) / 実費¥{total:.1f} / "
          f"全件換算 約¥{per*13671:,.0f} ===")
    print(f"WROTE {OUT}")


if __name__ == "__main__":
    main()
