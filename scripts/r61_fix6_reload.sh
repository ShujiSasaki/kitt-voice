#!/usr/bin/env bash
# R61 fix #6 最終ゲート: uvicorn再起動 (fix #6 メモリ反映) + Live E2E準備
set -e
cd /Users/shuji/Desktop/kitt-voice

echo "=== 1. uvicorn 再起動 (fix #6 reload) ==="
pkill -f "uvicorn meeting_system" || true
sleep 2
nohup python3 -m uvicorn meeting_system.server:create_app --factory \
  --host 100.70.20.113 --port 8765 \
  --ssl-keyfile meeting_system/certs/key.pem \
  --ssl-certfile meeting_system/certs/cert.pem > /tmp/uvicorn_fix6.log 2>&1 &
sleep 4
tail -3 /tmp/uvicorn_fix6.log

echo "=== 2. resume_relay (worker再開) ==="
CSRF=$(curl -k -s https://100.70.20.113:8765/api/csrf-token | python3 -c "import json,sys; print(json.load(sys.stdin)['token'])")
curl -k -s -X POST https://100.70.20.113:8765/api/rooms/test_room_001/resume_relay \
  -H "X-CSRF-Token: $CSRF" -H "Content-Type: application/json" -d '{}'
echo ""

echo "=== 3. Live E2E 証跡注入準備完了 ==="
echo "worker が次のpollで再開 → 3者が再びexternal_wait判定を出した時、"
echo "fix #6 (新コード) が即 state.status を書き、 worker が静かに止まればLive E2E合格"
