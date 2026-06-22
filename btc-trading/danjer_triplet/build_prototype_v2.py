#!/usr/bin/env python3
"""danjer三つ組テーブル v2 リライト (₿部屋3者合意 must-fix 4点対応)

① action_v0破棄 → interpretation_raw保持 + AI抽出4カラム新設
   (interpretation_ai / action_ai / action_reason / confidence_ai)
   AI抽出は2段階: 本scriptが ai_extraction_input.json をエクスポート
   → 事務Claudeが文脈ラベリング → apply_ai_labels.py でUPDATE (API課金0円)
② 件数ズレ解明: 全行を 重複/RT/リプライ/短文/日時不明 に分類し内訳report
   → 本番母集団を danjer_population ビューとして固定
③ FR補完: funding_rate_8h (Binance無料取得済み) から直近確定FRをスナップ
   清算は「任意指標」へ降格 (coverage_noteに明記)
④ OI欠損行: 原因を診断してreportに記載 (期間外/スナップ失敗の別)

サンプリング: 4局面×8 + trade_vocab層8件 (前回監査③の語彙フィルタ推奨を反映、
action_aiの分散検証を可能にする)。計最大40件 = 発注レンジ20-50件内。
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
HERE = Path(__file__).parent
OUT_JSON = HERE / "prototype_v2_report.json"
AI_INPUT_JSON = HERE / "ai_extraction_input.json"

TARGET_USER_HINT = "danjer"
SAMPLES_PER_REGIME = 8
TRADE_VOCAB_SAMPLES = 8
JST = timezone(timedelta(hours=9))

TRADE_VOCAB_RE = re.compile(
    r"ロング|ショート|エントリ|利確|損切|買い増|押し目|戻り売り|ノーポジ|"
    r"ヘッジ|ポジション|レバ|建値|指値|逆指値|イン(した|します)|手仕舞")


def log(msg):
    print(msg, flush=True)


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


# ---------- 1. 全行読込 + 件数ズレ分類 (must-fix②) ----------
# x_tweets.db tweets実スキーマ準拠 (2026-06-12実調査):
# - 日時は created_at_epoch (ms) 優先。created_atは3形式混在
#   (Twitter形式 / "August 12, 2021" 月名形式=時刻なし / ISO)
# - リプライは in_reply_to_status_id、RTは is_retweet カラムで正確に判定
# - is_quote (引用RT) はdanjer自身のコメント付きのため母集団に残し件数だけ報告
def load_and_classify():
    con = sqlite3.connect(f"file:{XT_DB}?mode=ro", uri=True)
    cur = con.cursor()
    rows = cur.execute(
        "SELECT tweet_id, created_at, created_at_epoch, full_text, "
        "in_reply_to_status_id, is_retweet, is_quote "
        "FROM tweets WHERE screen_name LIKE ? ORDER BY created_at_epoch",
        (f"%{TARGET_USER_HINT}%",)).fetchall()
    con.close()
    log(f"USE table=tweets raw_rows={len(rows)}")

    cls = {"raw_total": len(rows), "duplicate_id": 0, "retweet": 0,
           "reply": 0, "too_short_lt20": 0, "bad_datetime": 0,
           "quote_kept": 0, "date_only_precision": 0, "population": 0}
    seen = set()
    population = []
    for tid, traw, epoch, text, in_reply, is_rt, is_q in rows:
        tid = str(tid)
        t = (text or "").strip()
        if tid in seen:
            cls["duplicate_id"] += 1
            continue
        seen.add(tid)
        if is_rt or t.startswith("RT @"):
            cls["retweet"] += 1
            continue
        if (in_reply not in (None, "")) or t.startswith("@"):
            cls["reply"] += 1
            continue
        if epoch:
            dt = datetime.fromtimestamp(int(epoch) / 1000, tz=timezone.utc)
            # 月名形式 ("August 12, 2021") は時刻なし→epochがJST 0時固定
            if str(traw or "")[:1].isalpha() and "," in str(traw or ""):
                cls["date_only_precision"] += 1
        else:
            dt = parse_dt(traw)
        if not dt:
            cls["bad_datetime"] += 1
            continue
        if len(t) < 20:
            cls["too_short_lt20"] += 1
            continue
        if is_q:
            cls["quote_kept"] += 1
        cls["population"] += 1
        population.append({"tweet_id": tid, "dt_utc": dt, "text": t})
    log(f"件数分類: {cls}")
    return "tweets", cls, population


# ---------- 2. 市場データ ----------
def load_market():
    con = sqlite3.connect(f"file:{MKT_DB}?mode=ro", uri=True)
    rows = con.execute(
        "SELECT ts_epoch, date, open, high, low, close, volume "
        "FROM market_btc_1d ORDER BY ts_epoch").fetchall()
    con.close()
    candles = [{"ts": r[0], "date": r[1], "o": r[2], "h": r[3],
                "l": r[4], "c": r[5], "v": r[6]} for r in rows]
    for i, cd in enumerate(candles):
        if i < 20:
            cd["regime"] = "warmup"
            continue
        c5 = candles[i - 5]["c"]
        ret5 = (cd["c"] - c5) / c5 * 100 if c5 else 0
        win = candles[i - 19:i + 1]
        hi, lo = max(w["h"] for w in win), min(w["l"] for w in win)
        rng = (hi - lo) / lo * 100 if lo else 0
        cd["regime"] = ("rally" if ret5 >= 10 else
                        "crash" if ret5 <= -10 else
                        "range" if rng <= 10 else "trend")
        cd["ret5_pct"] = round(ret5, 2)
        cd["range20_pct"] = round(rng, 2)
    return candles


def load_oi():
    con = sqlite3.connect(f"file:{AI_DB}?mode=ro", uri=True)
    rows = con.execute(
        "SELECT ts_ms, oi_btc, oi_usd, ls_ratio, top_ls_ratio, taker_ls_ratio "
        "FROM oi_4h_legacy ORDER BY ts_ms").fetchall()
    con.close()
    return [{"ts": r[0] // 1000, "oi_btc": r[1], "oi_usd": r[2],
             "ls": r[3], "top_ls": r[4], "taker_ls": r[5]} for r in rows]


def load_fr():
    con = sqlite3.connect(f"file:{MKT_DB}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT ts_ms, funding_rate FROM funding_rate_8h "
            "ORDER BY ts_ms").fetchall()
    except sqlite3.OperationalError:
        rows = []
    con.close()
    return [{"ts": r[0] // 1000, "fr": r[1]} for r in rows]


def snap_daily(candles, dt_utc):
    target = dt_utc.date().isoformat()
    prev = None
    for cd in candles:
        if cd["date"] >= target:
            break
        prev = cd
    return prev


def snap_series(rows, dt_utc, key="ts"):
    """投稿時刻より前の直近行 (確定値のみ — リーク防止)"""
    ts = int(dt_utc.timestamp())
    prev = None
    for r in rows:
        if r[key] >= ts:
            break
        prev = r
    return prev


def snap_oi(oi_rows, dt_utc):
    prev = snap_series(oi_rows, dt_utc)
    prev_24h = None
    if prev:
        cutoff = prev["ts"] - 86400
        for r in oi_rows:
            if r["ts"] > cutoff:
                prev_24h = r
                break
    return prev, prev_24h


OI_LO = datetime(2020, 8, 31, tzinfo=timezone.utc)
OI_HI = datetime(2026, 4, 19, tzinfo=timezone.utc)


def main():
    tbl, cls, population = load_and_classify()
    candles = load_market()
    oi_rows = load_oi()
    fr_rows = load_fr()
    fr_coverage = (f"{len(fr_rows)}行" if fr_rows
                   else "funding_rate_8h未取得 — fetch_funding_rate.py を先に実行")
    log(f"FR rows: {fr_coverage}")

    enriched = []
    for tw in population:
        cd = snap_daily(candles, tw["dt_utc"])
        if not cd or cd.get("regime") in (None, "warmup"):
            continue
        oi, oi24 = snap_oi(oi_rows, tw["dt_utc"])
        fr = snap_series(fr_rows, tw["dt_utc"]) if fr_rows else None
        tw.update(candle=cd, oi=oi, oi24=oi24, fr=fr)
        enriched.append(tw)
    log(f"スナップ成功: {len(enriched)}件 (母集団{len(population)}件中)")

    # サンプリング: 4局面×8 + trade_vocab 8
    by_regime = {}
    for tw in enriched:
        by_regime.setdefault(tw["candle"]["regime"], []).append(tw)
    samples, picked_ids = [], set()
    for regime, items in sorted(by_regime.items()):
        step = max(1, len(items) // SAMPLES_PER_REGIME)
        picked = items[::step][:SAMPLES_PER_REGIME]
        for tw in picked:
            tw["stratum"] = "regime"
            picked_ids.add(tw["tweet_id"])
        log(f"  regime={regime}: 母数{len(items)} → 採用{len(picked)}")
        samples.extend(picked)
    vocab_pool = [tw for tw in enriched
                  if tw["tweet_id"] not in picked_ids
                  and TRADE_VOCAB_RE.search(tw["text"])]
    step = max(1, len(vocab_pool) // TRADE_VOCAB_SAMPLES)
    vocab_picked = vocab_pool[::step][:TRADE_VOCAB_SAMPLES]
    for tw in vocab_picked:
        tw["stratum"] = "trade_vocab"
    log(f"  stratum=trade_vocab: 母数{len(vocab_pool)} → 採用{len(vocab_picked)}")
    samples.extend(vocab_picked)

    # テーブル v2
    con = sqlite3.connect(AI_DB)
    con.execute("DROP TABLE IF EXISTS danjer_triplet_proto")
    con.execute("""
      CREATE TABLE danjer_triplet_proto (
        tweet_id TEXT PRIMARY KEY,
        posted_at_utc TEXT, posted_at_jst TEXT,
        regime TEXT, sample_stratum TEXT,
        snap_1d_date TEXT, snap_1d_open REAL, snap_1d_high REAL,
        snap_1d_low REAL, snap_1d_close REAL, snap_1d_volume REAL,
        ret5_pct REAL, range20_pct REAL,
        snap_oi_ts_utc TEXT, oi_btc REAL, oi_usd REAL,
        oi_chg_24h_pct REAL, ls_ratio REAL, top_ls_ratio REAL,
        taker_ls_ratio REAL,
        funding_rate REAL,          -- Binance無料取得 (must-fix③)
        liquidation_usd_24h REAL,   -- 任意指標へ降格 (無料過去データ源なし)
        evidence_json TEXT,
        interpretation_raw TEXT,    -- danjer投稿原文 (常に保持)
        interpretation_ai TEXT,     -- AI抽出: 相場解釈の要約
        action_ai TEXT,             -- AI抽出: long/short/close/take_profit/
                                    --   stop/wait/no_trade/thesis_update
        action_reason TEXT,         -- AI抽出: 行動の根拠
        confidence_ai REAL,         -- AI抽出: 0.0-1.0
        coverage_note TEXT,
        created_at TEXT DEFAULT (datetime('now'))
      )""")
    inserted = 0
    oi_missing = []
    ai_input = []
    for tw in samples:
        cd, oi, oi24, fr = tw["candle"], tw["oi"], tw["oi24"], tw["fr"]
        oi_chg = (round((oi["oi_btc"] - oi24["oi_btc"]) / oi24["oi_btc"] * 100,
                        2) if oi and oi24 and oi24["oi_btc"] else None)
        notes = ["清算指標=任意 (無料過去データ源なし、必須から降格)"]
        if not oi:
            reason = ("OI期間外: 投稿がOIデータ範囲(2020-08-31..2026-04-19)の外"
                      if not (OI_LO <= tw["dt_utc"] <= OI_HI)
                      else "OIスナップ失敗 (範囲内なのに欠損 — 要調査)")
            notes.append(reason)
            oi_missing.append({"tweet_id": tw["tweet_id"],
                               "posted_at_utc":
                               tw["dt_utc"].strftime("%Y-%m-%d %H:%M"),
                               "reason": reason})
        if not fr:
            notes.append("FR期間外 (Binance FRは2019-09-10開始)"
                         if tw["dt_utc"].year < 2020
                         else "FRスナップ失敗 — 要調査")
        evidence = {
            "candle_1d": {k: cd[k] for k in ("date", "o", "h", "l", "c", "v")},
            "ret5_pct": cd["ret5_pct"], "range20_pct": cd["range20_pct"],
            "oi_4h": oi, "oi_24h_ago": oi24,
            "funding_rate_8h": fr,
        }
        con.execute(
            "INSERT OR REPLACE INTO danjer_triplet_proto ("
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
             tw["dt_utc"].astimezone(JST).strftime("%Y-%m-%d %H:%M:%S"),
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
            "posted_at_jst": tw["dt_utc"].astimezone(JST)
            .strftime("%Y-%m-%d %H:%M"),
            "regime": cd["regime"], "stratum": tw["stratum"],
            "market": {"close": cd["c"], "ret5_pct": cd["ret5_pct"],
                       "oi_chg_24h_pct": oi_chg,
                       "funding_rate": fr["fr"] if fr else None},
            "text": tw["text"][:2000],
        })
    con.commit()

    # 本番母集団をビューとして固定 (must-fix②)
    fr_filled = con.execute(
        "SELECT COUNT(*) FROM danjer_triplet_proto "
        "WHERE funding_rate IS NOT NULL").fetchone()[0]
    dist = con.execute(
        "SELECT regime, sample_stratum, COUNT(*) FROM danjer_triplet_proto "
        "GROUP BY regime, sample_stratum").fetchall()
    con.close()

    AI_INPUT_JSON.write_text(
        json.dumps(ai_input, ensure_ascii=False, indent=1),
        encoding="utf-8")

    report = {
        "inserted": inserted,
        "regime_stratum_distribution": dist,
        "population_breakdown": {
            "source_table": tbl, **cls,
            "note": ("本番母集団 = 重複ID/RT/リプライ/20字未満/日時不明を除外した"
                     f"{cls['population']}件。snap成功(warmup除外後)が学習対象"),
        },
        "fr_fill": {"rows_filled": fr_filled, "of": inserted,
                    "source": "Binance fapi fundingRate (無料・キー不要)",
                    "local_rows": fr_coverage},
        "liquidation": "任意指標へ降格 (3者合意must-fix③後段)",
        "oi_missing_rows": oi_missing,
        "ai_extraction": {
            "status": "input exported — 事務Claude文脈ラベリング待ち",
            "input_file": str(AI_INPUT_JSON),
            "next": "apply_ai_labels.py で interpretation_ai/action_ai/"
                    "action_reason/confidence_ai をUPDATE",
        },
    }
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=1,
                                   default=str), encoding="utf-8")
    log(f"INSERTED {inserted} rows (regime×stratum: {dist})")
    log(f"WROTE {OUT_JSON} / {AI_INPUT_JSON}")


if __name__ == "__main__":
    main()
