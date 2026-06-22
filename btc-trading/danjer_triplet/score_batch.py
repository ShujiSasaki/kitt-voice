#!/usr/bin/env python3
"""採点バッチ準備 + 台帳 (Shuji 2026-06-18: 採点は事務Claudeが¥0で実施)

各予測(danjer_reading_prod の読み+方向)に対し、投稿時刻からの価格パスを
1h足(主)/日足で計算し、MFE(最大順行)/MAE(最大逆行)/期限終値リターンを出す。
→ 事務Claudeがこれを読んで0-100点を付け、danjer_scores へ書き戻す。

分類は3階層(大>中>小)に細分化。

usage:
  python3 score_batch.py --prepare --n 12 [--offset 0]   # 採点用バッチをJSON出力
  python3 score_batch.py --init                          # danjer_scoresテーブル作成
  python3 score_batch.py --stats                         # 進捗集計
"""
import argparse
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
AI = HERE.parent / "btc_trading_ai.db"
MK = HERE.parent / "btc_market.db"

# ---- 3階層タクソノミー (大 > 中 > 小)。danjer語彙 ----
TAXO = {
 "テクニカル": {
  "チャートパターン": [("三尊", ["三尊", "ヘッドアンドショルダー"]), ("逆三尊", ["逆三尊"]),
                ("ダイアモンド", ["ダイアモンド", "ダイヤ"]),
                ("ウェッジ", ["ウェッジ"]), ("ペナント", ["ペナント"]),
                ("三角持ち合い", ["三角持", "三角保", "アセトラ", "ディセトラ", "シンメトリカル"]),
                ("ネックライン", ["ネックライン", "ネック"]), ("ダブルトップ/ボトム", ["ダブルトップ", "ダブルボトム", "Wボトム", "Mトップ"])],
  "トレンド系": [("SMA200", ["SMA200", "200日", "200MA", "MA200"]), ("SMA短中期", ["SMA20", "SMA50", "SMA100", "MA20", "MA50", "MA100"]),
            ("グランビル", ["グランビル"]), ("GMMA", ["GMMA"]), ("パーフェクトオーダー", ["パーフェクトオーダー"]),
            ("一目/雲", ["一目", "雲"]), ("雲のねじれ", ["ねじれ", "捻じれ"]), ("トレンドライン/チャネル", ["チャネル", "トレンドライン"])],
  "水平線/フィボ": [("サポレジ/節目", ["サポート", "レジスタンス", "サポレジ", "節目", "水平線"]),
              ("フィボ半値", ["半値", "0.5戻", "50%戻"]), ("フィボその他", ["フィボ", "0.618", "0.382", "0.236", "0.786"])],
  "オシレーター": [("ダイバージェンス", ["ダイバージェンス", "ダイバ"]), ("ヒドゥンダイバ", ["ヒドゥン"]),
             ("MACD", ["MACD"]), ("RSI", ["RSI"]), ("ストキャス", ["ストキャス"])],
  "波動/周期": [("サイクル理論", ["サイクル"]), ("レフトトランスレーション", ["レフトトランス", "ライトトランス", "トランスレーション"]),
            ("フラクタル", ["フラクタル"]), ("エリオット", ["エリオット", "推進波", "修正波", "1波", "3波", "5波", "abc"])],
  "レンジ/ブレイク": [("レンジ/持ち合い", ["レンジ", "ボックス", "持ち合い", "保ち合い"]),
              ("上抜けブレイク", ["上抜け", "上ブレイク", "上放れ"]), ("下抜けブレイク", ["下抜け", "下ブレイク", "下放れ"]),
              ("ブレイク一般", ["ブレイク", "ブレイクアウト"])],
  "ローソク足": [("上髭", ["上髭", "上ヒゲ"]), ("下髭", ["下髭", "下ヒゲ", "たくり"]),
            ("包み足", ["包み足", "包足", "エンガルフ"]), ("坊主/大陽大陰", ["坊主", "大陽線", "大陰線"]), ("陽線/陰線一般", ["陽線", "陰線"])],
  "窓": [("CME窓", ["CME窓", "CME"]), ("窓埋め", ["窓埋め", "窓"])],
  "ボラ": [("ボラ拡大/収縮", ["ボラ", "煮詰ま", "収縮", "拡大"]), ("IVバンド/BB", ["IVバンド", "ボリンジャー", "BB"])],
 },
 "需給/レバ": {
  "建玉/OI": [("OI増", ["OI増", "建玉増", "OIが増"]), ("OI減", ["OI減", "建玉減", "OIが減"]), ("OI一般", ["OI", "建玉", "Open Interest", "未決済"])],
  "資金調達": [("FRマイナス", ["FR(-)", "FR（-）", "FRマイナス", "資金調達.*マイナス", "マイナス.*資金調達"]), ("FRプラス/一般", ["資金調達", "ファンディング", "FR", "Funding"])],
  "清算": [("ロング清算", ["ロング.*清算", "ロング.*精算", "ロング.*ロスカ"]), ("ショート清算", ["ショート.*清算", "ショート.*精算"]), ("清算一般", ["清算", "精算", "ロスカ", "リクイ"])],
  "ポジション偏り": [("ショートカバー/踏み上げ", ["ショートカバー", "踏み上げ", "踏み"]), ("ロング/ショート過多", ["ロング過多", "ショート過多", "LS比", "L/S"])],
 },
 "板/フロー": {
  "板読み": [("買い板/売り板", ["買い板", "売り板", "板"]), ("出来高", ["出来高", "VPVR"]), ("ヒートマップ", ["ヒートマップ", "注文量"])],
  "オプション": [("PCR", ["PCR", "プットコール"]), ("ピン/最大痛点", ["ピン", "最大痛", "Max Pain"]), ("OP一般", ["オプション", "プット", "コール"])],
 },
 "ファンダ": {
  "マクロ": [("金融政策/金利", ["金融政策", "日銀", "FOMC", "利上げ", "利下げ", "金利"]), ("経済指標", ["CPI", "消費者物価", "雇用統計", "PCE", "GDP"])],
  "規制/イベント": [("ETF", ["ETF"]), ("ネットワークイベント", ["ハードフォーク", "メインネット", "上海", "半減期", "アップグレード"]), ("規制", ["規制", "SEC", "提訴"])],
  "オンチェーン": [("取引所残高", ["取引所残高", "リザーブ"]), ("ハッシュレート", ["ハッシュレート"]), ("クジラ/大口", ["クジラ", "大口", "whale"]), ("オンチェーン一般", ["オンチェーン", "アクティブアドレス"])],
  "ステーブル": [("テザー発行", ["テザー", "USDT発行"]), ("デペグ", ["デペグ"]), ("ステーブル一般", ["USDC", "ステーブル"])],
 },
 "アノマリー": {
  "季節/暦": [("春節/旧正月", ["春節", "旧正月"]), ("納税/月末", ["納税", "月末", "月初"]), ("曜日", ["曜日", "週末", "月曜", "金曜"]),
           ("半減期サイクル", ["半減期"]), ("SQ/OP期限", ["SQ", "OP期限", "限月"]), ("季節一般", ["アノマリー", "成人式"])],
 },
 "地域差": {"プレミア": [("Coinbaseプレミア", ["Coinbaseプレミア", "プレミア"]), ("地域差一般", ["韓国", "Kimchi", "キムチ"])]},
}


