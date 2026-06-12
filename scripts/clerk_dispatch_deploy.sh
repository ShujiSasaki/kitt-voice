#!/bin/bash
# clerk_dispatch機構 デプロイ + danjer v2 リライト一括実行 (2026-06-12)
# 1) self-test → 2) サーバ+worker再起動 → 3) FR取得 → 4) proto v2再構築
set -u
cd /Users/shuji/Desktop/kitt-voice

echo "=== [1/4] self-tests ==="
python3 -m meeting_system.clerk_dispatch --self-test || exit 1
python3 -c "import ast; ast.parse(open('meeting_system/server.py').read()); print('server.py syntax OK')" || exit 1
python3 -c "import ast; ast.parse(open('scripts/relay_worker.py').read()); print('relay_worker.py syntax OK')" || exit 1

echo "=== [2/4] meeting_system 再起動 (canonical) ==="
bash scripts/restart_meeting.sh || exit 1

echo "=== [3/4] Binance FR全履歴取得 (無料・キー不要) ==="
python3 btc-trading/danjer_triplet/fetch_funding_rate.py || exit 1

echo "=== [4/4] danjer proto v2 再構築 ==="
python3 btc-trading/danjer_triplet/build_prototype_v2.py || exit 1

echo ""
echo "ALL DONE — 次: ai_extraction_input.json を事務Claudeがラベリング"
