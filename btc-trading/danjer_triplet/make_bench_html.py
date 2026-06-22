#!/usr/bin/env python3
"""model_bench_result.json → iPhone Safariで読める生データHTML (2026-06-15 Shuji要望)

meeting_systemサーバの ₿部屋 attachments に出力 → 同一オリジンなのでPWAの
Basic認証が再利用され、URLを開くだけで全モデルの生出力を読める。
"""
import html
import json
from pathlib import Path

HERE = Path(__file__).parent
SRC = HERE / "model_bench_result.json"
DEST_DIR = (HERE.parent.parent / "meeting_system" / "data" / "attachments"
            / "btc_auto_trade")
DEST = DEST_DIR / "model_bench.html"


def esc(x):
    return html.escape(str(x))


def main():
    r = json.loads(SRC.read_text())
    ref = r["reference"]
    rows = []
    for res in r["results"]:
        if res.get("ok"):
            rows.append(
                f"<tr><td>{esc(res['model'])}</td>"
                f"<td>{res['latency_sec']}s</td>"
                f"<td>¥{res['cost_jpy']}</td>"
                f"<td>{res['tokens_in']}/{res['tokens_out']}</td></tr>")
        else:
            rows.append(
                f"<tr><td>{esc(res['model'])}</td>"
                f"<td colspan=3 class=err>FAIL: {esc(res.get('error',''))[:80]}</td></tr>")

    blocks = []
    for res in r["results"]:
        if not res.get("ok"):
            continue
        out = res["output"]
        # JSONなら整形、ダメなら生
        body = out
        t = out.strip()
        for pre in ("```json", "```"):
            if t.startswith(pre):
                t = t[len(pre):]
        t = t.rstrip("`").strip()
        try:
            body = json.dumps(json.loads(t), ensure_ascii=False, indent=2)
        except Exception:
            body = out
        blocks.append(
            f"<details><summary>{esc(res['model'])} "
            f"({res['latency_sec']}s / ¥{res['cost_jpy']})</summary>"
            f"<pre>{esc(body)}</pre></details>")

    inp = r["input_summary"]
    doc = f"""<!doctype html><html lang=ja><head>
<meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>モデルベンチ生データ</title>
<style>
body{{font-family:-apple-system,sans-serif;margin:0;padding:14px;
background:#0d1117;color:#e6edf3;font-size:15px;line-height:1.6}}
h1{{font-size:18px}} h2{{font-size:15px;color:#58a6ff;margin-top:22px}}
table{{border-collapse:collapse;width:100%;font-size:13px;margin:8px 0}}
td,th{{border:1px solid #30363d;padding:6px 8px;text-align:left}}
th{{background:#161b22}} .err{{color:#f85149}}
pre{{white-space:pre-wrap;word-break:break-word;background:#161b22;
padding:10px;border-radius:8px;font-size:12px;overflow-x:auto}}
details{{margin:8px 0;border:1px solid #30363d;border-radius:8px;padding:8px}}
summary{{cursor:pointer;font-weight:bold;color:#58a6ff}}
.ref{{background:#161b22;padding:10px;border-radius:8px;font-size:13px}}
</style></head><body>
<h1>🤖 全モデル実機ベンチ 生データ</h1>
<p>投稿 {esc(r['tweet_id'])} / 画像3枚({inp['images_kb']}KB) / 推定合計 ¥{r['total_cost_jpy_est']}</p>

<h2>■ 入力した投稿本文</h2>
<div class=ref>{esc(inp['text'])}</div>

<h2>■ 市場データ</h2>
<pre>{esc(json.dumps(inp['market'], ensure_ascii=False, indent=2))}</pre>

<h2>■ 正解リファレンス (発言Claudeが実画像読解)</h2>
<div class=ref>
<b>thesis:</b> {esc(ref['thesis'])}<br><br>
<b>action:</b> {esc(json.dumps(ref['action'], ensure_ascii=False))}<br>
<b>confidence:</b> {esc(ref['confidence'])}
</div>

<h2>■ コスト/速度一覧</h2>
<table><tr><th>モデル</th><th>速度</th><th>1件¥</th><th>in/out tok</th></tr>
{''.join(rows)}</table>

<h2>■ 各モデルの生出力 (タップで展開)</h2>
{''.join(blocks)}
</body></html>"""
    DEST_DIR.mkdir(parents=True, exist_ok=True)
    DEST.write_text(doc, encoding="utf-8")
    print(f"WROTE {DEST} ({len(doc)//1024}KB)")
    print("URL: https://100.70.20.113:8765/api/rooms/btc_auto_trade/"
          "attachments/model_bench.html")


if __name__ == "__main__":
    main()
