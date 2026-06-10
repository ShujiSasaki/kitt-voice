#!/usr/bin/env bash
# restore_rooms — R57 Phase E: meeting_system data restore
#
# Usage:
#   scripts/restore_rooms.sh BACKUP_TARBALL [--force]
#
# 既定: data/ が空でない場合は abort (--force で上書き許可)
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 BACKUP_TARBALL [--force]" >&2
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MS_DIR="$REPO_ROOT/meeting_system"
DATA_DIR="$MS_DIR/data"
TARBALL="$1"
FORCE="${2:-}"

if [[ ! -f "$TARBALL" ]]; then
  echo "❌ backup file not found: $TARBALL" >&2
  exit 2
fi

# 既存data がある場合は確認
if [[ -d "$DATA_DIR/projects" && -n "$(ls -A "$DATA_DIR/projects" 2>/dev/null)" ]]; then
  if [[ "$FORCE" != "--force" ]]; then
    echo "❌ data/projects/ not empty. Use --force to overwrite." >&2
    echo "   current rooms:" >&2
    ls "$DATA_DIR/projects" | head -10 | sed 's/^/     /' >&2
    exit 3
  fi
  echo "⚠ --force: overwriting existing data/"
fi

cd "$MS_DIR"
tar -xzf "$TARBALL"
echo "✅ restored from: $TARBALL"
ls "$DATA_DIR" 2>/dev/null | head -10 | sed 's/^/  /'
