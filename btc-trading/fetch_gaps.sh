#!/bin/bash
# 欠落期間をgallery-dl SearchTimelineで順次取得
# 単一キュー、rate limit共有

PROFILE="${1:-Profile 4}"
DIR_BASE="/tmp/gdl_search"
LOG="/tmp/fetch_gaps.log"

echo "$(date '+%H:%M') === Fetching gaps ===" | tee "$LOG"

# 各アカウントの欠落期間(月単位ジョブ)
declare -a JOBS=(
  # danjer 2023-07〜2024-04
  "smile_danjer|2023-07-01|2023-08-01"
  "smile_danjer|2023-08-01|2023-09-01"
  "smile_danjer|2023-09-01|2023-10-01"
  "smile_danjer|2023-10-01|2023-11-01"
  "smile_danjer|2023-11-01|2023-12-01"
  "smile_danjer|2023-12-01|2024-01-01"
  "smile_danjer|2024-01-01|2024-02-01"
  "smile_danjer|2024-02-01|2024-03-01"
  "smile_danjer|2024-03-01|2024-04-01"
  "smile_danjer|2024-04-01|2024-05-01"
  # BobLoukas 2021-05〜2025-02
  "BobLoukas|2021-05-01|2021-08-01"
  "BobLoukas|2021-08-01|2021-11-01"
  "BobLoukas|2021-11-01|2022-02-01"
  "BobLoukas|2022-02-01|2022-05-01"
  "BobLoukas|2022-05-01|2022-08-01"
  "BobLoukas|2022-08-01|2022-11-01"
  "BobLoukas|2022-11-01|2023-02-01"
  "BobLoukas|2023-02-01|2023-05-01"
  "BobLoukas|2023-05-01|2023-08-01"
  "BobLoukas|2023-08-01|2023-11-01"
  "BobLoukas|2023-11-01|2024-02-01"
  "BobLoukas|2024-02-01|2024-05-01"
  "BobLoukas|2024-05-01|2024-08-01"
  "BobLoukas|2024-08-01|2024-11-01"
  "BobLoukas|2024-11-01|2025-02-01"
  # Checkmatey 2020-12〜2025-07
  "_Checkmatey_|2020-12-01|2021-03-01"
  "_Checkmatey_|2021-03-01|2021-06-01"
  "_Checkmatey_|2021-06-01|2021-09-01"
  "_Checkmatey_|2021-09-01|2021-12-01"
  "_Checkmatey_|2021-12-01|2022-03-01"
  "_Checkmatey_|2022-03-01|2022-06-01"
  "_Checkmatey_|2022-06-01|2022-09-01"
  "_Checkmatey_|2022-09-01|2022-12-01"
  "_Checkmatey_|2022-12-01|2023-03-01"
  "_Checkmatey_|2023-03-01|2023-06-01"
  "_Checkmatey_|2023-06-01|2023-09-01"
  "_Checkmatey_|2023-09-01|2023-12-01"
  "_Checkmatey_|2023-12-01|2024-03-01"
  "_Checkmatey_|2024-03-01|2024-06-01"
  "_Checkmatey_|2024-06-01|2024-09-01"
  "_Checkmatey_|2024-09-01|2024-12-01"
  "_Checkmatey_|2024-12-01|2025-03-01"
  "_Checkmatey_|2025-03-01|2025-07-01"
  # LynAlden 2021-04〜2025-05
  "LynAldenContact|2021-04-01|2021-07-01"
  "LynAldenContact|2021-07-01|2021-10-01"
  "LynAldenContact|2021-10-01|2022-01-01"
  "LynAldenContact|2022-01-01|2022-04-01"
  "LynAldenContact|2022-04-01|2022-07-01"
  "LynAldenContact|2022-07-01|2022-10-01"
  "LynAldenContact|2022-10-01|2023-01-01"
  "LynAldenContact|2023-01-01|2023-04-01"
  "LynAldenContact|2023-04-01|2023-07-01"
  "LynAldenContact|2023-07-01|2023-10-01"
  "LynAldenContact|2023-10-01|2024-01-01"
  "LynAldenContact|2024-01-01|2024-04-01"
  "LynAldenContact|2024-04-01|2024-07-01"
  "LynAldenContact|2024-07-01|2024-10-01"
  "LynAldenContact|2024-10-01|2025-01-01"
  "LynAldenContact|2025-01-01|2025-05-01"
  # PeterBrandt 2021-03〜2025-09
  "PeterLBrandt|2021-03-01|2021-06-01"
  "PeterLBrandt|2021-06-01|2021-09-01"
  "PeterLBrandt|2021-09-01|2021-12-01"
  "PeterLBrandt|2021-12-01|2022-03-01"
  "PeterLBrandt|2022-03-01|2022-06-01"
  "PeterLBrandt|2022-06-01|2022-09-01"
  "PeterLBrandt|2022-09-01|2022-12-01"
  "PeterLBrandt|2022-12-01|2023-03-01"
  "PeterLBrandt|2023-03-01|2023-06-01"
  "PeterLBrandt|2023-06-01|2023-09-01"
  "PeterLBrandt|2023-09-01|2023-12-01"
  "PeterLBrandt|2023-12-01|2024-03-01"
  "PeterLBrandt|2024-03-01|2024-06-01"
  "PeterLBrandt|2024-06-01|2024-09-01"
  "PeterLBrandt|2024-09-01|2025-01-01"
  "PeterLBrandt|2025-01-01|2025-09-01"
)

TOTAL_JOBS=${#JOBS[@]}
echo "Total jobs: $TOTAL_JOBS" | tee -a "$LOG"

for i in "${!JOBS[@]}"; do
  IFS='|' read -r HANDLE SINCE UNTIL <<< "${JOBS[$i]}"
  DIR="${DIR_BASE}_${HANDLE}"
  mkdir -p "$DIR"

  QUERY="from:${HANDLE} since:${SINCE} until:${UNTIL}"
  URL="https://x.com/search?q=$(python3 -c "import urllib.parse; print(urllib.parse.quote('${QUERY}'))")&f=live"

  echo "$(date '+%H:%M') [$((i+1))/$TOTAL_JOBS] $HANDLE: $SINCE → $UNTIL" | tee -a "$LOG"

  gallery-dl --cookies-from-browser "chrome:${PROFILE}" --no-download --write-metadata -d "$DIR" "$URL" >> "$LOG" 2>&1

  COUNT=$(find "$DIR" -name "*.json" | wc -l | tr -d ' ')
  echo "  Total files: $COUNT" | tee -a "$LOG"

  sleep 3
done

echo "$(date '+%H:%M') === All gaps done ===" | tee -a "$LOG"
