#!/usr/bin/env python3
"""danjer_triplet_proto_v3 — 工程C (₿部屋 3者true×2巡 2026-06-12 22:08 正式発注)

仕様 (3者一致4点):
①件数ズレ内訳report添付→本番母集団固定 (v2のload_and_classifyを流用)
②相場局面網羅 + stop投稿の意図的サンプリング:
   regime層 4×25=100 (rally急騰/crash急落/range/trendで上昇・下落・レンジ・急落を網羅)
   stop_vocab層 20 (損切り実行系語彙 — v2で0件だったstop抽出の検証用)
   squeeze_vocab層 15 (踏み上げ/ショートカバー系)
   wait_vocab層 15 (様子見/ノーポジ系)
   = 150件 (発注レンジ100-500内)
③v2カラム仕様を完全踏襲 (テーブル名のみ danjer_triplet_proto_v3)
④検証用にAI抽出入力をエクスポート + リーク検査を機械実行
"""
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import build_prototype_v2 as v2  # noqa: E402

HERE = Path(__file__).parent
OUT_JSON = HERE / "proto_v3_report.json"
AI_INPUT = HERE / "ai_extraction_input_v3.json"
TABLE = "danjer_triplet_proto_v3"

REGIME_N = 25
VOCAB_STRATA = [
    ("stop_vocab", 20, re.compile(
        r"損切り?(した|済|しました|くらった|喰らった|され|させられ|実行)|"
        r"ロスカ(ット)?(した|され|くらった)?|狩られた?|建値撤退|"
        r"ストップ(ロス)?(刺さ|かか|に引っ)|損切り最速|切らされ")),
    ("squeeze_vocab", 15, re.compile(
        r"踏み上げ|ショートカバー|焼かれ|ショーター|売り方(が)?(捕ま|焼け|狩られ)|"
        r"ショート(が|勢)?(捕ま|焼け|狩られ|捕獲)|青天井|S勢")),
    ("wait_vocab", 15, re.compile(
        r"様子見|ノーポジ|静観|見送り|待機|手を出さ(ない|ず)|傍観|エントリー?(は)?見送")),
]


