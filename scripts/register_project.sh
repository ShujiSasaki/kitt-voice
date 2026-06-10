#!/usr/bin/env bash
# register_project — R60 ② プロジェクト登録 (3者合意 R59 loop=5)
#
# Usage:
#   scripts/register_project.sh <project_id> <room_id> [tool] [repo_path]
#
# Example:
#   cd ~/Desktop/kitt-voice
#   scripts/register_project.sh kitt_main test_room_001 claude_code "$PWD"
set -euo pipefail

PROJECT_ID="${1:-}"
ROOM_ID="${2:-}"
TOOL="${3:-manual}"
REPO_PATH="${4:-$PWD}"
SERVER="${SERVER:-https://100.70.20.113:8765}"

if [[ -z "$PROJECT_ID" || -z "$ROOM_ID" ]]; then
  echo "Usage: $0 <project_id> <room_id> [tool] [repo_path]" >&2
  exit 1
fi

CSRF=$(curl -k -s "$SERVER/api/csrf-token" | python3 -c "import json,sys; print(json.load(sys.stdin)['token'])")
curl -k -s -X POST "$SERVER/api/projects" \
  -H "X-CSRF-Token: $CSRF" -H "Content-Type: application/json" \
  -d "{\"project_id\":\"$PROJECT_ID\",\"room_id\":\"$ROOM_ID\",\"tool\":\"$TOOL\",\"repo_path\":\"$REPO_PATH\"}"
echo ""
