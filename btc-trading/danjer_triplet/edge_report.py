#!/usr/bin/env python3
"""Step0: エッジ定量化レポート (₿部屋3者合意 2026-06-16・コスト0ローカル集計)

danjer_reading_prod 13,671件の方向シグナルを、投稿後のBTC実リターンと突き合わせ、
方向/売買シグナル/確信度/相場環境別に 勝率・期待値(EV) を算出。
ベースライン(同期間 buy&hold)と比較し、実力アルファかベータかを判定する。

シグナルリターンの定義:
  long   → +forward_return (上がれば勝ち)
  short  → -forward_return (下がれば勝ち)
  neutral→ ポジションなし (エッジ計算から除外、参考で別集計)
forward_return = (close[D+H] / close[D]) - 1   (D=投稿日, H=保有日数)
baseline(buy&hold) = 同じD群の平均 forward_return (常にロング=地合い)
excess_EV = signalのEV − baselineのEV (これがプラスならアルファの証拠)
"""
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
AI_DB = HERE.parent / "btc_trading_ai.db"
MKT_DB = HERE.parent / "btc_market.db"
OUT = HERE / "edge_report.json"
HORIZONS = [1, 3, 7, 14]


def load_prices():
    con = sqlite3.connect(f"file:{MKT_DB}?mode=ro", uri=True)
    rows = con.execute(
        "SELECT date, close FROM market_btc_1d ORDER BY date").fetchall()
    con.close()
    dates = [r[0] for r in rows]
    close = {r[0]: r[1] for r in rows}
    idx = {d: i for i, d in enumerate(dates)}
    return dates, close, idx


def conf_bucket(c):
    s = str(c).lower()
    if "high" in s:
        return "high"
    if "low" in s:
        return "low"
    if "medium" in s or "mid" in s:
        return "medium"
    return "unknown"


def main():
    dates, close, idx = load_prices()
    con = sqlite3.connect(f"file:{AI_DB}?mode=ro", uri=True)
    rows = con.execute(
        "SELECT posted_at_utc, regime, reading_json FROM danjer_reading_prod "
        "WHERE reading_json IS NOT NULL").fetchall()
    con.close()

    # 各投稿に forward_return(各H) と direction/conf/trade_signal を付与
    recs = []
    skipped = 0
    for posted, regime, rj in rows:
        d = json.loads(rj)
        post_date = posted[:10]
        # 投稿日以前の直近確定足を入口に (leak-safe)
        i = idx.get(post_date)
        if i is None:
            # 直近の過去営業日を探す
            cand = [k for k in dates if k <= post_date]
            if not cand:
                skipped += 1
                continue
            i = idx[cand[-1]]
        entry = close[dates[i]]
        if not entry:
            skipped += 1
            continue
        fr = {}
        for H in HORIZONS:
            j = i + H
            if j < len(dates) and close[dates[j]]:
                fr[H] = close[dates[j]] / entry - 1
        if not fr:
            skipped += 1
            continue
        action = d.get("danjer_action") or {}
        recs.append({
            "regime": regime,
            "direction": action.get("direction", "?"),
            "conf": conf_bucket(d.get("confidence")),
            "trade_signal": bool(d.get("trade_signal")),
            "fr": fr,
        })

    def stats(subset, H):
        """signalリターンの 勝率/EV/N と baseline(buy&hold)EV を返す"""
        sig, base = [], []
        for r in subset:
            if H not in r["fr"]:
                continue
            f = r["fr"][H]
            base.append(f)  # 常にロング=baseline
            dv = r["direction"]
            if dv == "long":
                sig.append(f)
            elif dv == "short":
                sig.append(-f)
            # neutral はポジション無し→sigに入れない
        if not sig:
            return None
        win = sum(1 for x in sig if x > 0) / len(sig)
        ev = sum(sig) / len(sig)
        base_ev = sum(base) / len(base) if base else 0
        return {"n": len(sig), "win_rate": round(win * 100, 1),
                "ev_pct": round(ev * 100, 2),
                "baseline_ev_pct": round(base_ev * 100, 2),
                "excess_ev_pct": round((ev - base_ev) * 100, 2)}

    report = {"total": len(recs), "skipped_no_price": skipped,
              "horizons_days": HORIZONS, "by": {}}

    # 全体 + 各H
    report["overall"] = {H: stats(recs, H) for H in HORIZONS}
    # trade_signal=true のみ (エッジが出るはずの母集団)
    sig_true = [r for r in recs if r["trade_signal"]]
    report["trade_signal_true"] = {H: stats(sig_true, H) for H in HORIZONS}
    # 方向別
    for dv in ("long", "short", "neutral"):
        sub = [r for r in recs if r["direction"] == dv]
        report["by"][f"direction={dv}"] = {
            "n": len(sub), **{f"H{H}": stats(sub, H) for H in HORIZONS}}
    # 確信度別 (trade_signal=trueのみ)
    for cb in ("high", "medium", "low"):
        sub = [r for r in sig_true if r["conf"] == cb]
        report["by"][f"confidence={cb}"] = {
            "n": len(sub), **{f"H{H}": stats(sub, H) for H in HORIZONS}}
    # 相場環境別 (trade_signal=trueのみ)
    for rg in ("rally", "crash", "range", "trend"):
        sub = [r for r in sig_true if r["regime"] == rg]
        report["by"][f"regime={rg}"] = {
            "n": len(sub), **{f"H{H}": stats(sub, H) for H in HORIZONS}}

    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    # コンソール要約
    print(f"対象 {len(recs)}件 (価格欠如除外 {skipped})")
    print(f"\n=== 全方向シグナル (long/short) のエッジ vs buy&hold ===")
    for H in HORIZONS:
        s = report["trade_signal_true"][H]
        if s:
            print(f"  {H:2}日: 勝率{s['win_rate']}% EV{s['ev_pct']:+}% "
                  f"baseline{s['baseline_ev_pct']:+}% → 超過{s['excess_ev_pct']:+}%")
    print(f"\n=== 方向別 (7日) ===")
    for dv in ("long", "short", "neutral"):
        b = report["by"][f"direction={dv}"]
        s = b.get("H7")
        if s:
            print(f"  {dv:7}(n={b['n']:5}): 勝率{s['win_rate']}% "
                  f"EV{s['ev_pct']:+}% 超過{s['excess_ev_pct']:+}%")
    print(f"\n=== 確信度別 (7日, trade_signal=true) ===")
    for cb in ("high", "medium", "low"):
        b = report["by"][f"confidence={cb}"]
        s = b.get("H7")
        if s:
            print(f"  {cb:7}(n={b['n']:5}): 勝率{s['win_rate']}% "
                  f"EV{s['ev_pct']:+}% 超過{s['excess_ev_pct']:+}%")
    print(f"\n=== 相場環境別 (7日) ===")
    for rg in ("rally", "crash", "range", "trend"):
        b = report["by"][f"regime={rg}"]
        s = b.get("H7")
        if s:
            print(f"  {rg:6}(n={b['n']:5}): 勝率{s['win_rate']}% "
                  f"EV{s['ev_pct']:+}% 超過{s['excess_ev_pct']:+}%")
    print(f"\nWROTE {OUT}")


if __name__ == "__main__":
    main()
