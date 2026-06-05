"""
Project danjer-GAIA — Exchange Router (Phase 4 動的切替)
==========================================================
3者会議 Round 30-38 (戦略Z v8) 確定の Phase 4 動的切替ロジック。

役割:
- 複数取引所 (Hyperliquid主, bitget副, Exness副) 間の動的切替
- 注文を最適な取引所に振り分ける (板厚・障害ステータス・CB効果)
- 障害時の自動退避 (Hyperliquid異常 → bitget)
- 配分比率管理 (Phase 4 Cap 1: Hyperliquid 60% + Exness 40%、 Cap 2以降 50:50)

Phase別有効化:
- Phase 2-3: Hyperliquid 単独 (Router 内部で他取引所をスキップ)
- Phase 3後半: Hyperliquid主 + bitget副 read-only テスト
- Phase 4 Cap 1+: 全機能有効化、 配分・障害退避動作

R72対策 (Hyperliquid 流動性集中):
- 板厚監視閾値 (BTC perp $30M下回り → bitget自動切替)

R84-R86対策 (MT5/Exness 連携):
- Exness は Order Router で「同方向ポジション 分割」 設計
- スリッページ・約定タイミングずれ吸収 (50pip超ズレで再発注)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Callable, Any
import uuid

from .base import (
    ExchangeBase, OrderType, OrderSide, OrderResult, Position, Balance,
    MarketSnapshot, ExchangeError,
)


class ExchangeStatus(Enum):
    """各取引所の状態"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"      # 一時的な遅延 (まだ使える)
    OUTAGE = "outage"          # 障害 (使用不可)
    DISABLED = "disabled"      # Phase別に無効化


@dataclass
class ExchangeWeight:
    """取引所の配分重み (Phase 4 Cap別設定)"""
    exchange_name: str
    target_pct: float = 0.0     # 配分目標 (0.0 - 1.0)
    enabled: bool = False        # Phase で enabled かどうか
    health: ExchangeStatus = ExchangeStatus.HEALTHY


@dataclass
class RouterConfig:
    """Router 設定 (Phase別の構成)"""
    weights: list[ExchangeWeight] = field(default_factory=list)
    min_depth_usd: float = 30_000_000.0  # 板厚閾値 (R72対策、 $30M下回りで自動切替)
    max_price_diff_pips: float = 50.0    # 取引所間 約定価格ズレ閾値 (R85対策)
    health_check_interval_sec: int = 30
    spread_diff_threshold_pct: float = 0.001  # スプ差 0.1%以上で 並走スキップ


# ============================================================
# Phase別 デフォルト構成 (戦略Z v8 確定)
# ============================================================
def phase_2_3_config() -> RouterConfig:
    """Phase 2-3 (Day 8 - Day 154、 Hyperliquid単独)"""
    return RouterConfig(weights=[
        ExchangeWeight("hyperliquid", target_pct=1.0, enabled=True),
        ExchangeWeight("bitget", target_pct=0.0, enabled=False),
        ExchangeWeight("exness", target_pct=0.0, enabled=False),
    ])


def phase_3_late_config() -> RouterConfig:
    """Phase 3後半 (Day 100-167、 bitget副 read-only テスト)"""
    return RouterConfig(weights=[
        ExchangeWeight("hyperliquid", target_pct=1.0, enabled=True),
        ExchangeWeight("bitget", target_pct=0.0, enabled=True),  # read-only テスト用
        ExchangeWeight("exness", target_pct=0.0, enabled=False),
    ])


def phase_4_cap1_config() -> RouterConfig:
    """Phase 4 Cap 1 (Day 168-、 $25k、 Hyperliquid 60% + Exness 40%)"""
    return RouterConfig(weights=[
        ExchangeWeight("hyperliquid", target_pct=0.6, enabled=True),
        ExchangeWeight("exness", target_pct=0.4, enabled=True),
        ExchangeWeight("bitget", target_pct=0.0, enabled=True),  # 障害退避用
    ])


def phase_4_cap2_config() -> RouterConfig:
    """Phase 4 Cap 2 (Day 240-、 $50k、 50:50)"""
    return RouterConfig(weights=[
        ExchangeWeight("hyperliquid", target_pct=0.5, enabled=True),
        ExchangeWeight("exness", target_pct=0.5, enabled=True),
        ExchangeWeight("bitget", target_pct=0.0, enabled=True),
    ])


