#!/usr/bin/env python3
"""danjer三つ組テーブル試作 (₿部屋合意 2026-06-12)

仕様: danjer過去投稿から相場局面の異なる20-50件を厳選 → 投稿時刻を直近確定足に
スナップ → 価格/OI(+LSレシオ)を実測Join → 「根拠→解釈→行動→信頼度」試作テーブル。

データ実態 (棚卸し済み):
- x_tweets.db: danjer投稿 (テーブル/カラムは動的検出)
- btc_market.db market_btc_1d: 日足OHLCV 2017-08-17〜2026-05-18
- btc_trading_ai.db oi_4h_legacy: 4h OI+LSレシオ 2020-08-31〜2026-04-19
- FR/清算: ローカルに無し → 欄のみ用意 (NULL) + coverage_note に明示

出力: btc_trading_ai.db に danjer_triplet_proto テーブル + report JSON
"""
import json
import re
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
XT_DB = BASE / "x_tweets.db"
MKT_DB = BASE / "btc_market.db"
AI_DB = BASE / "btc_trading_ai.db"
OUT_JSON = Path(__file__).parent / "prototype_report.json"

TARGET_USER_HINT = "danjer"
SAMPLES_PER_REGIME = 8  # 4局面 × 8 = 最大32件 (発注の20-50件レンジ内)
JST = timezone(timedelta(hours=9))


def log(msg):
    print(msg, flush=True)


# ---------- 1. danjerツイート読込 (スキーマ動的検出) ----------
def load_danjer_tweets():
    con = sqlite3.connect(f"file:{XT_DB}?mode=ro", uri=True)
    cur = con.cursor()
    best = None
    for (tbl,) in cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"):
        cols = [c[1] for c in cur.execute(f"PRAGMA table_info('{tbl}')")]
        user_col = next((c for c in cols if c.lower() in
                        ("username", "screen_name", "user", "author", "account")), None)
        text_col = next((c for c in cols if c.lower() in
                        ("text", "full_text", "content", "body")), None)
        time_col = next((c for c in cols if "created" in c.lower()
                        or c.lower() in ("date", "ts", "timestamp", "tweet_date")), None)
        id_col = next((c for c in cols if c.lower() in
                      ("id", "tweet_id", "id_str")), None)
        if user_col and text_col and time_col:
            n = cur.execute(
                f"SELECT COUNT(*) FROM '{tbl}' WHERE {user_col} LIKE ?",
                (f"%{TARGET_USER_HINT}%",)).fetchone()[0]
            log(f"  candidate table={tbl} danjer_rows={n}")
            if n and (best is None or n > best[1]):
                best = (tbl, n, user_col, text_col, time_col, id_col)
    if not best:
        raise SystemExit("danjerツイートのテーブルが見つからない")
    tbl, n, user_col, text_col, time_col, id_col = best
    log(f"USE table={tbl} rows={n} cols=({id_col},{user_col},{time_col},{text_col})")
    id_expr = id_col or "rowid"
    rows = cur.execute(
        f"SELECT {id_expr}, {time_col}, {text_col} FROM '{tbl}' "
        f"WHERE {user_col} LIKE ? ORDER BY {time_col}",
        (f"%{TARGET_USER_HINT}%",)).fetchall()
    con.close()
    out = []
    for tid, traw, text in rows:
        dt = parse_dt(traw)
        if dt and text and len(text.strip()) >= 20:  # 短すぎる投稿は学習価値低
            out.append({"tweet_id": str(tid), "dt_utc": dt, "text": text.strip()})
    log(f"danjer tweets usable={len(out)} (period: "
        f"{out[0]['dt_utc']:%Y-%m-%d} .. {out[-1]['dt_utc']:%Y-%m-%d})" if out else "0件")
    return out


def parse_dt(raw):
    if raw is None:
        return None
    s = str(raw).strip()
    if s.isdigit():
        v = int(s)
        if v > 10**12:
            v //= 1000
        return datetime.fromtimestamp(v, tz=timezone.utc)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S",
                "%a %b %d %H:%M:%S %z %Y", "%Y-%m-%d"):
        try:
            d = datetime.strptime(s[:len(datetime.now().strftime(fmt))]
                                  if "%z" not in fmt else s, fmt)
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


