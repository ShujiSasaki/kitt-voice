#!/bin/bash
# UX改善1反映: self-test → uvicorn + relay_worker 再起動 (待機列可視化)
set -x
cd /Users/shuji/Desktop/kitt-voice

echo "=== self-tests ==="
python3 -m meeting_system.rooms_overview || exit 1
python3 scripts/relay_worker.py --self-test || exit 1

pkill -f "uvicorn meeting_system" || true
pkill -f "relay_worker.py" || true
sleep 2

nohup python3 -m uvicorn meeting_system.server:create_app --factory \
  --host 100.70.20.113 --port 8765 \
  --ssl-keyfile meeting_system/certs/key.pem \
  --ssl-certfile meeting_system/certs/cert.pem > /tmp/uvicorn_ux1.log 2>&1 &

nohup caffeinate -dimsu python3 scripts/relay_worker.py > /tmp/relay_worker_router.log 2>&1 &
sleep 6

tail -3 /tmp/uvicorn_ux1.log
head -3 /tmp/relay_worker_router.log
cat meeting_system/data/router_state.json 2>/dev/null
pgrep -fl "uvicorn|relay_worker"