def classify(text):
    """テキストから (大,中,小) を全部拾う"""
    out = []
    for big, mids in TAXO.items():
        for mid, smalls in mids.items():
            for sm, pats in smalls:
                if any(re.search(p, text) for p in pats):
                    out.append(f"{big}>{mid}>{sm}")
    return out


# ---- 価格パス ----
def load_bars(table):
    con = sqlite3.connect(f"file:{MK}?mode=ro", uri=True)
    if table == "market_btc_1d":
        rows = con.execute(
            "SELECT date, open, high, low, close FROM market_btc_1d").fetchall()
        bars = [(datetime.strptime(r[0][:10], "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000,
                 r[1], r[2], r[3], r[4]) for r in rows]
    else:
        rows = con.execute(
            f"SELECT ts_ms, open, high, low, close FROM {table}").fetchall()
        bars = [(r[0], r[1], r[2], r[3], r[4]) for r in rows]
    con.close()
    return sorted(bars)


TF_HORIZON_H = [  # (検出キーワード, 期限時間) — danjerの時間軸明示
    (["1分", "5分", "15分", "スキャル", "秒足"], 12),
    (["30分", "1時間", "時間足", "1h"], 72),
    (["4時間", "4h"], 120),
    (["日足", "デイリー"], 240),
    (["週足", "ウィークリー"], 720),
    (["月足", "マンスリー"], 1440),
]
# 大分類別の既定期限(時間軸明示が無いとき): テーマ系は長め
BIGCAT_DEFAULT_H = {
    "ファンダ": 480, "アノマリー": 480, "需給/レバ": 120,
    "板/フロー": 72, "地域差": 240, "テクニカル": 168,
}

_M = "([0-9０-９]{1,3}(?:[,，][0-9０-９]{3})*(?:\\.[0-9]+)?)"
DATE_PATTS = [
    (re.compile(r"(\d{1,2})月(\d{1,2})日"), "md"),
    (re.compile(r"(\d{1,2})月(上旬|初旬|中旬|下旬|末|頭)"), "mphase"),
    (re.compile(r"今週|週内|週末まで"), "thisweek"),
    (re.compile(r"来週"), "nextweek"),
    (re.compile(r"月末"), "monthend"),
    (re.compile(r"(\d{1,2})日後"), "ndays"),
]


def extract_deadline_h(text, post_dt):
    """danjerの記述から期限(時間)を抽出。無ければNone"""
    for patt, kind in DATE_PATTS:
        m = patt.search(text)
        if not m:
            continue
        try:
            if kind == "md":
                mo, da = int(m.group(1)), int(m.group(2))
                yr = post_dt.year + (1 if mo < post_dt.month - 1 else 0)
                tgt = datetime(yr, mo, da, tzinfo=timezone.utc)
            elif kind == "mphase":
                mo = int(m.group(1))
                da = {"上旬": 7, "初旬": 7, "頭": 5, "中旬": 15,
                      "下旬": 25, "末": 28}[m.group(2)]
                yr = post_dt.year + (1 if mo < post_dt.month - 1 else 0)
                tgt = datetime(yr, mo, da, tzinfo=timezone.utc)
            elif kind == "thisweek":
                return 120
            elif kind == "nextweek":
                return 264
            elif kind == "monthend":
                return 360
            elif kind == "ndays":
                return int(m.group(1)) * 24
            else:
                continue
            h = (tgt - post_dt).total_seconds() / 3600
            if 6 <= h <= 2160:  # 6h〜90日の妥当域
                return round(h)
        except Exception:
            continue
    return None


def horizon_h(text, bigcats, post_dt):
    dl = extract_deadline_h(text, post_dt)
    if dl:
        return dl, "明示期限"
    for kws, h in TF_HORIZON_H:
        if any(k in text for k in kws):
            return h, "時間軸"
    for bc in bigcats:
        if bc in BIGCAT_DEFAULT_H:
            return BIGCAT_DEFAULT_H[bc], f"大分類既定({bc})"
    return 168, "既定7日"


def _zen2han(s):
    return s.translate(str.maketrans("０１２３４５６７８９，", "0123456789,"))


def extract_levels(text, entry):
    """thesisから背になりうる価格レベルを抽出 (entryの0.3〜3倍に限定)"""
    cands = set()
    # 万ドル表記 (6.7万 / 5万 等)
    for m in re.finditer(r"([0-9０-９]+(?:\.[0-9]+)?)\s*万", text):
        try:
            cands.add(float(_zen2han(m.group(1))) * 10000)
        except Exception:
            pass
    # k/K表記 (67k / 110K)
    for m in re.finditer(r"([0-9０-９]+(?:\.[0-9]+)?)\s*[kK]", text):
        try:
            cands.add(float(_zen2han(m.group(1))) * 1000)
        except Exception:
            pass
    # 素の数値 (3-6桁、ドル/円/付近 等の near)
    for m in re.finditer(r"([0-9０-９]{4,6}(?:[,，][0-9]{3})*(?:\.[0-9]+)?)", text):
        try:
            cands.add(float(_zen2han(m.group(1)).replace(",", "")))
        except Exception:
            pass
    return sorted(v for v in cands if entry * 0.3 <= v <= entry * 3)


def excursion(bars1h, bars1d, start_ms, horizon_h, direction, levels):
    end_ms = start_ms + horizon_h * 3600 * 1000
    seg = [b for b in bars1h if start_ms <= b[0] <= end_ms]
    src = "1h"
    if len(seg) < 2:
        seg = [b for b in bars1d if start_ms <= b[0] <= end_ms]
        src = "1d"
    if len(seg) < 1:
        return None
    entry = seg[0][1]
    # 時系列で順行ピーク/逆行ボトムの「時刻(何本目)」を求める
    fav_i = adv_i = 0
    fav = adv = 0.0
    for i, b in enumerate(seg):
        hi, lo = b[2], b[3]
        if direction == "long":
            f = (hi - entry) / entry
            a = (lo - entry) / entry
        else:
            f = (entry - lo) / entry
            a = (entry - hi) / entry
        if f > fav:
            fav, fav_i = f, i
        if a < adv:
            adv, adv_i = a, i
    last = seg[-1][4]
    cret = ((last - entry) / entry) if direction == "long" else ((entry - last) / entry)
    # 背レベルが先に割れたか (逆行側で entry を挟んで一番近いレベルを stop とみなす)
    stop = None
    if levels:
        if direction == "long":
            below = [v for v in levels if v < entry]
            stop = max(below) if below else None
        else:
            above = [v for v in levels if v > entry]
            stop = min(above) if above else None
    breach_i = None
    if stop is not None:
        for i, b in enumerate(seg):
            if (direction == "long" and b[3] <= stop) or \
               (direction == "short" and b[2] >= stop):
                breach_i = i
                break
    return {
        "src": src, "bars": len(seg), "entry": round(entry, 1),
        "mfe_pct": round(fav * 100, 2), "mae_pct": round(adv * 100, 2),
        "close_ret_pct": round(cret * 100, 2),
        "順行先行": fav_i <= adv_i,  # 順行ピークが逆行ボトムより先か
        "fav_bar": fav_i, "adv_bar": adv_i,
        "stop_level": round(stop, 1) if stop else None,
        "背割れ": breach_i is not None,
        "背割れが順行前": (breach_i is not None and breach_i < fav_i),
    }


NONBTC = re.compile(r"ETH|イーサ|LTC|ライト|XRP|リップル|SOL|BNB|ADA|DOGE|アルト|ドル円|USDJPY|ナスダ|日経|S&P|ゴールド|XAU")


def prepare(n, offset):
    ai = sqlite3.connect(f"file:{AI}?mode=ro", uri=True)
    bars1h = load_bars("market_btc_1h")
    bars1d = load_bars("market_btc_1d")
    rows = ai.execute(
        "SELECT r.tweet_id, r.posted_at_utc, r.reading_json, b.extract_json "
        "FROM danjer_reading_prod r JOIN danjer_bottomup b ON r.tweet_id=b.tweet_id "
        "WHERE b.extracted=1 AND r.reading_json IS NOT NULL "
        "ORDER BY r.tweet_id").fetchall()
    out = []
    skipped = 0
    for tid, posted, rj, ej in rows:
        d = json.loads(rj)
        a = d.get("danjer_action") or {}
        direction = a.get("direction")
        if direction not in ("long", "short"):
            continue
        th = (d.get("danjer_thesis") or "").strip()
        if len(th) < 40:
            continue
        if NONBTC.search(th[:70]):  # 非BTCはオンデマンド対象=今回スキップ
            skipped += 1
            continue
        try:
            post_dt = datetime.fromisoformat(posted.replace("Z", "+00:00"))
            start_ms = post_dt.timestamp() * 1000
        except Exception:
            continue
        cats = classify(ej)
        bigcats = {c.split(">")[0] for c in cats}
        inval = str(d.get("invalidation") or "")
        hz, hz_src = horizon_h(th + " " + inval, bigcats, post_dt)
        probe = excursion(bars1h, bars1d, start_ms, hz, direction, [])
        if not probe:
            continue
        entry = probe["entry"]
        levels = extract_levels(th + " " + inval, entry)
        exc = excursion(bars1h, bars1d, start_ms, hz, direction, levels)
        # Mode B用: 投稿後の日足パス(背/目標レベルを目視決着できる) 90日分
        end90 = start_ms + 90 * 86400 * 1000
        daily = [[datetime.fromtimestamp(b[0] / 1000, timezone.utc).strftime("%m-%d"),
                  round(b[2]), round(b[3]), round(b[4])]
                 for b in bars1d if start_ms <= b[0] <= end90][:90]
        out.append({
            "tweet_id": str(tid), "date": posted[:10], "direction": direction,
            "timeframe_h": hz, "horizon_src": hz_src, "entry": entry,
            "thesis_full": th, "invalidation": inval,
            "market_snapshot": str(d.get("market_snapshot", ""))[:200],
            "auto_levels": levels, "小分類": cats,
            "path_window": exc, "daily_90d": daily,
        })
        if len(out) >= offset + n:
            break
    batch = out[offset:offset + n]
    Path("/tmp/score_batch.json").write_text(
        json.dumps(batch, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"バッチ {len(batch)}件 (非BTC除外 {skipped}件) → /tmp/score_batch.json")
    for b in batch:
        p = b["path"]
        order = "順行先行" if p["順行先行"] else "逆行先行"
        stop = (f"背{p['stop_level']}{'→割れ' if p['背割れ'] else '→堅持'}"
                f"{'(順行前に割れ=損切り済み)' if p['背割れが順行前'] else ''}"
                if p["stop_level"] else "背レベル不明")
        print(f"\n--- {b['tweet_id']} {b['date']} [{b['direction']}] "
              f"期限{b['horizon_h']}h({b['horizon_src']}) {p['src']}")
        print(f"  読み: {b['thesis'][:120]}")
        print(f"  小分類: {b['小分類']}")
        print(f"  検出レベル: {b['levels']}")
        print(f"  パス: 順行MFE{p['mfe_pct']:+}% 逆行MAE{p['mae_pct']:+}% 終値{p['close_ret_pct']:+}% "
              f"| {order}(順{p['fav_bar']}本目/逆{p['adv_bar']}本目) | {stop}")


def init_table():
    con = sqlite3.connect(AI)
    con.execute("""CREATE TABLE IF NOT EXISTS danjer_scores (
        tweet_id TEXT PRIMARY KEY, posted_date TEXT, direction TEXT,
        horizon_h INTEGER, small_cats TEXT,
        score INTEGER, verdict TEXT, basis TEXT,
        mfe_pct REAL, mae_pct REAL, close_ret_pct REAL,
        scored_by TEXT DEFAULT 'clerk_claude',
        scored_at TEXT DEFAULT (datetime('now')))""")
    con.commit()
    con.close()
    print("danjer_scores テーブル作成OK")


def stats():
    con = sqlite3.connect(f"file:{AI}?mode=ro", uri=True)
    n = con.execute("SELECT COUNT(*) FROM danjer_scores").fetchone()[0]
    avg = con.execute("SELECT ROUND(AVG(score),1) FROM danjer_scores WHERE verdict='採点可'").fetchone()[0]
    print(f"採点済み {n}件 / 採点可平均 {avg}点")
    con.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--prepare", action="store_true")
    ap.add_argument("--init", action="store_true")
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("--n", type=int, default=12)
    ap.add_argument("--offset", type=int, default=0)
    args = ap.parse_args()
    if args.init:
        init_table()
    elif args.prepare:
        prepare(args.n, args.offset)
    elif args.stats:
        stats()
