#!/bin/bash
# R65反映: uvicorn再起動 (is_processing API) + relay_workerルーター再起動 (router_state書出し)
set -x
cd /Users/shuji/Desktop/kitt-voice

pkill -f "uvicorn meeting_system" || true
pkill -f "relay_worker.py" || true
sleep 2

nohup python3 -m uvicorn meeting_system.server:create_app --factory \
  --host 100.70.20.113 --port 8765 \
  --ssl-keyfile meeting_system/certs/key.pem \
  --ssl-certfile meeting_system/certs/cert.pem > /tmp/uvicorn_r65.log 2>&1 &

nohup caffeinate -dimsu python3 scripts/relay_worker.py > /tmp/relay_worker_router.log 2>&1 &
sleep 6

echo "=== uvicorn ==="
tail -4 /tmp/uvicorn_r65.log
echo "=== worker ==="
head -3 /tmp/relay_worker_router.log
echo "=== router_state.json (R65書出し確認) ==="
cat meeting_system/data/router_state.json 2>/dev/null || echo "(まだ未生成 — worker初回pollで生成)"
echo "=== processes ==="
pgrep -fl "uvicorn|relay_worker"
