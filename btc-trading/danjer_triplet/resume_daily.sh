#!/bin/bash
# danjer本番 残り再開 (OS cron用・Claude非依存) — 2026-06-16
# 毎朝8:07に走り、未完なら --resume で残りを処理。13,671件完走したら
# 自身のcron登録を削除して二度と走らないようにする(自己クリーンアップ)。
set -u
cd /Users/shuji/Desktop/kitt-voice || exit 1
DB=btc-trading/btc_trading_ai.db
LOG=/tmp/danjer_prod_resume.log
MARK=btc-trading/danjer_triplet/PROD_DONE

# 既に完走マークがあれば何もしない
[ -f "$MARK" ] && exit 0

N=$(python3 -c "import sqlite3;print(sqlite3.connect('$DB').execute('SELECT COUNT(*) FROM danjer_reading_prod').fetchone()[0])" 2>/dev/null || echo 0)
echo "[$(date '+%F %T')] resume開始 現在${N}/13671" >> "$LOG"

if [ "$N" -ge 13671 ]; then
    touch "$MARK"
else
    python3 btc-trading/danjer_triplet/production_run.py --all --resume \
        --workers 4 --out btc-trading/danjer_triplet/production_full_report.json \
        >> "$LOG" 2>&1
    N=$(python3 -c "import sqlite3;print(sqlite3.connect('$DB').execute('SELECT COUNT(*) FROM danjer_reading_prod').fetchone()[0])" 2>/dev/null || echo 0)
fi

echo "[$(date '+%F %T')] resume後 ${N}/13671" >> "$LOG"

# 完走したらcron登録を自己削除 + マーク
if [ "$N" -ge 13671 ]; then
    touch "$MARK"
    crontab -l 2>/dev/null | grep -v "resume_daily.sh" | crontab -
    echo "[$(date '+%F %T')] 完走 → cron自己削除済み" >> "$LOG"
fi
