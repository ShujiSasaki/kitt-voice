#!/usr/bin/env python3
"""danjer 材料インベントリ + 右側予測精度 (Shuji 2026-06-18 依頼)

ボトムアップ抽出(danjer_bottomup) × 方向(danjer_reading_prod) × 実リターン(unified.jsonl)。

出力3軸 (全て『局面数』=投稿単位の重複排除カウント。ワード出現回数ではない):
  A. 材料カテゴリ別 (technical/fundamental/anomaly/leverage_risk/sentiment/other)
  B. 具体テクニック別 (OI/FR/ダイバ/サイクル/三尊/雲… danjer語彙でキーワード集計)
  C. 組み合わせ別 (1投稿に同居した材料カテゴリの集合)
各軸に『右側予測の精度』= danjerの方向(long/short)を実リターンと突き合わせた
  局面数 / 勝率 / EV / baseline超過 を 1d/7d/30d/90d で付与。

注: returnsは clean horizon(1d/7d/30d/90d)のみ(4h/12h/2d/3dは破損のため除外)。
    neutral方向は『右側予測なし』として精度対象外(局面数には含む)。
"""
import json
import re
import sqlite3
import statistics
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
AI = HERE.parent / "btc_trading_ai.db"
UNI = HERE.parent / "danjer_gaia" / "data" / "danjer_posts_unified.jsonl"
OUT = HERE / "edge_inventory.json"
CLEAN = ["ret_1d", "ret_7d", "ret_30d", "ret_90d"]
PRIMARY = "ret_7d"

# danjer語彙: (表示名, [別名/表記ゆれ]) — 局面に1つでも出れば1カウント
TECHNIQUES = [
    ("OI/建玉", ["OI", "建玉", "Open Interest", "未決済", "オープンインタレスト"]),
    ("FR/資金調達", ["資金調達", "ファンディング", "FR", "Funding"]),
    ("清算/精算", ["清算", "精算", "リクイデーション", "ロスカ"]),
    ("ショートカバー/踏み上げ", ["ショートカバー", "踏み上げ", "踏み"]),
    ("ロング/ショート過多", ["ロング過多", "ショート過多", "ロング偏", "ショート偏", "L/S", "LS比"]),
    ("ダイバージェンス", ["ダイバージェンス", "ダイバ", "ヒドゥン"]),
    ("サイクル理論", ["サイクル"]),
    ("フラクタル", ["フラクタル"]),
    ("エリオット/波", ["エリオット", "推進波", "修正波", "1波", "3波", "5波"]),
    ("三尊/逆三尊", ["三尊", "逆三尊", "ヘッドアンドショルダー"]),
    ("ネックライン", ["ネックライン", "ネック"]),
    ("雲/一目", ["一目", "雲", "ねじれ", "捻じれ"]),
    ("移動平均(SMA/MA)", ["SMA", "移動平均", "MA20", "MA50", "MA100", "MA200", "GMMA", "グランビル", "パーフェクトオーダー"]),
    ("フィボナッチ", ["フィボ", "半値", "0.618", "0.382", "0.5戻"]),
    ("チャネル", ["チャネル"]),
    ("ウェッジ/ペナント/三角", ["ウェッジ", "ペナント", "三角持", "三角保ち", "アセトラ", "ディセトラ"]),
    ("ダイアモンド", ["ダイアモンド", "ダイヤモンド"]),
    ("レンジ/ボックス", ["レンジ", "ボックス", "持ち合い", "保ち合い"]),
    ("ブレイク", ["ブレイク", "ブレイクアウト", "上抜け", "下抜け"]),
    ("サポレジ", ["サポート", "レジスタンス", "サポレジ", "節目"]),
    ("髭/ローソク足", ["髭", "ヒゲ", "たくり", "包み足", "包足", "陽線", "陰線", "坊主"]),
    ("窓/CME窓", ["窓", "CME窓", "窓埋め"]),
    ("MACD", ["MACD"]),
    ("RSI", ["RSI"]),
    ("ボラティリティ", ["ボラ", "IVバンド", "ATR"]),
    ("アノマリー(時期/曜日)", ["アノマリー", "春節", "納税", "月末", "月初", "雇用統計", "SQ", "OP期限", "半減期"]),
    ("ファンダ(マクロ/規制)", ["金融政策", "日銀", "FOMC", "CPI", "消費者物価", "金利", "ETF", "規制", "上海", "メインネット"]),
    ("テザー/ステーブル", ["テザー", "USDT", "USDC", "デペグ", "発行"]),
    ("オーダー板/出来高", ["買い板", "売り板", "板", "出来高", "VPVR", "ヒートマップ", "注文量"]),
    ("オプション/PCR", ["オプション", "PCR", "プット", "コール", "put", "call"]),
    ("Coinbaseプレミア/地域差", ["Coinbaseプレミア", "プレミア", "韓国", "Kimchi"]),
]


def conf_clean_returns():
    ret = {}
    for line in open(UNI, encoding="utf-8"):
        try:
            d = json.loads(line)
        except Exception:
            continue
        r = d.get("returns") or {}
        cl = {h: r[h] for h in CLEAN
              if isinstance(r.get(h), (int, float)) and abs(r[h]) <= 1.0}
        if cl:
            ret[str(d["tweet_id"])] = cl
    return ret


def signal_ret(direction, f):
    if direction == "long":
        return f
    if direction == "short":
        return -f
    return None