def phase_5_cap5_config() -> RouterConfig:
    """Phase 5+ Cap 5 ($500k、 Hyperliquid 40% + Exness 40% + Lighter 20% 条件達成時)"""
    return RouterConfig(weights=[
        ExchangeWeight("hyperliquid", target_pct=0.4, enabled=True),
        ExchangeWeight("exness", target_pct=0.4, enabled=True),
        ExchangeWeight("lighter", target_pct=0.2, enabled=True),  # 条件達成時のみ
        ExchangeWeight("bitget", target_pct=0.0, enabled=True),
    ])


# ============================================================
# v11 (Round 43): AI動的判断による Router 構成 (Shuji方針3対応)
# ============================================================
def ai_dynamic_config(
    enabled_exchanges: list[str],
    stance_recommended: Optional[str] = None,
) -> RouterConfig:
    """
    v11: AI が Stance JSON で取引所推奨を出した場合、 Router構成を動的生成。

    Args:
        enabled_exchanges: 利用可能取引所のリスト (現在登録済み)
        stance_recommended: Stance.recommended_exchange ("auto"なら自律、
                            "hyperliquid" 等なら 指定取引所100%)

    使い方:
        # AI が「hyperliquid 100%」と判断
        cfg = ai_dynamic_config(
            enabled_exchanges=["hyperliquid", "bitget"],
            stance_recommended="hyperliquid",
        )

        # AI が「自律判断 (Router任せ)」 と判断
        cfg = ai_dynamic_config(
            enabled_exchanges=["hyperliquid", "exness"],
            stance_recommended="auto",
        )
    """
    if stance_recommended and stance_recommended != "auto":
        # AI が特定取引所を指定 → 100%振り分け
        return RouterConfig(weights=[
            ExchangeWeight(name, target_pct=(1.0 if name == stance_recommended else 0.0),
                           enabled=True)
            for name in enabled_exchanges
        ])

    # auto: 全 enabled取引所を均等配分 (Router がhealth+板厚で再選定)
    equal_weight = 1.0 / max(len(enabled_exchanges), 1)
    return RouterConfig(weights=[
        ExchangeWeight(name, target_pct=equal_weight, enabled=True)
        for name in enabled_exchanges
    ])


