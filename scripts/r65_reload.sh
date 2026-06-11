#!/bin/bash
# R65.1反映: uvicornのみ再起動 (no-cache headers + ui_version)。workerは触らない
set -x
cd /Users/shuji/Desktop/kitt-voice
pkill -f "uvicorn meeting_system" || true
sleep 2
nohup python3 -m uvicorn meeting_system.server:create_app --factory \
  --host 100.70.20.113 --port 8765 \
  --ssl-keyfile meeting_system/certs/key.pem \
  --ssl-certfile meeting_system/certs/cert.pem > /tmp/uvicorn_r65.log 2>&1 &
sleep 5
tail -3 /tmp/uvicorn_r65.log
pgrep -fl uvicorn