def spaced_pick(items, n):
    if not items:
        return []
    step = max(1, len(items) // n)
    return items[::step][:n]


def main():
    tbl, cls, population = v2.load_and_classify()
    candles = v2.load_market()
    oi_rows = v2.load_oi()
    fr_rows = v2.load_fr()
    if not fr_rows:
        raise SystemExit("funding_rate_8h未取得 — fetch_funding_rate.pyを先に実行")

    enriched = []
    for tw in population:
        cd = v2.snap_daily(candles, tw["dt_utc"])
        if not cd or cd.get("regime") in (None, "warmup"):
            continue
        oi, oi24 = v2.snap_oi(oi_rows, tw["dt_utc"])
        fr = v2.snap_series(fr_rows, tw["dt_utc"])
        tw.update(candle=cd, oi=oi, oi24=oi24, fr=fr)
        enriched.append(tw)
    v2.log(f"スナップ成功: {len(enriched)}件 (母集団{len(population)}件中)")

    samples, picked = [], set()
    # 1. 特殊語彙層を先に確保 (希少なため優先)
    for name, n, rx in VOCAB_STRATA:
        pool = [t for t in enriched
                if t["tweet_id"] not in picked and rx.search(t["text"])]
        got = spaced_pick(pool, n)
        for t in got:
            t["stratum"] = name
            picked.add(t["tweet_id"])
        v2.log(f"  stratum={name}: 母数{len(pool)} → 採用{len(got)}")
        samples.extend(got)
    # 2. regime層で残りを充足
    by_regime = {}
    for t in enriched:
        if t["tweet_id"] in picked:
            continue
        by_regime.setdefault(t["candle"]["regime"], []).append(t)
    for regime, items in sorted(by_regime.items()):
        got = spaced_pick(items, REGIME_N)
        for t in got:
            t["stratum"] = "regime"
            picked.add(t["tweet_id"])
        v2.log(f"  regime={regime}: 母数{len(items)} → 採用{len(got)}")
        samples.extend(got)

    import sqlite3
    con = sqlite3.connect(v2.AI_DB)
    con.execute(f"DROP TABLE IF EXISTS {TABLE}")
    con.execute(f"""
      CREATE TABLE {TABLE} (
        tweet_id TEXT PRIMARY KEY,
        posted_at_utc TEXT, posted_at_jst TEXT,
        regime TEXT, sample_stratum TEXT,
        snap_1d_date TEXT, snap_1d_open REAL, snap_1d_high REAL,
        snap_1d_low REAL, snap_1d_close REAL, snap_1d_volume REAL,
        ret5_pct REAL, range20_pct REAL,
        snap_oi_ts_utc TEXT, oi_btc REAL, oi_usd REAL,
        oi_chg_24h_pct REAL, ls_ratio REAL, top_ls_ratio REAL,
        taker_ls_ratio REAL,
        funding_rate REAL,
        liquidation_usd_24h REAL,
        evidence_json TEXT,
        interpretation_raw TEXT,
        interpretation_ai TEXT,
        action_ai TEXT,
        action_reason TEXT,
        confidence_ai REAL,
        coverage_note TEXT,
        created_at TEXT DEFAULT (datetime('now'))
      )""")
    inserted, leak_violations, ai_input = 0, [], []
    for tw in samples:
        cd, oi, oi24, fr = tw["candle"], tw["oi"], tw["oi24"], tw["fr"]
        oi_chg = (round((oi["oi_btc"] - oi24["oi_btc"]) / oi24["oi_btc"] * 100,
                        2) if oi and oi24 and oi24["oi_btc"] else None)
        # リーク検査: スナップ日足は必ず投稿UTC日付より前
        if cd["date"] >= tw["dt_utc"].date().isoformat():
            leak_violations.append(tw["tweet_id"])
        notes = ["清算指標=任意 (無料過去データ源なし)"]
        if not oi:
            notes.append("OI期間外(2020-08-31..2026-04-19外)")
        if not fr:
            notes.append("FR期間外(2019-09-10以前)")
        evidence = {
            "candle_1d": {k: cd[k] for k in ("date", "o", "h", "l", "c", "v")},
            "ret5_pct": cd["ret5_pct"], "range20_pct": cd["range20_pct"],
            "oi_4h": oi, "oi_24h_ago": oi24, "funding_rate_8h": fr,
        }
        con.execute(
            f"INSERT OR REPLACE INTO {TABLE} ("
            "tweet_id, posted_at_utc, posted_at_jst, regime, sample_stratum, "
            "snap_1d_date, snap_1d_open, snap_1d_high, snap_1d_low, "
            "snap_1d_close, snap_1d_volume, ret5_pct, range20_pct, "
            "snap_oi_ts_utc, oi_btc, oi_usd, oi_chg_24h_pct, "
            "ls_ratio, top_ls_ratio, taker_ls_ratio, "
            "funding_rate, liquidation_usd_24h, evidence_json, "
            "interpretation_raw, interpretation_ai, action_ai, "
            "action_reason, confidence_ai, coverage_note"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (tw["tweet_id"],
             tw["dt_utc"].strftime("%Y-%m-%d %H:%M:%S"),
             tw["dt_utc"].astimezone(v2.JST).strftime("%Y-%m-%d %H:%M:%S"),
             cd["regime"], tw["stratum"],
             cd["date"], cd["o"], cd["h"], cd["l"], cd["c"], cd["v"],
             cd["ret5_pct"], cd["range20_pct"],
             (datetime.fromtimestamp(oi["ts"], tz=timezone.utc)
              .strftime("%Y-%m-%d %H:%M") if oi else None),
             oi["oi_btc"] if oi else None, oi["oi_usd"] if oi else None,
             oi_chg,
             oi["ls"] if oi else None, oi["top_ls"] if oi else None,
             oi["taker_ls"] if oi else None,
             fr["fr"] if fr else None,
             None,
             json.dumps(evidence, ensure_ascii=False, default=str),
             tw["text"][:2000],
             None, None, None, None,
             "; ".join(notes)))
        inserted += 1
        ai_input.append({
            "tweet_id": tw["tweet_id"],
            "posted_at_jst": tw["dt_utc"].astimezone(v2.JST)
            .strftime("%Y-%m-%d %H:%M"),
            "regime": cd["regime"], "stratum": tw["stratum"],
            "market": {"close": cd["c"], "ret5_pct": cd["ret5_pct"],
                       "oi_chg_24h_pct": oi_chg,
                       "funding_rate": fr["fr"] if fr else None},
            "text": tw["text"][:2000],
        })
    con.commit()
    dist = con.execute(
        f"SELECT regime, sample_stratum, COUNT(*) FROM {TABLE} "
        "GROUP BY regime, sample_stratum").fetchall()
    nulls = {c: con.execute(
        f"SELECT SUM({c} IS NULL) FROM {TABLE}").fetchone()[0]
        for c in ("oi_btc", "funding_rate", "ls_ratio", "snap_1d_close")}
    con.close()

    AI_INPUT.write_text(json.dumps(ai_input, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    report = {
        "table": TABLE, "inserted": inserted,
        "regime_stratum_distribution": dist,
        "population_breakdown": {"source_table": tbl, **cls},
        "leak_check": {"violations": leak_violations,
                       "result": "PASS (全行: snap日足 < 投稿UTC日付)"
                       if not leak_violations else "FAIL"},
        "null_rates": {k: f"{v}/{inserted}" for k, v in nulls.items()},
        "ai_extraction": {"input_file": str(AI_INPUT),
                          "next": "事務Claudeラベリング→apply_ai_labels_v3.py"},
    }
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=1,
                                   default=str), encoding="utf-8")
    v2.log(f"INSERTED {inserted} rows into {TABLE}")
    v2.log(f"leak_check: {report['leak_check']['result']}")
    v2.log(f"WROTE {OUT_JSON} / {AI_INPUT}")


if __name__ == "__main__":
    main()
