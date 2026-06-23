#!/bin/bash
# サイクル末 → 次バージョン Kaggle push 統合スクリプト
#
# 3者合意 (2026-06-24): サイクル末で 教師化+データ生成+Kaggle push を1コマンド。
#
# 使い方:
#   cd btc-trading/ai_growth
#   bash cycle_to_next_version.sh
#
# 前提:
# - 50-100件 ラベル付け完了
# - eval/labels_vN.jsonl が存在
# - Kaggle CLI が ~/.kaggle/access_token 設定済
# - /tmp/kaggle_planA/ に kaggle_planA.ipynb + kernel-metadata.json 存在
#
# 処理 (6ステップ):
# 1. 現バージョン確認
# 2. 失敗ケース → 教師データ化 (teacher/failure_to_teacher.py)
# 3. 正例 → 教師データ追加 (teacher/success_to_teacher.py)
# 4. 7条件 見直しレポート生成 (teacher/stop_rules_update.py)
# 5. v(N+1) 学習データ生成 (training/data_builder.py)
# 6. Kaggle に v(N+1) として push

set -e
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

VENV_DIR="${VENV_DIR:-/tmp/kaggle_venv}"
PYTHON="$VENV_DIR/bin/python3"
KAGGLE="$VENV_DIR/bin/kaggle"

echo "======================================================================"
echo "  サイクル末 → 次バージョン 統合実行"
echo "======================================================================"
echo ""

# ===== 1. 現バージョン確認 =====
CURRENT_VERSION=$("$PYTHON" -c "
import re
text = open('config.yml').read()
m = re.search(r'^model_version:\s*(\S+)', text, re.M)
print(m.group(1).strip('\"\\'') if m else 'v6')
")
echo "[1/6] 現バージョン: $CURRENT_VERSION"

# 件数確認
SIGNAL_COUNT=$(wc -l < "logs/signals_${CURRENT_VERSION}.jsonl" 2>/dev/null || echo 0)
LABEL_COUNT=0
if [ -f "eval/labels_${CURRENT_VERSION}.jsonl" ]; then
    LABEL_COUNT=$(wc -l < "eval/labels_${CURRENT_VERSION}.jsonl")
fi
echo "  signal件数: $SIGNAL_COUNT、 ラベル件数: $LABEL_COUNT"
if [ "$LABEL_COUNT" -lt 30 ]; then
    echo "⚠️  ラベル件数 < 30。 サイクル末としては早すぎるかも (合意: 50-100件)"
    echo "    続行するか? (y/N)"
    read confirm
    if [ "$confirm" != "y" ]; then
        echo "中止"
        exit 1
    fi
fi
echo ""

# ===== 2. 失敗ケース 教師化 =====
echo "[2/6] 失敗ケース → 教師データ化..."
"$PYTHON" teacher/failure_to_teacher.py
echo ""

# ===== 3. 正例 教師化 =====
echo "[3/6] 正例 → 教師データ追加..."
"$PYTHON" teacher/success_to_teacher.py
echo ""

# ===== 4. 7条件 見直しレポート =====
echo "[4/6] 強制ストップ7条件 見直しレポート..."
"$PYTHON" teacher/stop_rules_update.py
echo ""

# ===== 5. v(N+1) 学習データ生成 =====
echo "[5/6] v(N+1) 学習データ生成..."
"$PYTHON" training/data_builder.py

NEXT_VERSION=$("$PYTHON" -c "
v = '$CURRENT_VERSION'
if v.startswith('v') and v[1:].isdigit():
    print(f'v{int(v[1:]) + 1}')
else:
    print(v + '_next')
")
echo "  次バージョン: $NEXT_VERSION"
echo ""

# ===== 6. Kaggle push =====
echo "[6/6] Kaggle に $NEXT_VERSION push..."
KAGGLE_DIR="/tmp/kaggle_planA"
if [ ! -d "$KAGGLE_DIR" ]; then
    echo "⚠️ $KAGGLE_DIR が存在しません。 既存 v6 push時のディレクトリを再利用するか、 手動で:"
    echo "   mkdir -p $KAGGLE_DIR"
    echo "   cp training/data_${NEXT_VERSION}.jsonl $KAGGLE_DIR/danjer_lora_poc_data.jsonl"
    echo "   cd $KAGGLE_DIR && $KAGGLE kernels push"
    exit 1
fi

# data_v(N+1).jsonl を Kaggle DLされる位置に配置
DATA_FILE="$HERE/training/data_${NEXT_VERSION}.jsonl"
if [ ! -f "$DATA_FILE" ]; then
    echo "❌ $DATA_FILE が無い (data_builder.py 失敗?)"
    exit 1
fi
cp "$DATA_FILE" /Users/shuji/Desktop/kitt-voice/btc-trading/danjer_triplet/danjer_lora_poc_data.jsonl
cd /Users/shuji/Desktop/kitt-voice && git add btc-trading/danjer_triplet/danjer_lora_poc_data.jsonl && git commit -m "[auto] sync data_${NEXT_VERSION}.jsonl from ai_growth cycle" && git push origin danjer-lora-poc

echo "  Kaggle push..."
cd "$KAGGLE_DIR"
"$KAGGLE" kernels push 2>&1 | tail -3

echo ""
echo "======================================================================"
echo "  サイクル完了! 次バージョン Kaggle 実行中"
echo ""
echo "  進捗確認: $KAGGLE kernels status shujisasaki/danjer-lora-plan-a"
echo ""
echo "  完走後 (約5-6時間):"
echo "    1. \$KAGGLE kernels output shujisasaki/danjer-lora-plan-a"
echo "    2. compare_planA.jsonl 評価"
echo "    3. config.yml の model_version を $NEXT_VERSION に更新"
echo "    4. setup.sh で新 adapter をDL"
echo "    5. runner.py で第N+1サイクル開始"
echo "======================================================================"
