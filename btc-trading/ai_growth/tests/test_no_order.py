"""本番遮断テスト (絶対に取引所APIを呼ばないことを保証)

3者合意 (2026-06-24): 設定一つでテストが本物になる事故を絶対防ぐ。

実行:
    cd btc-trading/ai_growth
    python3 -m unittest tests.test_no_order -v
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).parent.parent
sys.path.insert(0, str(HERE))


class TestNoOrderPlacement(unittest.TestCase):
    """本番発注遮断の物理的保証"""

    def test_ccxt_not_importable(self):
        """ccxt が install されていないこと"""
        try:
            import ccxt  # type: ignore  # noqa: F401
            self.fail("ccxt が install されています! 即 pip uninstall ccxt してください")
        except ImportError:
            pass  # 期待通り

    def test_pybit_not_importable(self):
        """pybit (Bybit公式) が install されていないこと"""
        try:
            import pybit  # type: ignore  # noqa: F401
            self.fail("pybit が install されています!")
        except ImportError:
            pass

    def test_paper_mode_in_config(self):
        """config.yml の paper_mode が必ず true であること"""
        config_path = HERE / "config.yml"
        self.assertTrue(config_path.exists(), "config.yml not found")
        text = config_path.read_text(encoding='utf-8')
        found = False
        for line in text.splitlines():
            line_clean = line.split('#')[0].strip()
            if line_clean.startswith('paper_mode:'):
                value = line_clean.split(':', 1)[1].strip().lower()
                self.assertIn(
                    value, ('true', 'yes', 'on'),
                    f"paper_mode={value} は禁止 (true以外は起動不可)"
                )
                found = True
                break
        self.assertTrue(found, "config.yml に paper_mode キー無し")

    def test_no_exchange_api_keys_in_env(self):
        """環境変数に取引所APIキーが無いこと"""
        suspicious = [
            'BYBIT_API_KEY', 'BINANCE_API_KEY', 'BITGET_API_KEY',
            'HYPERLIQUID_API_KEY', 'COINBASE_API_KEY',
        ]
        found = [k for k in suspicious if os.environ.get(k)]
        self.assertEqual(
            found, [],
            f"取引所APIキー検出: {found} 一切設定してはいけない"
        )

    def test_runner_asserts_paper_mode_at_startup(self):
        """runner.py が起動時に paper_mode をassertすること"""
        runner_path = HERE / "runner.py"
        text = runner_path.read_text(encoding='utf-8')
        self.assertIn('paper_mode', text, "runner.py に paper_mode 言及無し")
        self.assertIn('assert_paper_mode', text, "runner.py に assert_paper_mode 関数無し")

    def test_data_source_no_exchange_api(self):
        """data_source.py が yfinance のみを使い、 取引所APIを呼ばないこと"""
        ds_path = HERE / "data_source.py"
        text = ds_path.read_text(encoding='utf-8')

        # コード行 (コメント除外) を確認
        forbidden_patterns = [
            'import ccxt', 'from ccxt',
            'import pybit', 'from pybit',
            'binance.client',
            'place_order(', 'submit_order(',
        ]
        for line in text.splitlines():
            stripped = line.lstrip()
            if stripped.startswith('#') or stripped.startswith('"""'):
                continue
            for pattern in forbidden_patterns:
                self.assertNotIn(
                    pattern, line,
                    f"data_source.py に禁止パターン {pattern} (line: {line[:80]})"
                )

    def test_inference_no_order_calls(self):
        """inference.py が注文関連処理を含まないこと"""
        inf_path = HERE / "inference.py"
        text = inf_path.read_text(encoding='utf-8')
        forbidden = ['place_order', 'submit_order', 'create_order', 'execute_trade']
        for line in text.splitlines():
            stripped = line.lstrip()
            if stripped.startswith('#') or stripped.startswith('"""'):
                continue
            for pattern in forbidden:
                self.assertNotIn(
                    pattern, line,
                    f"inference.py に禁止パターン {pattern}"
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
