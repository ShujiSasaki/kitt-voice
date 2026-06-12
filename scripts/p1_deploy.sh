#!/bin/bash
# P1反映 (包括指示): self-test 3本 → uvicornのみ再起動 (workerはP1で変更なし)
set -x
cd /Users/shuji/Desktop/kitt-voice

echo "=== self-tests ==="
python3 -m meeting_system.validator_consensus || exit 1
python3 -m meeting_system.consensus_summary --self-test || exit 1
python3 scripts/relay_worker.py --self-test || exit 1

pkill -f "uvicorn meeting_system" || true
sleep 2
nohup python3 -m uvicorn meeting_system.server:create_app --factory \
  --host 100.70.20.113 --port 8765 \
  --ssl-keyfile meeting_system/certs/key.pem \
  --ssl-certfile meeting_system/certs/cert.pem > /tmp/uvicorn_p1.log 2>&1 &
sleep 5
tail -3 /tmp/uvicorn_p1.log
pgrep -fl "uvicorn|relay_worker"
