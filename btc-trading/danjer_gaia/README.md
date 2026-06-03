# Project danjer-GAIA — Day 1-2 評価基盤

3者会議 v3 ([議事録](../../logs/round_table_v3.md)) の Phase 1合意に基づく Trade-EHR 評価基盤の実装。

## 構成

```
danjer_gaia/
├── __init__.py        # パッケージ公開API
├── schemas.py         # Trade / TradingPeriod / GuardConfig / NoopConfig
├── metrics.py         # Trade-EHR / MA30 / noop機会損失ペナルティ / period_summary
├── guards.py          # Liquidation/MaxDD/NoStop/Slippage/OverLeverage/Overtrade
├── rewards.py         # episode_reward (報酬関数全体)
└── tests/
    ├── test_metrics.py  # 17 tests
    ├── test_guards.py   # 11 tests
    └── test_rewards.py  # 5 tests
```

## 仕様 (3者会議合意)

### Trade-EHR (Equity-Hours Return)

```
Trade-EHR = NetProfit / (max(AvgEquity, ε_equity) × max(ElapsedHours, ε_hours))
```

- 待機時間込み (前トレード終了〜今回終了までの全経過時間)
- 分母ガード: ε_equity=100 USD, ε_hours=1.0 h (Appendix-A、ゼロ除算防止)
- 集計: 直近30トレードの移動平均 (MA30)

### 報酬関数

```
Reward = Trade-EHR_MA30
       + noop_penalty (条件付き、 R28防止)
       - Σ guard_penalty (Liquidation/MaxDD/NoStop/Slippage/OverLeverage/Overtrade)
```

掛け算ではなく加算で学習安定化 (Gemini Round 6 監査指摘)。

### noop機会損失ペナルティ — 強制エントリーbug防止条件

以下 **4条件 全部満たす場合のみ発動** (R28 対策):
- Slow Brain confidence ≥ 0.75
- Slow Brain risk_level ≤ 0.4
- 期待値 > 0
- その後に実際の大きな順行が発生

ペナルティ自体も上限固定:
- base 0.001/h × min(現在ATR / ベースラインATR, 3.0)
- 絶対上限 0.01/h

### ガード減算 (Appendix-A, B, C, D, E)

| ペナルティ | 数式 | デフォルト |
|---|---|---|
| Liquidation | -100 × N | const=100 |
| MaxDD超過 | -coef × max(0, DD - limit)² | limit=5%, coef=1.0 |
| NoStop | -20 × N | const=20 |
| Slippage超過 | -coef × Σ max(0, slip - baseline) | coef=10, baseline=5 USD |
| OverLeverage | -coef × Σ max(0, lev - threshold) | threshold=5x, coef=2 |
| Overtrade | -coef × max(0, count - limit) | limit=50, coef=0.5 |

## 使用例

```python
from datetime import datetime
from danjer_gaia import Trade, TradingPeriod, episode_reward

trade = Trade(
    trade_id="t001", symbol="BTCUSDT", side="long",
    entered_at=datetime(2026, 6, 3, 10, 0),
    exited_at=datetime(2026, 6, 3, 12, 0),
    elapsed_hours=2.0,
    entry_price=50000.0, exit_price=50500.0,
    size=0.01, leverage=2.0,
    gross_profit=105.0, fees=3.0, slippage=2.0, net_profit=100.0,
    avg_equity=10000.0,
    had_sl=True, was_liquidated=False, max_dd_during=0.02,
)
period = TradingPeriod(
    period_start=datetime(2026, 6, 1),
    period_end=datetime(2026, 6, 30),
    trades=[trade],
    noop_hours_total=12.0,
)
result = episode_reward(period)
print(result)
# {'ma30_ehr': 0.005, 'noop_pen': 0.0, 'guard_pen': 0.0, 'total_reward': 0.005, ...}
```

## テスト実行

```bash
cd btc-trading
python3 -m unittest discover -s danjer_gaia/tests
```

→ **39 tests, all pass** (2026-06-03 確認)

## 次のステップ (Day 3-4)

- BigQuery `btc_trading` dataset の棚卸し
- X投稿49,667件の正確件数確認
- OHLCV/OI/FR/清算/LS比 の収集状態確認
