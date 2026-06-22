#!/usr/bin/env python3
"""検収パッケージ生成: GPT/Geminiが danjer_bottomup の成果を直接検収できるよう、
実レコード(本文+画像読取+抽出引用)を並べたテキストを生成する。

GPT/Geminiは会議スクレイプ越しにテキストしか読めず、DB/HTMLを開けない。
そこで『元ソース』と『抽出引用』を横並びにし、逐語一致を本人が照合できる形にする。
出力は relay の [[FULL]] マーカー付きで全文がGPT/Geminiに届く。

usage: python3 verify_package.py   # 標準出力にパッケージ本文
"""
import json
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
AI = HERE.parent / "btc_trading_ai.db"
XT = HERE.parent / "x_tweets.db"
TABLE = "danjer_bottomup"


def short(s, n):
    s = (s or "").replace("\n", " ").strip()
    return s if len(s) <= n else s[:n] + "…"


def pick(con, where, n):
    return con.execute(
        f"SELECT tweet_id, extract_json FROM {TABLE} "
        f"WHERE {where} AND extract_json IS NOT NULL "
        f"ORDER BY tweet_id LIMIT {n}").fetchall()


def main():
    con = sqlite3.connect(f"file:{AI}?mode=ro", uri=True)
    xt = sqlite3.connect(f"file:{XT}?mode=ro", uri=True)
    rd_map = {str(r[0]): r[1] for r in con.execute(
        "SELECT tweet_id, reading_json FROM danjer_reading_prod")}
    ft_map = {str(r[0]): (r[1] or "") for r in xt.execute(
        "SELECT tweet_id, full_text FROM tweets")}

    # 層化: 材料豊富 / fundamental / anomaly / leverage / 見送り / 捏造修正済み
    groups = [
        ("材料豊富(technical中心)", pick(con, "extracted=1 AND n_materials>=4", 3)),
        ("fundamental含む", pick(con, "extracted=1 AND extract_json LIKE '%fundamental%'", 2)),
        ("anomaly含む", pick(con, "extracted=1 AND extract_json LIKE '%anomaly%'", 2)),
        ("見送り(雑談/結果のみ)", pick(con, "extracted=0 AND extract_json LIKE '%抽出可能な相場分析%'", 1)
            or pick(con, "extracted=0", 1)),
        ("捏造修正済み(入力実質空→見送り化)",
            pick(con, "extracted=0 AND extract_json LIKE '%入力が実質空%'", 2)),
    ]

    out = []
    out.append("[事務Claude → 3者: 成果物 直接検収パッケージ] [[FULL]]")
    out.append("")
    out.append("GPT/Gemini各位: 自己申告ではなく実データで検収できるよう、danjer_bottomup の")
    out.append("実レコードを『元ソース(本文+画像読取)』と『抽出引用』横並びで提示します。")
    out.append("各材料の citation が 元ソース内に逐語存在するかを直接照合してください。")
    out.append("(※会議リレーは通常600字で切られますが、本発言は[[FULL]]で全文届きます)")
    out.append("")
    idx = 0
    for label, rows in groups:
        for tid, ej in rows:
            idx += 1
            d = json.loads(ej)
            ft = ft_map.get(str(tid), "")
            img = ""
            try:
                rj = json.loads(rd_map.get(str(tid), "{}"))
                for im in (rj.get("images") or []):
                    if isinstance(im, dict):
                        img += " | " + (im.get("reading", "") or "")
            except Exception:
                pass
            out.append(f"━━━ 例{idx} [{label}] tweet {tid} ━━━")
            out.append(f"【元ソース・本文】{short(ft, 220)}")
            if img.strip():
                out.append(f"【元ソース・画像読取】{short(img, 260)}")
            if d.get("extracted"):
                for m in d.get("materials", [])[:4]:
                    out.append(
                        f"  ◦[{m.get('type')}] {short(m.get('what'), 70)} "
                        f"／見方: {short(m.get('how'), 60)}")
                    out.append(f"     引用「{short(m.get('citation'), 110)}」")
                out.append(f"  ◆組み合わせ: {short(d.get('combination'), 130)}")
                if d.get("stance"):
                    out.append(f"  ◆構え: {short(d.get('stance'), 80)}")
            else:
                out.append(f"  → 見送り。理由: {short(d.get('reason_if_false'), 140)}")
            out.append("")

    out.append("# 検収観点")
    out.append("1. 各引用は元ソース(本文/画像読取)に逐語存在するか(捏造でないか)")
    out.append("2. 鉄の指示書準拠: カテゴリ先決めなし・組み合わせ言語化・見送り理由の妥当性")
    out.append("3. 全体統計: 13,635件処理/抽出10,084(74%)/引用付き99.9%/捏造37件は検出し見送り化済")
    out.append("4. これで検収可能か。consensus_candidate判定(true/false/blocked/external_wait)を明示")
    out.append("")
    out.append("<pwa_summary>実レコードを本文+引用の横並びで提示。GPT/Geminiが逐語一致を直接照合できる検収パッケージ。判定求む。</pwa_summary>")
    out.append("[事務Claude-検収パッケージ: BOTTOMUP-VERIFY]")
    text = "\n".join(out)
    sys.stdout.write(text)
    sys.stderr.write(f"\n[len={len(text)}字 / 例{idx}件]\n")


if __name__ == "__main__":
    main()
