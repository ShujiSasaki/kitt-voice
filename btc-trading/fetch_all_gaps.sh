#!/bin/bash
# 全アカウントの欠損期間をSearchTimelineで埋める
# バックグラウンドで放置用

cd "$(dirname "$0")"

echo "=== Gap Fill Start: $(date) ==="

# BobLoukas: 2021-05 〜 2024-12
echo ">>> BobLoukas 2021-05→2024-12"
python3 -u fetch_fast_v2.py BobLoukas 30 2021-05-01 2024-12-01
echo ">>> BobLoukas done: $(sqlite3 x_tweets.db "SELECT COUNT(*) FROM tweets WHERE screen_name='BobLoukas'") tweets"
echo ""

# _Checkmatey_: 2020-12 〜 2025-04
echo ">>> _Checkmatey_ 2020-12→2025-04"
python3 -u fetch_fast_v2.py _Checkmatey_ 30 2020-12-01 2025-05-01
echo ">>> _Checkmatey_ done: $(sqlite3 x_tweets.db "SELECT COUNT(*) FROM tweets WHERE screen_name='_Checkmatey_'") tweets"
echo ""

# LynAldenContact: 2021-04 〜 2025-05
echo ">>> LynAldenContact 2021-04→2025-05"
python3 -u fetch_fast_v2.py LynAldenContact 30 2021-04-01 2025-06-01
echo ">>> LynAldenContact done: $(sqlite3 x_tweets.db "SELECT COUNT(*) FROM tweets WHERE screen_name='LynAldenContact'") tweets"
echo ""

# PeterLBrandt: 2021-03 〜 2025-09
echo ">>> PeterLBrandt 2021-03→2025-09"
python3 -u fetch_fast_v2.py PeterLBrandt 30 2021-03-01 2025-10-01
echo ">>> PeterLBrandt done: $(sqlite3 x_tweets.db "SELECT COUNT(*) FROM tweets WHERE screen_name='PeterLBrandt'") tweets"
echo ""

# smile_danjer: 2020-02 〜 2024-04 (散発的な穴)
echo ">>> smile_danjer 2020-02→2024-04"
python3 -u fetch_fast_v2.py smile_danjer 30 2020-02-01 2024-05-01
echo ">>> smile_danjer done: $(sqlite3 x_tweets.db "SELECT COUNT(*) FROM tweets WHERE screen_name='smile_danjer'") tweets"
echo ""

# CryptoHayes: 2020-10 〜 2022-05 (散発的な穴)
echo ">>> CryptoHayes 2020-10→2022-05"
python3 -u fetch_fast_v2.py CryptoHayes 30 2020-10-01 2022-06-01
echo ">>> CryptoHayes done: $(sqlite3 x_tweets.db "SELECT COUNT(*) FROM tweets WHERE screen_name='CryptoHayes'") tweets"
echo ""

# ronpochi: 2020-10 〜 2025-11 (検索除外だが試みる)
echo ">>> 4HpO4Q9Dz3CWkhV 2020-10→2025-11"
python3 -u fetch_fast_v2.py 4HpO4Q9Dz3CWkhV 30 2020-10-01 2025-12-01
echo ">>> 4HpO4Q9Dz3CWkhV done: $(sqlite3 x_tweets.db "SELECT COUNT(*) FROM tweets WHERE screen_name='4HpO4Q9Dz3CWkhV'") tweets"
echo ""

echo "=== Gap Fill Complete: $(date) ==="
echo "=== Final DB Status ==="
sqlite3 x_tweets.db "SELECT screen_name, COUNT(*) FROM tweets GROUP BY screen_name ORDER BY COUNT(*) DESC"