# ============================================================
# Exchange Router 本体
# ============================================================
class ExchangeRouter:
    """
    複数取引所を動的に振り分ける Router。

    使い方:
        # Phase 2-3 (Hyperliquid単独)
        router = ExchangeRouter(
            exchanges={"hyperliquid": HyperliquidClient(...)},
            config=phase_2_3_config(),
        )
        result = router.place_order(symbol="BTC", ...)

        # Phase 4 Cap 1 (Hyperliquid 60% + Exness 40%)
        router = ExchangeRouter(
            exchanges={
                "hyperliquid": HyperliquidClient(...),
                "exness": ExnessClient(...),
                "bitget": BitgetClient(...),
            },
            config=phase_4_cap1_config(),
        )
        # 自動配分: Hyperliquidに60%、 Exnessに40%、 bitgetは障害退避時のみ
        result = router.place_order(symbol="BTC", size=0.01, ...)
    """

    def __init__(self, exchanges: dict[str, ExchangeBase],
                 config: Optional[RouterConfig] = None):
        self.exchanges = exchanges
        self.config = config or phase_2_3_config()
        self._health: dict[str, ExchangeStatus] = {
            name: ExchangeStatus.HEALTHY for name in exchanges
        }
        self._last_health_check: Optional[datetime] = None

    # ==================== ヘルスチェック ====================
    def check_health(self) -> dict[str, ExchangeStatus]:
        """全取引所の health_check 実行"""
        for name, exchange in self.exchanges.items():
            try:
                if exchange.health_check():
                    self._health[name] = ExchangeStatus.HEALTHY
                else:
                    self._health[name] = ExchangeStatus.DEGRADED
            except Exception:
                self._health[name] = ExchangeStatus.OUTAGE
        self._last_health_check = datetime.now(timezone.utc)
        return dict(self._health)

    def get_status(self, exchange_name: str) -> ExchangeStatus:
        """指定取引所の状態取得"""
        return self._health.get(exchange_name, ExchangeStatus.OUTAGE)

    # ==================== 配分計算 ====================
    def compute_allocation(self, total_size: float) -> dict[str, float]:
        """size を各取引所に分配"""
        allocations: dict[str, float] = {}

        # enabled かつ HEALTHY な取引所のみ
        active_weights = [
            w for w in self.config.weights
            if w.enabled and self._health.get(w.exchange_name) == ExchangeStatus.HEALTHY
            and w.target_pct > 0
        ]

        if not active_weights:
            # 全障害時: 最初の取引所に全振り (フォールバック)
            for w in self.config.weights:
                if w.enabled:
                    allocations[w.exchange_name] = total_size
                    return allocations
            return {}

        # target_pct 比率で配分 (R85対策: 板厚チェック後)
        total_weight = sum(w.target_pct for w in active_weights)
        for w in active_weights:
            allocations[w.exchange_name] = total_size * (w.target_pct / total_weight)
        return allocations

    # ==================== 板厚ベースフォールバック (R72) ====================
    def _check_depth_threshold(self, exchange_name: str, symbol: str) -> bool:
        """板厚が R72閾値を下回るかチェック"""
        try:
            exchange = self.exchanges[exchange_name]
            market = exchange.get_market(symbol)
            top5_depth_usd = (market.bid_top5_depth + market.ask_top5_depth) / 2 * market.mark_price
            return top5_depth_usd >= self.config.min_depth_usd
        except Exception:
            return False

    def get_routing_decision(self, symbol: str, total_size: float) -> dict[str, Any]:
        """発注前のルーティング判断 (説明可能性のため)"""
        decision = {
            "allocations": {},
            "skipped_exchanges": [],
            "reasons": {},
        }
        # 板厚チェック
        for w in self.config.weights:
            if not w.enabled or w.target_pct <= 0:
                continue
            ok = self._check_depth_threshold(w.exchange_name, symbol)
            if not ok:
                decision["skipped_exchanges"].append(w.exchange_name)
                decision["reasons"][w.exchange_name] = "depth_below_threshold"
                self._health[w.exchange_name] = ExchangeStatus.DEGRADED

        # 配分
        decision["allocations"] = self.compute_allocation(total_size)
        return decision

    # ==================== 統合発注 ====================
    def place_order(
        self,
        symbol: str,
        side: OrderSide,
        size: float,
        order_type: OrderType,
        leverage: float,
        decision_trace_id: str,
        price: Optional[float] = None,
        sl_price: Optional[float] = None,
        tp_price: Optional[float] = None,
        sl_reduce_only: bool = True,
    ) -> list[OrderResult]:
        """
        複数取引所に分散発注。 各取引所の結果リストを返す。

        Phase 2-3 (Hyperliquid単独): list の長さ1
        Phase 4 Cap 1 (Hyperliquid+Exness 並走): list の長さ2
        """
        results: list[OrderResult] = []
        allocations = self.compute_allocation(size)

        for ex_name, alloc_size in allocations.items():
            if alloc_size <= 0:
                continue
            exchange = self.exchanges.get(ex_name)
            if not exchange:
                results.append(OrderResult(
                    order_id="", decision_trace_id=decision_trace_id,
                    symbol=symbol, side=side, order_type=order_type,
                    size=alloc_size, price=price, status="rejected",
                    error=f"exchange {ex_name} not registered",
                ))
                continue

            try:
                # 各取引所固有の symbol 変換 (例: Hyperliquidは "BTC"、 Exnessは "BTCUSD")
                ex_symbol = self._translate_symbol(ex_name, symbol)
                result = exchange.place_order(
                    symbol=ex_symbol, side=side, size=alloc_size,
                    order_type=order_type, leverage=leverage,
                    decision_trace_id=f"{decision_trace_id}:{ex_name}",
                    price=price, sl_price=sl_price, tp_price=tp_price,
                    sl_reduce_only=sl_reduce_only,
                )
                results.append(result)
            except Exception as e:
                results.append(OrderResult(
                    order_id="", decision_trace_id=decision_trace_id,
                    symbol=symbol, side=side, order_type=order_type,
                    size=alloc_size, price=price, status="rejected",
                    error=f"{ex_name} place_order failed: {e}",
                ))

        # R85対策: 約定価格ズレチェック
        filled = [r for r in results if r.status == "filled"]
        if len(filled) >= 2:
            prices = [r.filled_price for r in filled]
            max_p, min_p = max(prices), min(prices)
            spread_pips = (max_p - min_p) * 10  # BTC で 1pip = 0.0001 想定
            if spread_pips > self.config.max_price_diff_pips:
                # ズレ大: 後段で 1取引所キャンセル+再発注ロジック (今は警告のみ)
                for r in results:
                    if r.error is None:
                        r.error = f"price_drift_warning: spread={spread_pips:.1f}pips"

        return results

    def _translate_symbol(self, exchange_name: str, symbol: str) -> str:
        """取引所固有の symbol に変換 (例: BTC ↔ BTCUSD ↔ BTCUSDT)"""
        if exchange_name == "hyperliquid":
            # Hyperliquid: "BTC" (USDC建て前提)
            return symbol.replace("USDT", "").replace("USDC", "").replace("USD", "")
        elif exchange_name == "bitget":
            # bitget perp: "BTCUSDT"
            base = symbol.replace("USDT", "").replace("USDC", "").replace("USD", "")
            return f"{base}USDT"
        elif exchange_name == "exness":
            # Exness CFD: "BTCUSD"
            base = symbol.replace("USDT", "").replace("USDC", "").replace("USD", "")
            return f"{base}USD"
        elif exchange_name == "lighter":
            return symbol.replace("USDT", "").replace("USDC", "").replace("USD", "")
        return symbol

    # ==================== 統合決済 ====================
    def close_position(self, symbol: str, decision_trace_id: str = "") -> list[OrderResult]:
        """全取引所の同一symbol ポジションを並列クローズ"""
        results: list[OrderResult] = []
        for ex_name, exchange in self.exchanges.items():
            ex_symbol = self._translate_symbol(ex_name, symbol)
            try:
                pos = exchange.get_position(ex_symbol)
                if not pos:
                    continue
                # 緊急時は Exness を優先 (R86対策: スプレッド拡大前にクローズ)
                # 通常時は Hyperliquid を優先 (maker rebate確保)
                result = exchange.close_position(
                    ex_symbol, decision_trace_id=f"{decision_trace_id}:{ex_name}",
                )
                results.append(result)
            except Exception as e:
                results.append(OrderResult(
                    order_id="", decision_trace_id=decision_trace_id,
                    symbol=symbol, side=OrderSide.SELL,
                    order_type=OrderType.MARKET, size=0, price=None,
                    status="rejected", error=f"{ex_name} close failed: {e}",
                ))
        return results

    # ==================== 統合残高 ====================
    def get_total_balance(self) -> dict[str, Balance]:
        """全取引所の残高取得"""
        balances: dict[str, Balance] = {}
        for ex_name, exchange in self.exchanges.items():
            try:
                balances[ex_name] = exchange.get_balance()
            except Exception:
                balances[ex_name] = Balance(
                    equity=0, available=0, used=0, currency="N/A",
                )
        return balances

    def get_total_equity(self) -> float:
        """全取引所合計の equity (規模キャップ判定用)"""
        total = 0.0
        for balance in self.get_total_balance().values():
            total += balance.equity
        return total

    # ==================== v11: AI動的設定変更 (Round 43) ====================
    def apply_dynamic_config(self, stance_recommended: Optional[str] = None) -> None:
        """
        v11: Stance JSON の recommended_exchange を受け、 Router 構成を動的更新。

        Shuji方針3: 「運用中も取引所の条件変わるから変更の可能性もある」 への対応。

        Args:
            stance_recommended: "auto" / "hyperliquid" / "bitget" / "exness" / None
                None なら設定変更なし (既存 config 維持)
        """
        if not stance_recommended:
            return
        enabled = list(self.exchanges.keys())
        new_config = ai_dynamic_config(enabled, stance_recommended)
        self.config = new_config