def accuracy(posts, ret, dirmap, h):
    """posts(tweet_id list)の 右側予測精度 を horizon h で算出"""
    sig, base = [], []
    for t in posts:
        rr = ret.get(t)
        if not rr or h not in rr:
            continue
        base.append(rr[h])
        s = signal_ret(dirmap.get(t), rr[h])
        if s is not None:
            sig.append(s)
    if not sig:
        return None
    ev = statistics.mean(sig)
    bev = statistics.mean(base) if base else 0
    return {
        "scored_n": len(sig),
        "win_rate": round(sum(1 for x in sig if x > 0) / len(sig) * 100, 1),
        "ev_pct": round(ev * 100, 2),
        "median_pct": round(statistics.median(sig) * 100, 2),
        "baseline_ev_pct": round(bev * 100, 2),
        "excess_pct": round((ev - bev) * 100, 2),
    }


def block(posts, ret, dirmap, label):
    scorable = [t for t in posts if dirmap.get(t) in ("long", "short")]
    d = Counter(dirmap.get(t) for t in posts)
    return {
        "label": label,
        "局面数": len(posts),
        "方向内訳": {"long": d.get("long", 0), "short": d.get("short", 0),
                  "neutral": d.get("neutral", 0)},
        "精度計算可能局面": len(scorable),
        "精度": {h: accuracy(scorable, ret, dirmap, h) for h in CLEAN},
    }


def main():
    ret = conf_clean_returns()
    con = sqlite3.connect(f"file:{AI}?mode=ro", uri=True)
    dirmap = {}
    for tid, rj in con.execute(
            "SELECT tweet_id, reading_json FROM danjer_reading_prod "
            "WHERE reading_json IS NOT NULL"):
        try:
            a = (json.loads(rj).get("danjer_action") or {})
            dirmap[str(tid)] = a.get("direction", "?")
        except Exception:
            pass

    # 各局面の: 材料type集合, テクニックキーワード集合, 全文
    post_types = {}
    post_techs = {}
    rows = con.execute(
        "SELECT tweet_id, extract_json FROM danjer_bottomup "
        "WHERE extracted=1 AND extract_json IS NOT NULL").fetchall()
    for tid, ej in rows:
        tid = str(tid)
        d = json.loads(ej)
        types = set()
        text = (d.get("combination", "") or "") + " " + (d.get("stance", "") or "")
        for m in d.get("materials", []):
            types.add(m.get("type", "other"))
            text += " " + " ".join(str(m.get(k, "")) for k in ("what", "how", "citation"))
        post_types[tid] = types
        techs = set()
        for disp, alii in TECHNIQUES:
            if any(a in text for a in alii):
                techs.add(disp)
        post_techs[tid] = techs

    allposts = list(post_types.keys())

    # A. 材料カテゴリ別
    type_posts = defaultdict(list)
    for t, types in post_types.items():
        for ty in types:
            type_posts[ty].append(t)
    A = [block(ps, ret, dirmap, ty)
         for ty, ps in sorted(type_posts.items(), key=lambda kv: -len(kv[1]))]

    # B. 具体テクニック別
    tech_posts = defaultdict(list)
    for t, techs in post_techs.items():
        for tc in techs:
            tech_posts[tc].append(t)
    B = [block(ps, ret, dirmap, tc)
         for tc, ps in sorted(tech_posts.items(), key=lambda kv: -len(kv[1]))]

    # C. 材料カテゴリ組み合わせ別 (同居集合)
    combo_posts = defaultdict(list)
    for t, types in post_types.items():
        sig = "+".join(sorted(types))
        combo_posts[sig].append(t)
    C = [block(ps, ret, dirmap, sig)
         for sig, ps in sorted(combo_posts.items(), key=lambda kv: -len(kv[1]))
         if len(ps) >= 10]

    rep = {
        "spec": "danjer材料インベントリ+右側予測精度 (2026-06-18)",
        "母集団": {"抽出あり局面": len(allposts),
                "方向long/short": sum(1 for t in allposts if dirmap.get(t) in ("long", "short")),
                "精度計算可能(方向+リターン)": sum(1 for t in allposts if dirmap.get(t) in ("long", "short") and t in ret)},
        "注記": "局面数=投稿単位(重複排除)。neutralは右側予測なしで精度対象外。returnsはclean horizon(1d/7d/30d/90d)のみ。",
        "primary_horizon": PRIMARY,
        "A_材料カテゴリ別": A,
        "B_具体テクニック別": B,
        "C_組み合わせ別": C,
    }
    OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")

    def line(b):
        a = b["精度"].get(PRIMARY)
        acc = (f"勝率{a['win_rate']}% EV{a['ev_pct']:+}% 超過{a['excess_pct']:+}%(n={a['scored_n']})"
               if a else "精度n/a")
        return f"  {b['label'][:30]:30} 局面{b['局面数']:5}  {acc}"

    print(f"=== 母集団 {rep['母集団']} ===")
    print(f"\n=== A. 材料カテゴリ別 (右側予測精度は{PRIMARY}) ===")
    for b in A:
        print(line(b))
    print(f"\n=== B. 具体テクニック別 (局面数降順) ===")
    for b in B:
        print(line(b))
    print(f"\n=== C. 組み合わせ別 (局面10+、上位15) ===")
    for b in C[:15]:
        print(line(b))
    print(f"\nWROTE {OUT}")


if __name__ == "__main__":
    main()
