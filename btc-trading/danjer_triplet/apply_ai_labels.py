#!/usr/bin/env python3
"""AI抽出ラベルを danjer_triplet_proto に適用 (must-fix① 後段)

入力: ai_extraction_labels.json
  [{"tweet_id": "...", "interpretation_ai": "...",
    "action_ai": "long|short|close|take_profit|stop|wait|no_trade|thesis_update",
    "action_reason": "...", "confidence_ai": 0.0-1.0}, ...]
事務Claude(本物のAI)が ai_extraction_input.json を読んで文脈ラベリングした結果。
API課金0円 (Claude Codeセッション内で抽出)。

出力: テーブルUPDATE + final_report_v2.json (action_ai分布 + 代表3行)
"""
import json
import sqlite3
from pathlib import Path

HERE = Path(__file__).parent
AI_DB = HERE.parent / "btc_trading_ai.db"
LABELS = HERE / "ai_extraction_labels.json"
OUT = HERE / "final_report_v2.json"

VALID_ACTIONS = {"long", "short", "close", "take_profit", "stop",
                 "wait", "no_trade", "thesis_update"}


def main():
    labels = json.loads(LABELS.read_text(encoding="utf-8"))
    bad = [l for l in labels if l["action_ai"] not in VALID_ACTIONS
           or not (0.0 <= float(l["confidence_ai"]) <= 1.0)]
    if bad:
        raise SystemExit(f"不正ラベル {len(bad)}件: {bad[:3]}")

    con = sqlite3.connect(AI_DB)
    updated = 0
    for l in labels:
        cur = con.execute(
            "UPDATE danjer_triplet_proto SET interpretation_ai=?, "
            "action_ai=?, action_reason=?, confidence_ai=? WHERE tweet_id=?",
            (l["interpretation_ai"], l["action_ai"], l["action_reason"],
             float(l["confidence_ai"]), l["tweet_id"]))
        updated += cur.rowcount
    con.commit()

    total = con.execute(
        "SELECT COUNT(*) FROM danjer_triplet_proto").fetchone()[0]
    unlabeled = con.execute(
        "SELECT COUNT(*) FROM danjer_triplet_proto "
        "WHERE action_ai IS NULL").fetchone()[0]
    dist = con.execute(
        "SELECT action_ai, COUNT(*) FROM danjer_triplet_proto "
        "GROUP BY action_ai ORDER BY 2 DESC").fetchall()
    # 代表3行: action_aiが異なる3行 (分散の証跡 — Gemini要求)
    reps = con.execute("""
      SELECT tweet_id, posted_at_jst, regime, action_ai, confidence_ai,
             action_reason, substr(interpretation_raw,1,80),
             snap_1d_close, oi_chg_24h_pct, funding_rate
      FROM danjer_triplet_proto
      WHERE tweet_id IN (
        SELECT MIN(tweet_id) FROM danjer_triplet_proto
        WHERE action_ai IS NOT NULL GROUP BY action_ai)
      ORDER BY confidence_ai DESC LIMIT 5""").fetchall()
    con.close()

    report = {"labels_applied": updated, "table_rows": total,
              "unlabeled": unlabeled,
              "action_ai_distribution": dist,
              "representative_rows": reps}
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1,
                              default=str), encoding="utf-8")
    print(f"UPDATED {updated}/{total} (未ラベル{unlabeled})")
    print(f"action_ai分布: {dist}")
    print(f"WROTE {OUT}")


if __name__ == "__main__":
    main()
