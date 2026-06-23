#!/bin/bash
# danjerクローンAI 育成環境 セットアップスクリプト
#
# 3者合意 (2026-06-24): Mac戻ったらこれを実行→ 全自動でセットアップ完了
#
# 使い方:
#   cd btc-trading/ai_growth
#   bash setup.sh
#
# 内容:
# 1. Python venv 確認 / 作成
# 2. 依存ライブラリ install (transformers / peft / yfinance / pyyaml)
# 3. Kaggle CLI で v6 adapter を ./adapter/ にDL
# 4. config.yml の adapter_path を更新
# 5. python3 safety_check.py で 🟢 SAFE 確認
# 6. python3 -m unittest tests を実行

set -e
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

VENV_DIR="${VENV_DIR:-/tmp/kaggle_venv}"
PYTHON="$VENV_DIR/bin/python3"
PIP="$VENV_DIR/bin/pip"

echo "======================================================================"
echo "  danjerクローンAI 育成環境 セットアップ"
echo "======================================================================"
echo ""

# ===== 1. venv 確認 =====
echo "[1/6] Python venv 確認..."
if [ ! -d "$VENV_DIR" ]; then
    echo "  venv作成: $VENV_DIR"
    python3 -m venv "$VENV_DIR"
fi
echo "  ✅ venv: $VENV_DIR"
echo ""

# ===== 2. 依存install =====
echo "[2/6] 依存ライブラリ install..."
# 必須セット
"$PIP" install -q --upgrade pip 2>&1 | tail -1
"$PIP" install -q yfinance transformers peft pyyaml accelerate 2>&1 | tail -3
echo "  ✅ yfinance, transformers, peft, pyyaml, accelerate"
echo ""

# ===== 3. v6 adapter DL =====
echo "[3/6] v6 adapter DL (Kaggle CLI)..."
ADAPTER_DIR="$HERE/adapter"
if [ -d "$ADAPTER_DIR" ] && [ -f "$ADAPTER_DIR/adapter_model.safetensors" ]; then
    echo "  既に存在: $ADAPTER_DIR"
else
    if [ ! -f "$HOME/.kaggle/access_token" ] && [ ! -f "$HOME/.kaggle/kaggle.json" ]; then
        echo "  ⚠️ Kaggle credentialsが無い (~/.kaggle/access_token or kaggle.json)"
        echo "    手動DL: kaggle kernels output shujisasaki/danjer-lora-plan-a -p ./adapter/"
    else
        if [ -f "$VENV_DIR/bin/kaggle" ]; then
            KAGGLE="$VENV_DIR/bin/kaggle"
        else
            "$PIP" install -q kaggle 2>&1 | tail -1
            KAGGLE="$VENV_DIR/bin/kaggle"
        fi
        mkdir -p "$ADAPTER_DIR"
        echo "  DL中 (約86MB)..."
        "$KAGGLE" kernels output shujisasaki/danjer-lora-plan-a -p "$ADAPTER_DIR" 2>&1 | tail -3
        # Kaggleのoutputは adapter/danjer_lora_planA_adapter/ に入る → 直下に持ち上げる
        if [ -d "$ADAPTER_DIR/danjer_lora_planA_adapter" ]; then
            mv "$ADAPTER_DIR/danjer_lora_planA_adapter"/* "$ADAPTER_DIR/" 2>/dev/null || true
            rmdir "$ADAPTER_DIR/danjer_lora_planA_adapter" 2>/dev/null || true
        fi
    fi
fi
if [ -f "$ADAPTER_DIR/adapter_model.safetensors" ]; then
    echo "  ✅ adapter: $(du -h $ADAPTER_DIR/adapter_model.safetensors | cut -f1)"
else
    echo "  ⚠️ adapter未配置 (手動で配置してください、 inferenceは dry_run になります)"
fi
echo ""

# ===== 4. config.yml の adapter_path 更新 =====
echo "[4/6] config.yml adapter_path 更新..."
if [ -f "$ADAPTER_DIR/adapter_model.safetensors" ]; then
    "$PYTHON" -c "
import re
config_path = '$HERE/config.yml'
text = open(config_path).read()
new_text = re.sub(
    r'model_adapter_local:.*',
    'model_adapter_local: \"$ADAPTER_DIR\"',
    text
)
open(config_path, 'w').write(new_text)
print('  ✅ updated')
"
else
    echo "  ⚠️ adapter未配置のため config変更スキップ"
fi
echo ""

# ===== 5. safety_check 実行 =====
echo "[5/6] safety_check.py..."
"$PYTHON" safety_check.py
SAFETY_EXIT=$?
if [ $SAFETY_EXIT -ne 0 ]; then
    echo "  ❌ safety_check 失敗 (exit $SAFETY_EXIT)、 上記の❌を解消してください"
    exit 1
fi
echo ""

# ===== 6. tests 実行 =====
echo "[6/6] テスト実行..."
"$PYTHON" -m unittest tests.test_no_order tests.test_stop_rules 2>&1 | tail -10
echo ""

echo "======================================================================"
echo "  セットアップ完了! Mac戻ったら以下で運用開始:"
echo ""
echo "  cd $HERE"
echo "  $PYTHON safety_check.py        # ★Shujiさん自身で🟢SAFE確認"
echo "  $PYTHON runner.py --once       # 1回テスト判定"
echo "  $PYTHON runner.py              # 8h間隔で無限ループ"
echo "  $PYTHON eval/dashboard.py      # 評価ダッシュボード"
echo "  $PYTHON eval/label_tool.py     # 8択ラベル付け"
echo "======================================================================"
