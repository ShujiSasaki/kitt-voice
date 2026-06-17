#!/usr/bin/env python3
"""Step0 完全版 エッジ定量化 (₿部屋3者合意仕様・コスト0)

合意仕様を満たす: danjer_reading_prod × unified.jsonl returns。
集計軸= direction / trade_signal / confidence / market_regime / Pro有無 / 画像有無。
指標= 件数 / 平均 / 中央値 / 勝率 / EV / 損失率(下方) / baseline超過。
問い= long超過? short下落局面優位? neutral=機会損失orDD回避? trade_signal=false除外でEV改善? confidence high当たる? regime別。

注意: unified.jsonlのreturnsはret_4h/12h/2d/3dが破損(±100%超の異常値25-78%)。
→ 正常な ret_1d/7d/30d/90d のみ使用。破損horizonはreportに明記してスキップ。
逆行率: 終値リターンしか無く intra-path 不在のため真のMAEは出せない →
        『損失率(signal_return<0の割合)』と『平均損失幅』を代理指標として提示。
"""
import json
import sqlite3
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
AI_DB = HERE.parent / "btc_trading_ai.db"
UNIFIED = HERE.parent / "danjer_gaia" / "data" / "danjer_posts_unified.jsonl"
OUT = HERE / "edge_report_v2.json"

CLEAN_HZ = ["ret_1d", "ret_7d", "ret_30d", "ret_90d"]
CORRUPT_HZ = ["ret_4h", "ret_12h", "ret_2d", "ret_3d"]


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
        # 破損horizon除外 + |x|>1の異常値も個別に弾く
        clean = {}
        for h in CLEAN_HZ:
            v = r.get(h)
            if isinstance(v, (int, float)) and abs(v) <= 1.0:
                clean[h] = v
        if clean:
            ret[str(d["tweet_id"])] = clean
    return ret


def load_signals():
    con = sqlite3.connect(f"file:{AI_DB}?mode=ro", uri=True)
    rows = con.execute(
        "SELECT tweet_id, regime, has_images, routed_to_pro, reading_json "
        "FROM danjer_reading_prod WHERE reading_json IS NOT NULL").fetchall()
    con.close()
    out = []
    for tid, regime, himg, pro, rj in rows:
        d = json.loads(rj)
        a = d.get("danjer_action") or {}
        out.append({
            "tweet_id": str(tid), "regime": regime,
            "has_images": int(himg), "pro": int(pro),
            "direction": a.get("direction", "?"),
            "conf": conf_bucket(d.get("confidence")),
            "trade_signal": bool(d.get("trade_signal")),
        })
    return out


def signal_ret(direction, f):
    if direction == "long":
        return f
    if direction == "short":
        return -f
    return None  # neutral=ポジション無し


def stats(subset, ret, h):
    sig, base = [], []
    for r in subset:
        rr = ret.get(r["tweet_id"])
        if not rr or h not in rr:
            continue
        f = rr[h]
        base.append(f)
        s = signal_ret(r["direction"], f)
        if s is not None:
            sig.append(s)
    if not sig:
        return None
    losses = [x for x in sig if x < 0]
    ev = statistics.mean(sig)
    base_ev = statistics.mean(base) if base else 0
    return {
        "n": len(sig),
        "win_rate": round(sum(1 for x in sig if x > 0) / len(sig) * 100, 1),
        "ev_pct": round(ev * 100, 2),
        "median_pct": round(statistics.median(sig) * 100, 2),
        "loss_rate": round(len(losses) / len(sig) * 100, 1),
        "avg_loss_pct": round(statistics.mean(losses) * 100, 2) if losses else 0,
        "baseline_ev_pct": round(base_ev * 100, 2),
        "excess_ev_pct": round((ev - base_ev) * 100, 2),
    }


def neutral_dd_stats(subset, ret, h):
    """neutral投稿: もしロングしてたら(=機会損失)のreturnと、回避できたDDを見る"""
    rets = [ret[r["tweet_id"]][h] for r in subset
            if r["direction"] == "neutral" and ret.get(r["tweet_id"], {}).get(h) is not None]
    if not rets:
        return None
    return {"n": len(rets),
            "if_long_ev_pct": round(statistics.mean(rets) * 100, 2),
            "downside_avoided_pct": round(
                statistics.mean([x for x in rets if x < 0]) * 100, 2)
            if any(x < 0 for x in rets) else 0,
            "up_share": round(sum(1 for x in rets if x > 0) / len(rets) * 100, 1)}


