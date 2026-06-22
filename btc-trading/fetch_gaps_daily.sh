#!/bin/bash
# 欠落期間をgallery-dl SearchTimelineで日単位取得
# 単一キュー、直列実行

PROFILE="${1:-Profile 4}"
LOG="/tmp/fetch_gaps_daily.log"

echo "$(date '+%H:%M') === Daily gap fetch ===" | tee "$LOG"

# アカウントごとの欠落期間
declare -A GAPS
GAPS[smile_danjer]="2023-07-01:2024-05-01"
GAPS[BobLoukas]="2021-05-01:2025-03-01"
GAPS[_Checkmatey_]="2020-12-01:2025-08-01"
GAPS[LynAldenContact]="2021-04-01:2025-06-01"
GAPS[PeterLBrandt]="2021-03-01:2025-10-01"

for HANDLE in smile_danjer BobLoukas _Checkmatey_ LynAldenContact PeterLBrandt; do
  IFS=':' read -r START END <<< "${GAPS[$HANDLE]}"
  DIR="/tmp/gdl_search_${HANDLE}"
  mkdir -p "$DIR"

  echo "$(date '+%H:%M') === $HANDLE: $START → $END ===" | tee -a "$LOG"

  current="$START"
  while [[ "$current" < "$END" ]]; do
    next=$(date -j -f "%Y-%m-%d" -v+1d "$current" "+%Y-%m-%d" 2>/dev/null || date -d "$current + 1 day" "+%Y-%m-%d")

    QUERY="from:${HANDLE} since:${current} until:${next}"
    URL="https://x.com/search?q=$(python3 -c "import urllib.parse; print(urllib.parse.quote('${QUERY}'))")&f=live"

    gallery-dl --cookies-from-browser "chrome:${PROFILE}" --no-download --write-metadata -d "$DIR" "$URL" >> "$LOG" 2>&1

    current="$next"
  done

  COUNT=$(find "$DIR" -name "*.json" | wc -l | tr -d ' ')
  echo "$(date '+%H:%M') $HANDLE done: $COUNT files" | tee -a "$LOG"
done

echo "$(date '+%H:%M') === All done ===" | tee -a "$LOG"
