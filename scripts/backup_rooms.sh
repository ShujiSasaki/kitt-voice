#!/usr/bin/env bash
# backup_rooms — R57 Phase E: meeting_system data backup
#
# Usage:
#   scripts/backup_rooms.sh [BACKUP_DIR]
#
# 既定 BACKUP_DIR = $HOME/Desktop/kitt-voice/meeting_system/archive/backups/
#
# 圧縮: data/projects/ + data/timeline.jsonl + data/notifications.json
# 命名: rooms_backup_YYYYMMDD_HHMMSS.tar.gz
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MS_DIR="$REPO_ROOT/meeting_system"
DATA_DIR="$MS_DIR/data"
BACKUP_DIR="${1:-$MS_DIR/archive/backups}"

if [[ ! -d "$DATA_DIR" ]]; then
  echo "❌ data dir not found: $DATA_DIR" >&2
  exit 2
fi

mkdir -p "$BACKUP_DIR"
TS="$(date +%Y%m%d_%H%M%S)"
OUT="$BACKUP_DIR/rooms_backup_$TS.tar.gz"

# 含める対象: projects + timeline.jsonl + notifications.json
INCLUDES=()
[[ -d "$DATA_DIR/projects" ]] && INCLUDES+=("data/projects")
[[ -f "$DATA_DIR/timeline.jsonl" ]] && INCLUDES+=("data/timeline.jsonl")
[[ -f "$DATA_DIR/notifications.json" ]] && INCLUDES+=("data/notifications.json")
[[ -f "$DATA_DIR/validator_log.jsonl" ]] && INCLUDES+=("data/validator_log.jsonl")

if [[ ${#INCLUDES[@]} -eq 0 ]]; then
  echo "⚠ nothing to backup (empty data dir)" >&2
  exit 0
fi

cd "$MS_DIR"
tar -czf "$OUT" "${INCLUDES[@]}"
SIZE=$(du -h "$OUT" | awk '{print $1}')
echo "✅ backup: $OUT ($SIZE)"
echo "   files: ${INCLUDES[*]}"
