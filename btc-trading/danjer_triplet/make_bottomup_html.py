#!/usr/bin/env python3
"""bottomup_sample.json → iPhone Safari で読める検収用HTML (同サーバ配信)"""
import html
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "bottomup_sample.json"
DEST = (HERE.parent.parent / "meeting_system" / "data" / "attachments"
        / "btc_auto_trade" / "bottomup_sample.html")


def esc(x):
    return html.escape(str(x or ""))


def main():
    data = json.loads(SRC.read_text())
    blocks = []
    n_ext = 0
    for r in data:
        e = r.get("extract") or {}
        ext = bool(e.get("extracted"))
        if ext:
            n_ext += 1
        head = f"{esc(r['tweet_id'])} — {'抽出あり' if ext else '抽出なし'}"
        body = [f"<div class=tw>本文: {esc(r.get('full_text'))}</div>"]
        if not ext:
            body.append(f"<div class=non>抽出なし: {esc(e.get('reason_if_false'))}</div>")
        else:
            for m in e.get("materials", []):
                body.append(
                    "<div class=mat>"
                    f"<span class=tp>{esc(m.get('type'))}</span> "
                    f"<b>{esc(m.get('what'))}</b>"
                    f"<div class=how>どう見た: {esc(m.get('how'))}</div>"
                    f"<div class=cite>引用「{esc(m.get('citation'))}」</div></div>")
            body.append(f"<div class=combo>◆組み合わせ: {esc(e.get('combination'))}</div>")
            if e.get("stance"):
                body.append(f"<div class=stance>◆構え: {esc(e.get('stance'))}</div>")
        blocks.append(
            f"<details {'open' if ext else ''}><summary>{head}</summary>"
            + "".join(body) + "</details>")
    doc = f"""<!doctype html><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>ボトムアップ抽出 検収30件</title><style>
body{{font-family:-apple-system,sans-serif;margin:0;padding:14px;background:#0d1117;color:#e6edf3;font-size:15px;line-height:1.6}}
h1{{font-size:18px}} details{{margin:8px 0;border:1px solid #30363d;border-radius:8px;padding:8px}}
summary{{cursor:pointer;color:#58a6ff;font-weight:bold}}
.tw{{background:#161b22;padding:8px;border-radius:6px;font-size:13px;color:#9bd;margin:6px 0;white-space:pre-wrap}}
.mat{{border-left:3px solid #2f81f7;padding:4px 8px;margin:6px 0;background:#11161d}}
.tp{{background:#1f6feb;color:#fff;font-size:11px;padding:1px 6px;border-radius:4px}}
.how{{font-size:13px;color:#c9d1d9;margin:2px 0}}
.cite{{font-size:12px;color:#8b949e}} .combo{{margin-top:6px;color:#f0c674;font-size:14px}}
.stance{{color:#7ee787;font-size:13px}} .non{{color:#8b949e}}</style>
<h1>danjer ボトムアップ抽出 検収30件</h1>
<p>抽出あり {n_ext}/{len(data)} 件。カテゴリ先決めなし・各材料に本文/画像読取からの引用付き。タップで展開。</p>
{''.join(blocks)}"""
    DEST.parent.mkdir(parents=True, exist_ok=True)
    DEST.write_text(doc, encoding="utf-8")
    print(f"WROTE {DEST} ({len(doc)//1024}KB, 抽出あり{n_ext}/{len(data)})")


if __name__ == "__main__":
    main()
