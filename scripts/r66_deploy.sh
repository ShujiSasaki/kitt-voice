#!/bin/bash
# R66反映: uvicorn + relay_worker 再起動 (max_loops到達通知)
set -x
cd /Users/shuji/Desktop/kitt-voice

pkill -f "uvicorn meeting_system" || true
pkill -f "relay_worker.py" || true
sleep 2

nohup python3 -m uvicorn meeting_system.server:create_app --factory \
  --host 100.70.20.113 --port 8765 \
  --ssl-keyfile meeting_system/certs/key.pem \
  --ssl-certfile meeting_system/certs/cert.pem > /tmp/uvicorn_r66.log 2>&1 &

nohup caffeinate -dimsu python3 scripts/relay_worker.py > /tmp/relay_worker_router.log 2>&1 &
sleep 6

echo "=== uvicorn ==="
tail -3 /tmp/uvicorn_r66.log
echo "=== worker ==="
head -3 /tmp/relay_worker_router.log
echo "=== processes ==="
pgrep -fl "uvicorn|relay_worker"
