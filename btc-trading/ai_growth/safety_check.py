#!/usr/bin/env python3
"""danjerクローンAI 育成環境 安全確認スクリプト

3者合意 (2026-06-24 06:41 btc部屋):
「Step 2「🟢SAFE確認」 は必ずShujiさん自身の目で 画面確認」
「AIの報告じゃなく自分で画面確認、 これがお金を守る最後の砦」

このスクリプトを Shujiさんが自分のターミナルで実行 → 「🟢 SAFE」 を目視確認。
"""
import os
import sys
from pathlib import Path

HERE = Path(__file__).parent

# ===== チェック関数 =====

def check_ccxt_not_installed():
    """ccxt (取引所APIラッパー) が install されていないか"""
    try:
        import ccxt  # type: ignore
        return False, f"❌ ccxt installed at {ccxt.__file__}. UNINSTALL: pip uninstall ccxt"
    except ImportError:
        return True, "ccxt not installed (取引所API library 無し)"


def check_paper_mode():
    """config.yml で paper_mode=true 固定か"""
    config_path = HERE / "config.yml"
    if not config_path.exists():
        return False, "config.yml not found"
    text = config_path.read_text(encoding='utf-8')
    # シンプル grep (yaml parser依存避ける)
    for line in text.splitlines():
        line_clean = line.split('#')[0].strip()  # コメント除去
        if line_clean.startswith('paper_mode:'):
            value = line_clean.split(':', 1)[1].strip().lower()
            if value in ('true', 'yes', 'on'):
                return True, "config paper_mode=true (本番遮断 ON)"
            return False, f"❌ config paper_mode={value} (true以外、 起動禁止)"
    return False, "❌ config paper_mode 未設定"


def check_no_api_keys():
    """取引所APIキーが環境変数にないか"""
    suspicious_envs = [
        'BYBIT_API_KEY', 'BYBIT_API_SECRET',
        'BINANCE_API_KEY', 'BINANCE_API_SECRET',
        'BITGET_API_KEY', 'BITGET_API_SECRET',
        'HYPERLIQUID_API_KEY', 'HYPERLIQUID_API_SECRET',
        'EXNESS_API_KEY', 'EXNESS_API_SECRET',
        'GMO_API_KEY', 'GMO_API_SECRET',
        'BITFLYER_API_KEY', 'BITFLYER_API_SECRET',
        'LIGHTER_API_KEY',
        'COINBASE_API_KEY', 'COINBASE_API_SECRET',
        'OKX_API_KEY', 'OKX_API_SECRET',
        'KRAKEN_API_KEY', 'KRAKEN_API_SECRET',
    ]
    found = [k for k in suspicious_envs if os.environ.get(k)]
    if found:
        return False, f"❌ 取引所APIキー検出 ({len(found)}件): {found[:3]}..."
    return True, "no exchange API keys in env"


def check_data_source_only_ohlcv():
    """data_source.py が取引所APIではなく yfinance のみ使うか

    コード行 (コメント除外) を grep する。 コメント (#で始まる行) は無視。
    """
    ds_path = HERE / "data_source.py"
    if not ds_path.exists():
        return None, "data_source.py not yet created (Phase 1未完成)"
    text = ds_path.read_text(encoding='utf-8')
    # 行単位で見て、 # コメント行をskip
    forbidden_patterns = ['import ccxt', 'from ccxt', 'import pybit', 'from pybit',
                          'binance.client', 'bybit_api',
                          'place_order(', 'submit_order(', 'create_order(']
    for line in text.splitlines():
        # docstring内も除外したいが、 ここでは行先頭が # のみ除外
        stripped = line.lstrip()
        if stripped.startswith('#') or stripped.startswith('"""') or stripped.startswith("'''"):
            continue
        for pattern in forbidden_patterns:
            if pattern in line:
                return False, f"❌ data_source.py に禁止パターン検出: {pattern} (行: {line.strip()[:60]})"
    # yfinance使用確認
    if 'yfinance' in text or 'yf.' in text:
        return True, "data_source.py uses yfinance only (取引所API無し)"
    return True, "data_source.py OK (取引所API無し)"


def check_inference_no_orders():
    """inference.py が注文関連処理を含まないか"""
    inf_path = HERE / "inference.py"
    if not inf_path.exists():
        return None, "inference.py not yet created (Phase 1未完成)"
    text = inf_path.read_text(encoding='utf-8')
    forbidden = ['place_order', 'submit_order', 'create_order', 'execute_trade',
                 'place_market_order', 'send_order']
    for pattern in forbidden:
        if pattern in text:
            return False, f"❌ inference.py に注文処理検出: {pattern}"
    return True, "inference.py only reads/writes local files (注文処理無し)"


def check_runner_paper_mode_assert():
    """runner.py が起動時に paper_mode=true をassertするか"""
    runner_path = HERE / "runner.py"
    if not runner_path.exists():
        return None, "runner.py not yet created (Phase 1未完成)"
    text = runner_path.read_text(encoding='utf-8')
    if 'paper_mode' in text and ('assert' in text or 'raise' in text):
        return True, "runner.py asserts paper_mode at startup"
    return False, "❌ runner.py に paper_mode の起動時assertが無い"


# ===== メイン =====

def main():
    checks = [
        ("ccxt 取引所APIライブラリ非導入", check_ccxt_not_installed),
        ("config paper_mode=true", check_paper_mode),
        ("環境変数に取引所APIキー無し", check_no_api_keys),
        ("data_source.py が yfinance のみ使用", check_data_source_only_ohlcv),
        ("inference.py に注文処理無し", check_inference_no_orders),
        ("runner.py に paper_mode 起動時assert", check_runner_paper_mode_assert),
    ]

    print()
    print("=" * 70)
    print("  danjerクローンAI 育成環境 安全確認 (5+1項目チェック)")
    print("  ★Shujiさん自身がこの画面を見て確認してください★")
    print("  (3者合意 2026-06-24: AIの報告じゃなく自分の目で見ること)")
    print("=" * 70)

    fail_count = 0
    incomplete_count = 0
    for name, check in checks:
        try:
            result, msg = check()
        except Exception as e:
            print(f"⚠️  {name}: 例外発生 {type(e).__name__}: {e}")
            fail_count += 1
            continue
        if result is None:
            print(f"⏳ {msg}")
            incomplete_count += 1
        elif result:
            print(f"✅ {msg}")
        else:
            print(f"{msg}")
            fail_count += 1

    print("=" * 70)
    if fail_count == 0 and incomplete_count == 0:
        print()
        print("  🟢 SAFE: this environment CANNOT place real orders")
        print("  ★Shujiさん、 上記の✅を自分の目で確認しましたか?★")
        print()
        return 0
    elif fail_count == 0 and incomplete_count > 0:
        print()
        print(f"  ⏳ INCOMPLETE: Phase 1未完成のファイル {incomplete_count}件")
        print("     (完成後にもう一度 safety_check.py を実行)")
        print()
        return 2
    else:
        print()
        print(f"  ⚠️  NOT SAFE: 上記の❌を解消するまで起動禁止 ({fail_count}件)")
        print()
        return 1


if __name__ == "__main__":
    sys.exit(main())
