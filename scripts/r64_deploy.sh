#!/bin/bash
# R64反映: uvicorn再起動 (R63.1 ▶再開fix + R64 合意まとめhook) + E2Eテスト
set -x
cd /Users/shuji/Desktop/kitt-voice
pkill -f "uvicorn meeting_system" || true
sleep 2
nohup python3 -m uvicorn meeting_system.server:create_app --factory \
  --host 100.70.20.113 --port 8765 \
  --ssl-keyfile meeting_system/certs/key.pem \
  --ssl-certfile meeting_system/certs/cert.pem > /tmp/uvicorn_r64.log 2>&1 &
sleep 5
echo "=== uvicorn log ==="
tail -5 /tmp/uvicorn_r64.log
echo "=== E2E: R64合意自体の合意まとめを自動生成 (検収テストケース) ==="
python3 -m meeting_system.consensus_summary test_room_001 --force
echo "=== process ==="
pgrep -fl uvicorn
