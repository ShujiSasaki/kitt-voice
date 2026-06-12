#!/bin/bash
# stale-dup guard反映: self-test → relay_workerのみ再起動 (uvicorn変更なし)
set -x
cd /Users/shuji/Desktop/kitt-voice
python3 scripts/relay_worker.py --self-test || exit 1
pkill -f "relay_worker.py" || true
sleep 2
nohup caffeinate -dimsu python3 scripts/relay_worker.py > /tmp/relay_worker_router.log 2>&1 &
sleep 4
head -3 /tmp/relay_worker_router.log
pgrep -fl relay_worker