# ---------- 2. 市場データ読込 + 局面ラベル ----------
def load_market():
    con = sqlite3.connect(f"file:{MKT_DB}?mode=ro", uri=True)
    rows = con.execute(
        "SELECT ts_epoch, date, open, high, low, close, volume "
        "FROM market_btc_1d ORDER BY ts_epoch").fetchall()
    con.close()
    candles = [{"ts": r[0], "date": r[1], "o": r[2], "h": r[3],
                "l": r[4], "c": r[5], "v": r[6]} for r in rows]
    # 局面: 5日リターンと20日レンジ幅で分類
    for i, cd in enumerate(candles):
        if i < 20:
            cd["regime"] = "warmup"
            continue
        c5ago = candles[i - 5]["c"]
        ret5 = (cd["c"] - c5ago) / c5ago * 100 if c5ago else 0
        win = candles[i - 19:i + 1]
        hi, lo = max(w["h"] for w in win), min(w["l"] for w in win)
        range_pct = (hi - lo) / lo * 100 if lo else 0
        if ret5 >= 10:
            cd["regime"] = "rally"      # 急騰
        elif ret5 <= -10:
            cd["regime"] = "crash"      # 急落
        elif range_pct <= 10:
            cd["regime"] = "range"      # レンジ
        else:
            cd["regime"] = "trend"      # 通常トレンド
        cd["ret5_pct"] = round(ret5, 2)
        cd["range20_pct"] = round(range_pct, 2)
    return candles


def load_oi():
    con = sqlite3.connect(f"file:{AI_DB}?mode=ro", uri=True)
    rows = con.execute(
        "SELECT ts_ms, oi_btc, oi_usd, ls_ratio, top_ls_ratio, taker_ls_ratio "
        "FROM oi_4h_legacy ORDER BY ts_ms").fetchall()
    con.close()
    return [{"ts": r[0] // 1000, "oi_btc": r[1], "oi_usd": r[2],
             "ls": r[3], "top_ls": r[4], "taker_ls": r[5]} for r in rows]


def snap_daily(candles, dt_utc):
    """投稿時刻より前に確定した直近の日足 (date < 投稿日のUTC日付)"""
    target = dt_utc.date().isoformat()
    prev = None
    for cd in candles:
        if cd["date"] >= target:
            break
        prev = cd
    return prev


def snap_oi(oi_rows, dt_utc):
    """投稿時刻より前の直近4h OI行 + 24h前比"""
    ts = int(dt_utc.timestamp())
    prev = None
    prev_24h = None
    for r in oi_rows:
        if r["ts"] >= ts:
            break
        prev = r
    if prev:
        cutoff = prev["ts"] - 86400
        for r in oi_rows:
            if r["ts"] > cutoff:
                prev_24h = r
                break
    return prev, prev_24h


# ---------- 3. 解釈・行動・信頼度の素朴抽出 (v0: 配管検証用) ----------
ACTION_PATTERNS = [
    ("long_entry", r"ロング(エントリ|参戦|イン|します|した)|買い(増し|場|エントリ)|押し目買い"),
    ("short_entry", r"ショート(エントリ|参戦|イン|します|した)|売り(場|エントリ)|戻り売り"),
    ("close_position", r"利確|損切り|クローズ|手仕舞い|ポジション(解消|閉じ)"),
    ("wait", r"様子見|ノーポジ|待ち|静観|見送り"),
]
CONFIDENCE_PATTERNS = [
    (0.9, r"確信|間違いない|鉄板|強い(確度|自信)"),
    (0.7, r"おそらく|可能性が高い|本命|有力"),
    (0.5, r"かもしれない|警戒|どちらとも|五分"),
    (0.3, r"わからない|不明|難しい|読めない"),
]


def extract_action(text):
    for label, pat in ACTION_PATTERNS:
        if re.search(pat, text):
            return label
    return "observation"  # 相場観のみの投稿


def extract_confidence(text):
    for score, pat in CONFIDENCE_PATTERNS:
        if re.search(pat, text):
            return score
    return None  # 明示なし → AI抽出フェーズで補完


