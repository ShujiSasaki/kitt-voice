#!/usr/bin/env bash
# R61 fix #6 デプロイ一括 (smoke test → commit → push → 完了報告inject → worker再起動)
set -e
cd /Users/shuji/Desktop/kitt-voice

echo "=== 1. smoke test ==="
python3 -m meeting_system.tests.test_smoke 2>&1 | tail -3

echo "=== 2. commit + push ==="
git add meeting_system/validator_consensus.py scripts/r61_fix6_deploy.sh
git commit -m "R61 fix #6: 3者全員 blocked/external_wait で state.status 書込 (3者合意4巡一致)

3者会議 (loop 3-6、 4巡連続一致) の行レベル指示どおり:
- validator_consensus.py mark_consensus_if_established に追加
- 最新loopの3者判定が全員 blocked/external_wait なら state.status へ永続化
- blocked優先 (同数時)、 既にstop状態ならskip
- relay_worker は R59 Q3経路で auto-pause → 静かに止まって▶再開で戻る UX 完成

発言Claude R6: パース欠落ではなく書き込み欠落でした、 の最終配線

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git push 2>&1 | tail -2

echo "=== 3. grep証跡 (3者要求) ==="
grep -n "fix #6" meeting_system/validator_consensus.py

echo "=== 4. 完了報告 inject ==="
python3 scripts/post_completion_report.py \
  --room test_room_001 \
  --topic "R61 fix #6 実装完了 (3者要求の status永続化配線)" \
  --grep "fix #6" \
  --risks "なし"

echo "=== 5. worker再起動 ==="
pkill -f relay_worker || true
sleep 2
rm -f meeting_system/data/projects/test_room_001/relay_heartbeat.json
nohup caffeinate -dimsu python3 scripts/relay_worker.py \
  --room test_room_001 --cdp-port 9222 \
  --base /Users/shuji/Desktop/kitt-voice/meeting_system \
  --server https://100.70.20.113:8765 \
  --poll 3 --max-loops 6 > /tmp/relay_worker_fix6.log 2>&1 &
echo "worker PID=$!"
sleep 15
echo "=== 6. worker log ==="
cat /tmp/relay_worker_fix6.log
