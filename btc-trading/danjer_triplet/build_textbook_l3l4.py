#!/usr/bin/env python3
"""L3 ボトムアップsetup集 + L4 検証済み実戦ルール集 (₿部屋4層教科書・コスト0)

3者合意の4層のうち、弟子AIが実際に学習・使用する核心(L3+L4)を、既存データ
(danjer_reading_prod + unified.jsonl returns)からローカル生成する。新規API課金なし。

L3 setup = danjer自身の語彙(材料) × 方向 × 相場環境 の創発的組み合わせ。
  固定カテゴリを先に決めず、投稿のthesisに実在する語彙からタグを立てる(ボトムアップ)。
L4 rule  = 各setupに returns(EV/勝率/下方リスク)を紐付け、入る条件/入らない(見送り)
  条件/相対的優位性を数値で言語化。弟子AIの行動指針。

注: returnsは unified.jsonl の正常horizon(1d/7d/30d/90d)のみ使用(4h/12h/2d/3dは破損)。
"""
import json
import sqlite3
import statistics
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
AI_DB = HERE.parent / "btc_trading_ai.db"
UNIFIED = HERE.parent / "danjer_gaia" / "data" / "danjer_posts_unified.jsonl"
OUT_L3 = HERE / "textbook_L3_setups.json"
OUT_L4 = HERE / "textbook_L4_rules.json"
CLEAN_HZ = ["ret_1d", "ret_7d", "ret_30d"]
PRIMARY = "ret_7d"

# danjer自身の語彙(材料タグ)。過度に汎用な語(レンジ/OI単独)は文脈語として残しつつ、
# シグナル性の高い語を材料として扱う。ボトムアップ=投稿に実在する語のみ。
TAGS = [
    "ダイバージェンス", "ダイバ", "ショートカバー", "踏み上げ", "押し目", "戻り売り",
    "三尊", "逆三尊", "ネックライン", "ブレイク", "清算", "精算", "ヒドゥン",
    "サポート", "レジスタンス", "雲", "一目", "フィボ", "ダイアモンド", "ウェッジ",
    "チャネル", "サイクル", "フラクタル", "髭", "たくり足", "包足", "窓",
    "資金調達", "FR", "ボラ",
]
TAG_ALIAS = {"ダイバ": "ダイバージェンス", "精算": "清算", "FR": "資金調達"}


def conf_bucket(c):
    s = str(c).lower()
    return ("high" if "high" in s else "low" if "low" in s
            else "medium" if ("medium" in s or "mid" in s) else "unknown")


def load_returns():
    ret = {}
    for line in open(UNIFIED, encoding="utf-8"):
        try:
            d = json.loads(line)
        except Exception:
            continue
        r = d.get("returns") or {}
        clean = {h: r[h] for h in CLEAN_HZ
                 if isinstance(r.get(h), (int, float)) and abs(r[h]) <= 1.0}
        if clean:
            ret[str(d["tweet_id"])] = clean
    return ret


def extract_tags(text):
    found = set()
    for t in TAGS:
        if t in text:
            found.add(TAG_ALIAS.get(t, t))
    return found


def signal_ret(direction, f):
    if direction == "long":
        return f
    if direction == "short":
        return -f
    return None


def setup_stats(rows, ret, hz):
    """setupに属する投稿群の outcome 統計"""
    out = {}
    for h in hz:
        sig = []
        for r in rows:
            rr = ret.get(r["tweet_id"], {})
            if h not in rr:
                continue
            s = signal_ret(r["direction"], rr[h])
            if s is not None:
                sig.append(s)
        if not sig:
            out[h] = None
            continue
        losses = [x for x in sig if x < 0]
        out[h] = {
            "n": len(sig),
            "ev_pct": round(statistics.mean(sig) * 100, 2),
            "median_pct": round(statistics.median(sig) * 100, 2),
            "win_rate": round(sum(1 for x in sig if x > 0) / len(sig) * 100, 1),
            "avg_loss_pct": round(statistics.mean(losses) * 100, 2) if losses else 0,
        }
    return out


