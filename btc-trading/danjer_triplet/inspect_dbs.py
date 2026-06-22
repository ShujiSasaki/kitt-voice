#!/usr/bin/env python3
"""danjer三つ組テーブル試作 Phase1: DB棚卸し (読み取りのみ)

₿部屋合意 (2026-06-12): danjer過去投稿20-50件 × 確定足スナップ × 価格/OI/FR/清算Join
の試作に先立ち、両DBのスキーマ・件数・期間カバレッジを出力する。
"""
import json
import sqlite3
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent  # btc-trading/
DBS = {
    "xtweets": BASE / "xtweets.db",
    "btc_market": BASE / "btc_market.db",
    "btc_trading_ai": BASE / "btc_trading_ai.db",
}

def inspect(name: str, path: Path) -> dict:
    if not path.exists():
        return {"exists": False, "path": str(path)}
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    cur = con.cursor()
    out = {"exists": True, "path": str(path), "tables": {}}
    for (tbl,) in cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
        info = {"columns": [], "rows": None}
        for col in cur.execute(f"PRAGMA table_info('{tbl}')"):
            info["columns"].append(f"{col[1]} {col[2]}")
        try:
            info["rows"] = cur.execute(f"SELECT COUNT(*) FROM '{tbl}'").fetchone()[0]
        except Exception as e:
            info["rows"] = f"err:{e}"
        out["tables"][tbl] = info
    con.close()
    return out

def main():
    report = {}
    for name, path in DBS.items():
        report[name] = inspect(name, path)
    # 追加: danjer関連の件数と期間 (テーブル名は実物に合わせて動的に探す)
    extras = {}
    xt = DBS["xtweets"]
    if xt.exists():
        con = sqlite3.connect(f"file:{xt}?mode=ro", uri=True)
        cur = con.cursor()
        for (tbl,) in cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"):
            cols = [c[1] for c in cur.execute(f"PRAGMA table_info('{tbl}')")]
            user_col = next((c for c in cols if c in
                            ("username", "screen_name", "user", "author")), None)
            time_col = next((c for c in cols if "created" in c.lower()
                            or "date" in c.lower() or c in ("ts", "timestamp")), None)
            if user_col:
                try:
                    rows = cur.execute(
                        f"SELECT {user_col}, COUNT(*), MIN({time_col}), MAX({time_col}) "
                        f"FROM '{tbl}' GROUP BY {user_col} ORDER BY 2 DESC LIMIT 10"
                    ).fetchall() if time_col else cur.execute(
                        f"SELECT {user_col}, COUNT(*) FROM '{tbl}' "
                        f"GROUP BY {user_col} ORDER BY 2 DESC LIMIT 10").fetchall()
                    extras[f"{tbl}.by_{user_col}"] = rows
                except Exception as e:
                    extras[f"{tbl}.err"] = str(e)
        con.close()
    # 市場データの期間カバレッジ
    bm = DBS["btc_market"]
    if bm.exists():
        con = sqlite3.connect(f"file:{bm}?mode=ro", uri=True)
        cur = con.cursor()
        for (tbl,) in cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"):
            cols = [c[1] for c in cur.execute(f"PRAGMA table_info('{tbl}')")]
            time_col = next((c for c in cols if "time" in c.lower()
                            or "date" in c.lower() or c == "ts"), None)
            if time_col:
                try:
                    extras[f"market.{tbl}.range"] = cur.execute(
                        f"SELECT MIN({time_col}), MAX({time_col}), COUNT(*) "
                        f"FROM '{tbl}'").fetchone()
                except Exception as e:
                    extras[f"market.{tbl}.err"] = str(e)
        con.close()
    report["extras"] = extras
    out_path = Path(__file__).parent / "inspect_result.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=1,
                                   default=str), encoding="utf-8")
    print(f"WROTE {out_path}")
    # コンソールにも要約
    for name, r in report.items():
        if name == "extras":
            continue
        if not r.get("exists"):
            print(f"[{name}] MISSING: {r['path']}")
            continue
        print(f"[{name}] {len(r['tables'])} tables")
        for tbl, info in r["tables"].items():
            print(f"  {tbl}: rows={info['rows']} cols={len(info['columns'])}")

if __name__ == "__main__":
    main()
