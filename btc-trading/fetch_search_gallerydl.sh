#!/bin/bash
# gallery-dl SearchTimeline 週単位取得
# Usage: bash fetch_search_gallerydl.sh <handle> <start_date> <end_date>
# Example: bash fetch_search_gallerydl.sh smile_danjer 2025-10-01 2026-05-13

HANDLE="$1"
START="$2"
END="$3"
PROFILE="${4:-Profile 4}"
DIR="/tmp/gdl_search_${HANDLE}"
LOG="/tmp/gdl_search_${HANDLE}.log"

if [ -z "$HANDLE" ] || [ -z "$START" ] || [ -z "$END" ]; then
  echo "Usage: $0 <handle> <start_date> <end_date> [chrome_profile]"
  exit 1
fi

mkdir -p "$DIR"
echo "$(date '+%H:%M') Starting SearchTimeline for @${HANDLE}: ${START} → ${END}" | tee -a "$LOG"

# 週単位で分割
current="$START"
while [[ "$current" < "$END" ]]; do
  # 7日後
  next=$(date -j -f "%Y-%m-%d" -v+7d "$current" "+%Y-%m-%d" 2>/dev/null || date -d "$current + 7 days" "+%Y-%m-%d")
  if [[ "$next" > "$END" ]]; then
    next="$END"
  fi

  QUERY="from:${HANDLE} since:${current} until:${next}"
  URL="https://x.com/search?q=$(python3 -c "import urllib.parse; print(urllib.parse.quote('${QUERY}'))")&f=live"

  echo "$(date '+%H:%M') Job: ${current} → ${next}" | tee -a "$LOG"

  gallery-dl --cookies-from-browser "chrome:${PROFILE}" --no-download --write-metadata -d "$DIR" "$URL" >> "$LOG" 2>&1

  # 件数確認
  COUNT=$(find "$DIR" -name "*.json" -newer "$LOG" 2>/dev/null | wc -l | tr -d ' ')
  echo "  Files: $COUNT" | tee -a "$LOG"

  current="$next"
  sleep 5
done

echo "$(date '+%H:%M') Done: @${HANDLE}" | tee -a "$LOG"
TOTAL=$(find "$DIR" -name "*.json" | wc -l | tr -d ' ')
echo "Total files: $TOTAL" | tee -a "$LOG"