def main():
    ret = load_returns()
    con = sqlite3.connect(f"file:{AI_DB}?mode=ro", uri=True)
    rows = []
    for tid, regime, himg, pro, rj in con.execute(
            "SELECT tweet_id, regime, has_images, routed_to_pro, reading_json "
            "FROM danjer_reading_prod WHERE reading_json IS NOT NULL"):
        d = json.loads(rj)
        a = d.get("danjer_action") or {}
        dirv = a.get("direction", "?")
        if dirv not in ("long", "short"):
            continue  # 方向ありのみsetup対象 (neutralはL2/別途)
        text = str(d.get("danjer_thesis", "")) + " " + str(d.get("market_snapshot", ""))
        rows.append({
            "tweet_id": str(tid), "regime": regime, "direction": dirv,
            "conf": conf_bucket(d.get("confidence")),
            "tags": extract_tags(text),
            "thesis": str(d.get("danjer_thesis", ""))[:160],
        })
    con.close()

    # === L3: setup = (regime × direction × tag) の創発的組み合わせ ===
    buckets = defaultdict(list)
    for r in rows:
        for tg in r["tags"]:
            buckets[(r["regime"], r["direction"], tg)].append(r)

    setups = []
    for (regime, dirv, tag), rs in buckets.items():
        if len(rs) < 15:  # 母数が少なすぎるsetupは統計的に弱い→除外
            continue
        st = setup_stats(rs, ret, CLEAN_HZ)
        prim = st.get(PRIMARY)
        if not prim:
            continue
        setups.append({
            "setup_id": f"{regime}|{dirv}|{tag}",
            "材料": {"相場環境": regime, "方向": dirv, "シグナル": tag},
            "n": len(rs),
            "outcome": st,
            "代表thesis": [x["thesis"] for x in rs[:2]],
        })
    setups.sort(key=lambda s: -(s["outcome"][PRIMARY]["ev_pct"]))

    l3 = {
        "layer": "L3 ボトムアップsetup集 (核心)",
        "method": "danjer語彙×方向×相場環境の創発的組み合わせ。母数15件以上のみ。",
        "primary_horizon": PRIMARY,
        "n_setups": len(setups),
        "setups": setups,
    }
    OUT_L3.write_text(json.dumps(l3, ensure_ascii=False, indent=1), encoding="utf-8")

    # === L4: 実戦ルール (入る/見送り を EV で線引き) ===
    enter = [s for s in setups if s["outcome"][PRIMARY]["ev_pct"] > 0.5]
    avoid = [s for s in setups if s["outcome"][PRIMARY]["ev_pct"] < 0]
    def rule(s, kind):
        o = s["outcome"][PRIMARY]
        return {
            "setup": s["setup_id"], "材料": s["材料"], "n": s["n"],
            "ev_7d_pct": o["ev_pct"], "win_rate": o["win_rate"],
            "avg_loss_pct": o["avg_loss_pct"],
            "判定": kind,
        }
    l4 = {
        "layer": "L4 検証済み実戦ルール集 (弟子AIの行動指針)",
        "基準": f"{PRIMARY}のEVで線引き。入る=EV>+0.5% / 見送り(入らない)=EV<0。",
        "注記": "EV/勝率は過去実績ベース。真のMAE(逆行率)はintra-path不在のため平均損失幅で代用。",
        "入る条件_setup": [rule(s, "入る") for s in enter],
        "入らない_見送り条件_setup": [rule(s, "見送り") for s in avoid],
        "全体方針": {
            "long偏重の地合い依存に注意": "longはbuy&hold超過ほぼ0=地合いβ。αは方向の選別とcrash/short精緻化に存在",
            "range環境は原則見送り": "range×方向当ては地合い以下。休む判断が勝ちに直結",
        },
    }
    OUT_L4.write_text(json.dumps(l4, ensure_ascii=False, indent=1), encoding="utf-8")

    # コンソール要約
    print(f"対象 方向ありsetup候補 {len(rows)}投稿 / 成立setup {len(setups)}個 (母数15+)")
    print(f"\n=== L4 入る条件 (EV>+0.5%/7d, 上位) ===")
    for s in enter[:10]:
        o = s["outcome"][PRIMARY]
        print(f"  {s['setup_id']:34} n={s['n']:4} EV{o['ev_pct']:+5}% 勝率{o['win_rate']}%")
    print(f"\n=== L4 見送り条件 (EV<0/7d, 下位) ===")
    for s in sorted(avoid, key=lambda x: x['outcome'][PRIMARY]['ev_pct'])[:10]:
        o = s["outcome"][PRIMARY]
        print(f"  {s['setup_id']:34} n={s['n']:4} EV{o['ev_pct']:+5}% 勝率{o['win_rate']}%")
    print(f"\nWROTE {OUT_L3.name} ({len(setups)}setup) / {OUT_L4.name} "
          f"(入る{len(enter)}/見送り{len(avoid)})")


if __name__ == "__main__":
    main()
