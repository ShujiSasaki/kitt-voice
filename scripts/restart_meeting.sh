#!/bin/bash
# 標準再起動スクリプト (2026-06-12): uvicorn + relay_worker を確実に1個ずつにする
# 背景: SSE接続を抱えた旧uvicornがTERMで終了せずゾンビ蓄積 (3個同時を実測)
#       → TERM → 3秒待ち → 残党をKILL の2段階に変更
set -x
cd /Users/shuji/Desktop/kitt-voice

echo "=== self-tests ==="
python3 -m meeting_system.validator_consensus || exit 1
python3 -m meeting_system.consensus_summary --self-test || exit 1
python3 scripts/relay_worker.py --self-test || exit 1

echo "=== stop (TERM -> KILL escalation) ==="
pkill -f "uvicorn meeting_system" || true
pkill -f "relay_worker.py" || true
sleep 3
pkill -9 -f "uvicorn meeting_system" || true
pkill -9 -f "relay_worker.py" || true
sleep 1

echo "=== start ==="
nohup python3 -m uvicorn meeting_system.server:create_app --factory \
  --host 100.70.20.113 --port 8765 \
  --ssl-keyfile meeting_system/certs/key.pem \
  --ssl-certfile meeting_system/certs/cert.pem > /tmp/uvicorn_meeting.log 2>&1 &
nohup caffeinate -dimsu python3 scripts/relay_worker.py > /tmp/relay_worker_router.log 2>&1 &
sleep 6

echo "=== verify ==="
tail -3 /tmp/uvicorn_meeting.log
head -2 /tmp/relay_worker_router.log
lsof -nP -i :8765 | grep LISTEN
pgrep -fl "uvicorn|relay_worker"