# ---------- 4. メイン ----------
def main():
    tweets = load_danjer_tweets()
    candles = load_market()
    oi_rows = load_oi()

    # 各ツイートに局面ラベル付与 (スナップ先日足の局面)
    enriched = []
    for tw in tweets:
        cd = snap_daily(candles, tw["dt_utc"])
        if not cd or cd.get("regime") in (None, "warmup"):
            continue
        oi, oi24 = snap_oi(oi_rows, tw["dt_utc"])
        tw["candle"] = cd
        tw["oi"] = oi
        tw["oi24"] = oi24
        enriched.append(tw)
    log(f"スナップ成功: {len(enriched)}件")

    # 局面別に時間分散サンプリング
    by_regime = {}
    for tw in enriched:
        by_regime.setdefault(tw["candle"]["regime"], []).append(tw)
    samples = []
    for regime, items in sorted(by_regime.items()):
        step = max(1, len(items) // SAMPLES_PER_REGIME)
        picked = items[::step][:SAMPLES_PER_REGIME]
        log(f"  regime={regime}: 母数{len(items)} → 採用{len(picked)}")
        samples.extend(picked)

    # テーブル作成 + 投入
    con = sqlite3.connect(AI_DB)
    con.execute("DROP TABLE IF EXISTS danjer_triplet_proto")
    con.execute("""
      CREATE TABLE danjer_triplet_proto (
        tweet_id TEXT PRIMARY KEY,
        posted_at_utc TEXT, posted_at_jst TEXT,
        regime TEXT,
        -- 根拠 (確定足スナップ + 実測Join)
        snap_1d_date TEXT, snap_1d_open REAL, snap_1d_high REAL,
        snap_1d_low REAL, snap_1d_close REAL, snap_1d_volume REAL,
        ret5_pct REAL, range20_pct REAL,
        snap_oi_ts_utc TEXT, oi_btc REAL, oi_usd REAL,
        oi_chg_24h_pct REAL, ls_ratio REAL, top_ls_ratio REAL, taker_ls_ratio REAL,
        funding_rate REAL,          -- ローカルデータ無し (NULL)
        liquidation_usd_24h REAL,   -- ローカルデータ無し (NULL)
        evidence_json TEXT,
        -- 解釈・行動・信頼度
        interpretation_raw TEXT,    -- danjer投稿原文 (解釈のソース)
        action_v0 TEXT,             -- 素朴抽出 (AI抽出フェーズで置換予定)
        confidence_v0 REAL,
        coverage_note TEXT,
        created_at TEXT DEFAULT (datetime('now'))
      )""")
    inserted = 0
    for tw in samples:
        cd, oi, oi24 = tw["candle"], tw["oi"], tw["oi24"]
        oi_chg = (round((oi["oi_btc"] - oi24["oi_btc"]) / oi24["oi_btc"] * 100, 2)
                  if oi and oi24 and oi24["oi_btc"] else None)
        notes = []
        if not oi:
            notes.append("OI期間外(2020-08以前or2026-04以降)")
        notes.append("FR/清算はローカル未保有→NULL")
        evidence = {
            "candle_1d": {k: cd[k] for k in ("date", "o", "h", "l", "c", "v")},
            "ret5_pct": cd["ret5_pct"], "range20_pct": cd["range20_pct"],
            "oi_4h": oi, "oi_24h_ago": oi24,
        }
        con.execute(
            "INSERT OR REPLACE INTO danjer_triplet_proto ("
            "tweet_id, posted_at_utc, posted_at_jst, regime, "
            "snap_1d_date, snap_1d_open, snap_1d_high, snap_1d_low, "
            "snap_1d_close, snap_1d_volume, ret5_pct, range20_pct, "
            "snap_oi_ts_utc, oi_btc, oi_usd, oi_chg_24h_pct, "
            "ls_ratio, top_ls_ratio, taker_ls_ratio, "
            "funding_rate, liquidation_usd_24h, evidence_json, "
            "interpretation_raw, action_v0, confidence_v0, coverage_note"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (tw["tweet_id"],
             tw["dt_utc"].strftime("%Y-%m-%d %H:%M:%S"),
             tw["dt_utc"].astimezone(JST).strftime("%Y-%m-%d %H:%M:%S"),
             cd["regime"],
             cd["date"], cd["o"], cd["h"], cd["l"], cd["c"], cd["v"],
             cd["ret5_pct"], cd["range20_pct"],
             (datetime.fromtimestamp(oi["ts"], tz=timezone.utc)
              .strftime("%Y-%m-%d %H:%M") if oi else None),
             oi["oi_btc"] if oi else None, oi["oi_usd"] if oi else None,
             oi_chg,
             oi["ls"] if oi else None, oi["top_ls"] if oi else None,
             oi["taker_ls"] if oi else None,
             None, None,
             json.dumps(evidence, ensure_ascii=False, default=str),
             tw["text"][:2000],
             extract_action(tw["text"]),
             extract_confidence(tw["text"]),
             "; ".join(notes)))
        inserted += 1
    con.commit()

    # 検算: 件数 + 局面分布 + サンプル3行
    dist = con.execute(
        "SELECT regime, COUNT(*) FROM danjer_triplet_proto GROUP BY regime").fetchall()
    sample_rows = con.execute(
        "SELECT tweet_id, posted_at_jst, regime, snap_1d_date, snap_1d_close, "
        "oi_btc, oi_chg_24h_pct, action_v0, substr(interpretation_raw,1,60) "
        "FROM danjer_triplet_proto LIMIT 3").fetchall()
    con.close()

    report = {
        "inserted": inserted,
        "regime_distribution": dist,
        "sample_rows": sample_rows,
        "data_coverage": {
            "price_1d": "2017-08-17..2026-05-18 (3197行)",
            "oi_4h": "2020-08-31..2026-04-19 (12341行, LSレシオ込み)",
            "funding_rate": "ローカル未保有 — 全行NULL (要調達判断)",
            "liquidation": "ローカル未保有 — 全行NULL (無料の過去データ源なし)",
        },
        "extraction_note": "action/confidenceはv0素朴抽出。本番はAI抽出に置換予定",
    }
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=1,
                                   default=str), encoding="utf-8")
    log(f"INSERTED {inserted} rows into danjer_triplet_proto")
    log(f"regime分布: {dist}")
    log(f"WROTE {OUT_JSON}")


if __name__ == "__main__":
    main()
