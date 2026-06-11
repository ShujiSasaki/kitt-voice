#!/bin/bash
# R63: 旧worker(固定room)停止 → 自動roomルーター起動
set -x
pkill -f "relay_worker.py" || true
sleep 2
cd /Users/shuji/Desktop/kitt-voice
nohup caffeinate -dimsu python3 scripts/relay_worker.py > /tmp/relay_worker_router.log 2>&1 &
sleep 5
echo "=== router log (先頭) ==="
head -20 /tmp/relay_worker_router.log
echo "=== worker process ==="
pgrep -fl relay_worker.py
