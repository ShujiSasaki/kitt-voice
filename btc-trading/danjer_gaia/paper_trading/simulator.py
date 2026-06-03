"""
Project danjer-GAIA — Paper Trading Simulator (Phase 1全モジュール統合)
==========================================================================
Phase 1 で作った全モジュールを1つのループに統合し、 paper環境で動作させる。

フロー:
  1. 市場データ取得 (MarketSnapshot)
  2. PaperClient.update_market(snapshot)
  3. Slow Brain 呼び出し (本物はGemini API、 ここでは inject)
  4. Stance → TTLManager.on_stance_received
  5. TTLManager.decide_action → (action, stance)
  6. FastGuardSignal 計算 (簡易: price spike / liquidity drop 等)
  7. resolve_conflict(stance, signal, has_pos) → FastGuardDecision
  8. NEW_LONG/SHORT なら → TradeIntent 作成 → run_order_gate
  9. APPROVE → PaperClient.place_order
  10. CLOSE系なら PaperClient.close_position
  11. 全ステップを decision_trace_id 付きで JSON ログ保存

このシミュレータは Slow Brain LLM呼び出しを inject式にしているので、
本番では Slow Brain を Cloud Run経由で呼び出す形に差し替えるだけで稼働可能。
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Callable
import uuid
import json

from ..exchange.base import (
    ExchangeBase, OrderType, OrderSide, OrderResult, MarketSnapshot, Position,
)
from ..stance import Stance
from ..ttl_manager import TTLManager, TTLAction, TTLConfig
from ..fast_guard import (
    FastGuardSignal, FinalAction, resolve_conflict, FastGuardDecision,
)
from ..order_gate import (
    TradeIntent, GateContext, GateConfig, GateResult, run_order_gate,
)
from ..schemas import GuardConfig
from .slippage_model import estimate_slippage_pct


@dataclass
class SimulatorConfig:
    """シミュレータ設定"""
    initial_equity: float = 10000.0
    symbol: str = "BTCUSDT"
    daily_dd_limit: float = 0.05    # 日次DD 5%でhalt
    total_dd_limit: float = 0.15    # 累計DD 15%でhalt
    default_leverage: float = 2.0
    default_size_pct_of_equity: float = 0.005  # 0.5% (Stage 1上限)
    sl_atr_mult: float = 1.5         # SL距離 = ATR × 1.5
    tp_atr_mult: float = 3.0         # TP距離 = ATR × 3.0 (R:R=1:2)


@dataclass
class TickEvent:
    """1tickの判断・実行ログ"""
    timestamp: datetime
    market: dict
    stance_used: Optional[dict]
    ttl_action: str
    fast_signal: str
    final_action: str
    order_result: Optional[dict]
    reason: str
    decision_trace_id: str
    notes: str = ""


# ============================================================
# 市場状態 → Fast Guard Signal の簡易判定
# ============================================================
def detect_fast_guard_signal(
    current: MarketSnapshot,
    prev: Optional[MarketSnapshot] = None,
    position: Optional[Position] = None,
    baseline_depth: Optional[float] = None,
    api_latency_ms: float = 50.0,
) -> FastGuardSignal:
    """簡易 Fast Guard signal 判定"""
    # API異常
    if api_latency_ms > 500:
        return FastGuardSignal.API_ERROR

    # 価格急変 (前tickから±2%以上)
    if prev:
        change_pct = abs(current.mark_price - prev.mark_price) / max(prev.mark_price, 1.0)
        if change_pct >= 0.02:
            if current.mark_price > prev.mark_price:
                return FastGuardSignal.PRICE_SPIKE_UP
            else:
                return FastGuardSignal.PRICE_SPIKE_DOWN

    # 流動性ドロップ
    if baseline_depth and current.bid_top5_depth < baseline_depth * 0.3:
        return FastGuardSignal.LIQUIDITY_DROP

    # SL未設置 (ポジあるのに SL info ない場合)
    if position and position.sl_price is None:
        return FastGuardSignal.SL_MISSING

    # 清算距離不足
    if position:
        atr_unit = current.mark_price * 0.01  # 簡易 ATR (1%)
        liq_distance = abs(current.mark_price - position.liquidation_price)
        if liq_distance < atr_unit:
            return FastGuardSignal.LIQ_DISTANCE_LOW

    return FastGuardSignal.NORMAL


# ============================================================
# Simulator メインクラス
# ============================================================
class PaperSimulator:
    """Phase 1 全モジュール統合シミュレータ"""

    def __init__(self, exchange: ExchangeBase,
                 config: Optional[SimulatorConfig] = None,
                 ttl_config: Optional[TTLConfig] = None,
                 gate_config: Optional[GateConfig] = None,
                 explanation_provider: Optional[Callable[[Stance, MarketSnapshot], str]] = None):
        self.exchange = exchange
        self.config = config or SimulatorConfig()
        self.ttl_mgr = TTLManager(ttl_config or TTLConfig())
        self.gate_config = gate_config or GateConfig()
        self.explanation_provider = explanation_provider or self._default_explanation

        self._prev_market: Optional[MarketSnapshot] = None
        self._tick_log: list[TickEvent] = []
        self._baseline_depth: float = 50.0  # 平常時の板厚 (実環境では学習)
        self._starting_equity: float = self.config.initial_equity
        self._peak_equity: float = self.config.initial_equity

    @staticmethod
    def _default_explanation(stance: Stance, market: MarketSnapshot) -> str:
        """default explanation: stance + market を文字列化"""
        return (
            f"Slow Brain stance={stance.stance} direction={stance.direction:.2f} "
            f"confidence={stance.confidence:.2f} risk={stance.risk_level:.2f} "
            f"max_lev={stance.max_lev} sl_atr_mult={stance.sl_atr_mult}; "
            f"market: price={market.mark_price} spread={market.spread} FR={market.funding_rate}"
        )

    def on_stance(self, stance: Stance):
        """Slow Brain が新しいスタンスを出した時に呼ぶ"""
        self.ttl_mgr.on_stance_received(stance)

    def step(self, market: MarketSnapshot, api_latency_ms: float = 50.0) -> TickEvent:
        """1tick処理 (Cloud Run でも同じ関数を呼べる)"""
        decision_trace_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        # 1. 市場更新
        self.exchange.update_market(market) if hasattr(self.exchange, 'update_market') else None

        # 2. TTL → action
        ttl_action, stance = self.ttl_mgr.decide_action(now)

        # 3. position
        pos = self.exchange.get_position(market.symbol)

        # 4. Fast Guard
        fg_signal = detect_fast_guard_signal(
            current=market, prev=self._prev_market, position=pos,
            baseline_depth=self._baseline_depth, api_latency_ms=api_latency_ms,
        )

        # 5. 緊急halt
        if ttl_action == TTLAction.HALT_AND_CLOSE_ALL:
            if pos:
                self.exchange.close_position(market.symbol, decision_trace_id=decision_trace_id)
            event = TickEvent(
                timestamp=now, market={"price": market.mark_price},
                stance_used=None, ttl_action=ttl_action.value,
                fast_signal=fg_signal.value, final_action="halt_close_all",
                order_result=None, reason="TTL halt", decision_trace_id=decision_trace_id,
            )
            self._tick_log.append(event)
            self._prev_market = market
            return event

        # 6. resolve conflict
        decision = resolve_conflict(stance, fg_signal, has_existing_pos=(pos is not None))

        # 7. 緊急close
        if decision.action in (FinalAction.EMERGENCY_CLOSE, FinalAction.CLOSE_ALL, FinalAction.REDUCE):
            if pos:
                size = pos.size if decision.action != FinalAction.REDUCE else pos.size * 0.5
                r = self.exchange.close_position(market.symbol, size=size, decision_trace_id=decision_trace_id)
                event = self._make_event(now, market, stance, ttl_action, fg_signal,
                                          decision, r, decision_trace_id)
                self._tick_log.append(event)
                self._prev_market = market
                return event

        # 8. NEW_LONG/SHORT → Order Gate
        if decision.action in (FinalAction.NEW_LONG, FinalAction.NEW_SHORT):
            balance = self.exchange.get_balance()
            # 累計DD/日次DD更新
            if balance.equity > self._peak_equity:
                self._peak_equity = balance.equity
            total_dd_pct = max(0.0, (self._peak_equity - balance.equity) / self._peak_equity)
            daily_pnl_pct = (balance.equity - self._starting_equity) / self._starting_equity

            # ATR 簡易 (= 1% の Mark)
            atr = market.mark_price * 0.01
            size = (balance.equity * self.config.default_size_pct_of_equity) / market.mark_price
            sl_price = (
                market.mark_price - atr * (stance.sl_atr_mult if stance else self.config.sl_atr_mult)
                if decision.action == FinalAction.NEW_LONG
                else market.mark_price + atr * (stance.sl_atr_mult if stance else self.config.sl_atr_mult)
            )
            tp_price = (
                market.mark_price + atr * self.config.tp_atr_mult
                if decision.action == FinalAction.NEW_LONG
                else market.mark_price - atr * self.config.tp_atr_mult
            )

            intent = TradeIntent(
                side="long" if decision.action == FinalAction.NEW_LONG else "short",
                size=size, leverage=stance.max_lev if stance else self.config.default_leverage,
                entry_price=market.mark_price, sl_price=sl_price, tp_price=tp_price,
                symbol=market.symbol, decision_trace_id=decision_trace_id,
            )
            ev = (atr * self.config.tp_atr_mult) * size  # 期待利益 (シンプル)
            slip = estimate_slippage_pct(size, market.bid_top5_depth)
            slip_cost = market.mark_price * slip * size

            gate_ctx = GateContext(
                current_equity=balance.equity,
                daily_pnl_pct=daily_pnl_pct,
                total_dd_pct=total_dd_pct,
                api_latency_ms=api_latency_ms,
                bid_depth_top5=market.bid_top5_depth,
                bid_depth_baseline=self._baseline_depth,
                ask_depth_top5=market.ask_top5_depth,
                ask_depth_baseline=self._baseline_depth,
                last_price=market.last_price, mark_price=market.mark_price,
                expected_value=ev,
                fee_estimate=abs(size * market.mark_price * 0.00075),
                slippage_estimate=slip_cost,
                current_atr=atr,
                explanation=self.explanation_provider(stance, market) if stance else "no stance",
            )
            gate = run_order_gate(intent, gate_ctx, self.gate_config)
            if gate.result == GateResult.APPROVE:
                ord_side = OrderSide.BUY if intent.side == "long" else OrderSide.SELL
                r = self.exchange.place_order(
                    symbol=market.symbol, side=ord_side, size=size,
                    order_type=OrderType.MARKET, leverage=intent.leverage,
                    decision_trace_id=decision_trace_id,
                    sl_price=sl_price, tp_price=tp_price, sl_reduce_only=True,
                )
                event = self._make_event(now, market, stance, ttl_action, fg_signal,
                                          decision, r, decision_trace_id,
                                          notes=f"gate APPROVE: {gate.reason}")
                self._tick_log.append(event)
                self._prev_market = market
                return event
            else:
                event = self._make_event(now, market, stance, ttl_action, fg_signal,
                                          decision, None, decision_trace_id,
                                          notes=f"gate REJECT at {gate.failed_step}: {gate.reason}")
                self._tick_log.append(event)
                self._prev_market = market
                return event

        # 9. SKIP / HOLD
        event = self._make_event(now, market, stance, ttl_action, fg_signal,
                                  decision, None, decision_trace_id)
        self._tick_log.append(event)
        self._prev_market = market
        return event

    def _make_event(self, now, market, stance, ttl_action, fg_signal, decision,
                    order_result, decision_trace_id, notes=""):
        return TickEvent(
            timestamp=now,
            market={"price": market.mark_price, "spread": market.spread,
                    "fr": market.funding_rate, "bid_depth": market.bid_top5_depth},
            stance_used={"stance": stance.stance, "confidence": stance.confidence,
                         "direction": stance.direction, "risk": stance.risk_level} if stance else None,
            ttl_action=ttl_action.value if hasattr(ttl_action, 'value') else str(ttl_action),
            fast_signal=fg_signal.value,
            final_action=decision.action.value,
            order_result={
                "status": order_result.status,
                "filled_price": order_result.filled_price,
                "size": order_result.filled_size,
                "fees": order_result.fees,
                "slippage": order_result.slippage,
                "error": order_result.error,
            } if order_result else None,
            reason=decision.reason,
            decision_trace_id=decision_trace_id,
            notes=notes,
        )

    def get_log(self) -> list[TickEvent]:
        return list(self._tick_log)

    def save_log(self, path: str):
        with open(path, 'w') as f:
            for e in self._tick_log:
                d = {
                    "timestamp": e.timestamp.isoformat(),
                    "market": e.market,
                    "stance_used": e.stance_used,
                    "ttl_action": e.ttl_action,
                    "fast_signal": e.fast_signal,
                    "final_action": e.final_action,
                    "order_result": e.order_result,
                    "reason": e.reason,
                    "decision_trace_id": e.decision_trace_id,
                    "notes": e.notes,
                }
                f.write(json.dumps(d, ensure_ascii=False) + "\n")