def main():
    ret = load_returns()
    sigs = load_signals()
    matched = [s for s in sigs if s["tweet_id"] in ret]
    sig_true = [s for s in matched if s["trade_signal"]]

    rep = {
        "spec": "Step0完全版 (3者合意仕様)",
        "data_quality_note": {
            "returns_source": "danjer_posts_unified.jsonl",
            "clean_horizons": CLEAN_HZ,
            "corrupt_horizons_excluded": CORRUPT_HZ,
            "corrupt_reason": "ret_4h/12h/2d/3dは±100%超の異常値が25-78%混入(計算バグ)。EV信頼不可のため除外。",
            "mae_note": "終値リターンのみでintra-path不在→真のMAE不可。損失率+平均損失幅を代理指標とした。",
        },
        "matched": len(matched), "trade_signal_true": len(sig_true),
        "horizons": CLEAN_HZ,
    }

    # 1) 全シグナル(trade_signal=true) のエッジ vs baseline
    rep["overall_signal_true"] = {h: stats(sig_true, ret, h) for h in CLEAN_HZ}
    # 2) trade_signal=false 除外の効果 (全件 vs true限定)
    rep["all_vs_filtered"] = {
        h: {"all": stats(matched, ret, h),
            "trade_signal_true_only": stats(sig_true, ret, h)}
        for h in CLEAN_HZ}
    # 3) 方向別
    rep["by_direction"] = {}
    for dv in ("long", "short"):
        sub = [s for s in sig_true if s["direction"] == dv]
        rep["by_direction"][dv] = {"n": len(sub),
                                   **{h: stats(sub, ret, h) for h in CLEAN_HZ}}
    # neutral: DD回避 or 機会損失
    nsub = [s for s in sig_true if s["direction"] == "neutral"]
    rep["by_direction"]["neutral_dd_analysis"] = {
        "n": len(nsub), **{h: neutral_dd_stats(nsub, ret, h) for h in CLEAN_HZ}}
    # 4) 確信度別
    rep["by_confidence"] = {}
    for cb in ("high", "medium", "low"):
        sub = [s for s in sig_true if s["conf"] == cb]
        rep["by_confidence"][cb] = {"n": len(sub),
                                    **{h: stats(sub, ret, h) for h in CLEAN_HZ}}
    # 5) 相場環境別
    rep["by_regime"] = {}
    for rg in ("rally", "crash", "range", "trend"):
        sub = [s for s in sig_true if s["regime"] == rg]
        rep["by_regime"][rg] = {"n": len(sub),
                                **{h: stats(sub, ret, h) for h in CLEAN_HZ}}
    # 6) Pro有無 / 画像有無
    rep["by_pro"] = {
        "pro": {"n": sum(1 for s in sig_true if s["pro"]),
                **{h: stats([s for s in sig_true if s["pro"]], ret, h) for h in CLEAN_HZ}},
        "flash": {"n": sum(1 for s in sig_true if not s["pro"]),
                  **{h: stats([s for s in sig_true if not s["pro"]], ret, h) for h in CLEAN_HZ}}}
    rep["by_images"] = {
        "with_img": {"n": sum(1 for s in sig_true if s["has_images"]),
                     **{h: stats([s for s in sig_true if s["has_images"]], ret, h) for h in CLEAN_HZ}},
        "no_img": {"n": sum(1 for s in sig_true if not s["has_images"]),
                   **{h: stats([s for s in sig_true if not s["has_images"]], ret, h) for h in CLEAN_HZ}}}

    OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")

    def line(tag, s):
        if not s:
            return f"  {tag}: データ無"
        return (f"  {tag}: n={s['n']} 勝率{s['win_rate']}% EV{s['ev_pct']:+}% "
                f"中央{s['median_pct']:+}% 損失率{s['loss_rate']}% 超過{s['excess_ev_pct']:+}%")

    print(f"対象 {len(matched)}件 (trade_signal=true {len(sig_true)}) / 正常horizon {CLEAN_HZ}")
    print("\n=== シグナル(true)のエッジ vs buy&hold ===")
    for h in CLEAN_HZ:
        print(line(h, rep["overall_signal_true"][h]))
    print("\n=== trade_signal=false除外の効果 (1d) ===")
    av = rep["all_vs_filtered"]["ret_1d"]
    print(line("全件      ", av["all"])); print(line("true限定  ", av["trade_signal_true_only"]))
    print("\n=== 方向別 (7d) ===")
    for dv in ("long", "short"):
        print(line(dv, rep["by_direction"][dv]["ret_7d"]))
    print("\n=== 確信度別 (7d) ===")
    for cb in ("high", "medium", "low"):
        print(line(cb, rep["by_confidence"][cb]["ret_7d"]))
    print("\n=== 相場環境別 (7d) ===")
    for rg in ("rally", "crash", "range", "trend"):
        print(line(rg, rep["by_regime"][rg]["ret_7d"]))
    print("\n=== Pro有無/画像有無 (7d) ===")
    print(line("Pro    ", rep["by_pro"]["pro"]["ret_7d"]))
    print(line("Flash  ", rep["by_pro"]["flash"]["ret_7d"]))
    print(line("画像有 ", rep["by_images"]["with_img"]["ret_7d"]))
    print(line("画像無 ", rep["by_images"]["no_img"]["ret_7d"]))
    print(f"\nWROTE {OUT}")


if __name__ == "__main__":
    main()
