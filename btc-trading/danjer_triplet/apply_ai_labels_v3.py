#!/usr/bin/env python3
"""工程C: AI抽出ラベルを danjer_triplet_proto_v3 に適用 + 検証レポート生成

入力: ai_extraction_labels_v3.json (150件)
  各要素: tweet_id / interpretation_ai / action_ai / action_reason /
          confidence_ai / (任意) hard_case_note — 判定困難例の注記=失敗例として収集
出力: final_report_v3.json
  action_ai分布(層別含む) / confidence_ai分布 / 欠損率 / リーク検査 /
  代表例(stop含む) / 失敗例(hard_case)
"""
import json
import sqlite3
from pathlib import Path

HERE = Path(__file__).parent
AI_DB = HERE.parent / "btc_trading_ai.db"
LABELS = HERE / "ai_extraction_labels_v3.json"
OUT = HERE / "final_report_v3.json"
TABLE = "danjer_triplet_proto_v3"

VALID = {"long", "short", "close", "take_profit", "stop",
         "wait", "no_trade", "thesis_update"}


def main():
    labels = json.loads(LABELS.read_text(encoding="utf-8"))
    bad = [l for l in labels if l["action_ai"] not in VALID
           or not (0.0 <= float(l["confidence_ai"]) <= 1.0)]
    if bad:
        raise SystemExit(f"不正ラベル {len(bad)}件: {[b['tweet_id'] for b in bad[:5]]}")

    con = sqlite3.connect(AI_DB)
    updated = 0
    hard_cases = []
    for l in labels:
        cur = con.execute(
            f"UPDATE {TABLE} SET interpretation_ai=?, action_ai=?, "
            "action_reason=?, confidence_ai=? WHERE tweet_id=?",
            (l["interpretation_ai"], l["action_ai"], l["action_reason"],
             float(l["confidence_ai"]), l["tweet_id"]))
        updated += cur.rowcount
        if l.get("hard_case_note"):
            hard_cases.append({"tweet_id": l["tweet_id"],
                               "action_ai": l["action_ai"],
                               "note": l["hard_case_note"]})
    con.commit()  # 2026-06-12事故: commit漏れでclose時に全行ロールバックされた

    total = con.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0]
    unlabeled = con.execute(
        f"SELECT COUNT(*) FROM {TABLE} WHERE action_ai IS NULL").fetchone()[0]
    dist = con.execute(
        f"SELECT action_ai, COUNT(*) FROM {TABLE} "
        "GROUP BY action_ai ORDER BY 2 DESC").fetchall()
    dist_by_stratum = con.execute(
        f"SELECT sample_stratum, action_ai, COUNT(*) FROM {TABLE} "
        "GROUP BY sample_stratum, action_ai ORDER BY 1, 3 DESC").fetchall()
    conf_dist = con.execute(f"""
      SELECT CASE WHEN confidence_ai >= 0.7 THEN 'high(>=0.7)'
                  WHEN confidence_ai >= 0.5 THEN 'mid(0.5-0.7)'
                  ELSE 'low(<0.5)' END, COUNT(*)
      FROM {TABLE} WHERE confidence_ai IS NOT NULL GROUP BY 1""").fetchall()
    nulls = {c: con.execute(
        f"SELECT SUM({c} IS NULL) FROM {TABLE}").fetchone()[0]
        for c in ("oi_btc", "funding_rate", "ls_ratio", "snap_1d_close",
                  "action_ai", "interpretation_ai")}
    leak = con.execute(
        f"SELECT COUNT(*) FROM {TABLE} "
        "WHERE snap_1d_date >= date(posted_at_utc)").fetchone()[0]
    # 代表例: action_aiごとに最高confidenceの1行 (stop必須確認)
    reps = con.execute(f"""
      SELECT t.action_ai, t.tweet_id, t.posted_at_jst, t.regime,
             t.sample_stratum, t.confidence_ai, t.action_reason,
             substr(t.interpretation_raw, 1, 90)
      FROM {TABLE} t
      JOIN (SELECT action_ai a, MAX(confidence_ai) c FROM {TABLE}
            WHERE action_ai IS NOT NULL GROUP BY action_ai) m
        ON t.action_ai = m.a AND t.confidence_ai = m.c
      GROUP BY t.action_ai""").fetchall()
    con.close()

    report = {
        "table": TABLE, "labels_applied": updated, "table_rows": total,
        "unlabeled": unlabeled,
        "action_ai_distribution": dist,
        "action_ai_by_stratum": dist_by_stratum,
        "confidence_distribution": conf_dist,
        "null_rates": {k: f"{v}/{total}" for k, v in nulls.items()},
        "leak_check": "PASS (違反0行)" if leak == 0 else f"FAIL ({leak}行)",
        "representative_rows": reps,
        "failure_examples_hard_cases": hard_cases,
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1,
                              default=str), encoding="utf-8")
    print(f"UPDATED {updated}/{total} (未ラベル{unlabeled})")
    print(f"action分布: {dist}")
    print(f"conf分布: {conf_dist}  leak: {report['leak_check']}")
    print(f"hard_cases: {len(hard_cases)}件")
    print(f"WROTE {OUT}")


if __name__ == "__main__":
    main()
