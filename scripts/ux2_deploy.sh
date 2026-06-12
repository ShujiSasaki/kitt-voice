#!/bin/bash
# UX改善2反映: uvicornのみ再起動 (activate未読クリア)。worker変更なし
set -x
cd /Users/shuji/Desktop/kitt-voice
pkill -f "uvicorn meeting_system" || true
sleep 2
nohup python3 -m uvicorn meeting_system.server:create_app --factory \
  --host 100.70.20.113 --port 8765 \
  --ssl-keyfile meeting_system/certs/key.pem \
  --ssl-certfile meeting_system/certs/cert.pem > /tmp/uvicorn_ux2.log 2>&1 &
sleep 5
tail -3 /tmp/uvicorn_ux2.log
pgrep -fl "uvicorn|relay_worker"
