"""
Project danjer-GAIA — Slippage Model
======================================
紙トレで Live より厳しめのスリッページを算出 (R40対策)。
板の厚さ vs 注文サイズで実際の約定コストを保守的に推定。
"""
from __future__ import annotations


def estimate_slippage_pct(order_size: float, bid_or_ask_depth_top5: float,
                          base_slippage: float = 0.0005,
                          depth_ratio_penalty: float = 0.001) -> float:
    """
    スリッページ率 (絶対値) を推定。

    Args:
        order_size: 注文サイズ (base currency)
        bid_or_ask_depth_top5: top5 板の厚さ (同方向)
        base_slippage: 基本スリッページ (0.05%デフォルト、 R40保守的)
        depth_ratio_penalty: 板薄時の追加ペナルティ (size/depth 比率に応じて)

    Returns:
        スリッページ率 (例: 0.001 = 0.1%)

    例:
        size=0.01、 depth=10.0 → ratio=0.001 → slip = 0.0005 + 0.001*0 = 0.0005
        size=1.0、 depth=10.0  → ratio=0.1   → slip = 0.0005 + 0.001*0.1 = 0.0006
        size=5.0、 depth=10.0  → ratio=0.5   → slip = 0.0005 + 0.001*0.5 = 0.001
    """
    if bid_or_ask_depth_top5 <= 0:
        return base_slippage * 10  # 流動性ゼロは大きいペナルティ
    ratio = order_size / bid_or_ask_depth_top5
    return base_slippage + depth_ratio_penalty * ratio


def estimate_fill_price(order_side: str, mark_price: float,
                        slippage_pct: float) -> float:
    """
    約定価格を推定 (slippage を考慮)

    Args:
        order_side: "buy" or "sell"
        mark_price: 現在 Mark 価格
        slippage_pct: スリッページ率
    """
    if order_side == "buy":
        return mark_price * (1 + slippage_pct)
    else:
        return mark_price * (1 - slippage_pct)
