#!/bin/bash
# UserTweets v3を繰り返し実行 - cursor保存→再開の自動ループ
# Usage: ./fetch_loop.sh <handle> [max_iterations]

HANDLE=${1:-BobLoukas}
MAX=${2:-100}

echo "=== Fetch Loop: $HANDLE (max $MAX iterations) ==="

cd "$(dirname "$0")"

for i in $(seq 1 $MAX); do
    echo ""
    echo "--- Iteration $i/$MAX ($(date '+%H:%M:%S')) ---"

    BEFORE=$(sqlite3 x_tweets.db "SELECT COUNT(*) FROM tweets WHERE screen_name='$HANDLE'")

    python3 -u fetch_user_tweets_v3.py "$HANDLE" 2>&1

    AFTER=$(sqlite3 x_tweets.db "SELECT COUNT(*) FROM tweets WHERE screen_name='$HANDLE'")
    DIFF=$((AFTER - BEFORE))

    echo "  Iteration $i result: $BEFORE → $AFTER (+$DIFF)"

    if [ "$DIFF" -eq 0 ]; then
        # 3回連続0件なら終了
        ZERO_COUNT=$((${ZERO_COUNT:-0} + 1))
        echo "  Zero new ($ZERO_COUNT consecutive)"
        if [ "$ZERO_COUNT" -ge 3 ]; then
            echo "  3 consecutive zero results, stopping."
            break
        fi
    else
        ZERO_COUNT=0
    fi

    # 429待ち: 次のrunまで60秒待つ
    echo "  Waiting 60s before next iteration..."
    sleep 60
done

FINAL=$(sqlite3 x_tweets.db "SELECT COUNT(*) FROM tweets WHERE screen_name='$HANDLE'")
echo ""
echo "=== Loop complete: $HANDLE DB=$FINAL ==="
