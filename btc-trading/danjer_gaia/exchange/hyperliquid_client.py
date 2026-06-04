"""
Project danjer-GAIA — Hyperliquid Client
==========================================
3者会議 Round 30-38 (戦略Z 改訂版 v8) で主取引所に確定。

機能:
- read-only: Info クラス経由で残高・ポジション・市場データ取得 (秘密鍵不要)
- 発注: Exchange クラス経由で place_order / close_position (秘密鍵必須)
- testnet/mainnet 切替 (base_url 引数)
- mock_mode: Shuji Wallet 未準備時のオフライン動作 (Phase 0 着手前のテスト用)

公式 Python SDK:
- pip install hyperliquid-python-sdk
- https://github.com/hyperliquid-dex/hyperliquid-python-sdk

testnet endpoints:
- API: https://api.hyperliquid-testnet.xyz
- WebSocket: wss://api.hyperliquid-testnet.xyz/ws
- HyperEVM RPC: https://rpc.hyperliquid-testnet.xyz/evm (Chain ID 998)

手数料モデル:
- maker: -0.001% (rebate、 取引するほど利益)
- taker: 0.035%
- BTC perp スプレッド: 約 $0.30 (薄い)

v8 セキュリティ:
- 秘密鍵は GCP Secret Manager 経由でのみ読み込み (環境変数直接は禁止)
- IAM制限 + IP制限 + 出金先Whitelist (R83対策)
- Wallet階層: Phase 2-3 は MetaMask Hot のみ、 Phase 4 Cap 1 直前で Ledger Cold 追加 (R89対策)
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Callable, Any
import uuid

from .base import (
    ExchangeBase, OrderType, OrderSide, OrderResult, Position, Balance,
    MarketSnapshot, ExchangeError,
)

# ============================================================
# Endpoints (Round 38 確定)
# ============================================================
MAINNET_API_URL = "https://api.hyperliquid.xyz"
MAINNET_WS_URL = "wss://api.hyperliquid.xyz/ws"
TESTNET_API_URL = "https://api.hyperliquid-testnet.xyz"
TESTNET_WS_URL = "wss://api.hyperliquid-testnet.xyz/ws"

# Hyperliquid 手数料モデル (Round 34 検証済)
MAKER_FEE_PCT = -0.00001  # -0.001% rebate
TAKER_FEE_PCT = 0.00035   # 0.035%


@dataclass
class HyperliquidConfig:
    """Hyperliquid クライアント設定"""
    base_url: str = MAINNET_API_URL
    ws_url: str = MAINNET_WS_URL
    account_address: Optional[str] = None  # 公開アドレス (0x...)
    private_key: Optional[str] = None      # 秘密鍵 (発注時必須、 GCP Secret Manager 経由)
    mock_mode: bool = False                # True なら SDK 読み込まず、 オフライン動作
    min_size: float = 0.0001               # 最小注文サイズ
    skip_ws: bool = False                  # WebSocket初期化スキップ (read-only時)


class HyperliquidClient(ExchangeBase):
    """
    Hyperliquid DEX クライアント。

    Phase 2-3 (Stage 0/1/2): mock_mode or read-only + Hot Wallet 発注
    Phase 4 Cap 1+: Ledger Cold + MetaMask Hot 二段運用

    使い方:
        # Phase 0 接続検証 (Shuji Wallet なし、 mock_mode):
        client = HyperliquidClient(HyperliquidConfig(mock_mode=True))

        # Phase 2 testnet (Shuji Wallet 作成後):
        client = HyperliquidClient(HyperliquidConfig(
            base_url=TESTNET_API_URL,
            account_address="0x...",
            private_key=None,  # read-only
        ))

        # Phase 2 mainnet 発注 (秘密鍵 必須):
        from os import environ
        client = HyperliquidClient(HyperliquidConfig(
            account_address=environ["HL_ACCOUNT_ADDRESS"],
            private_key=environ["HL_PRIVATE_KEY"],  # GCP Secret Manager 経由
        ))
    """

    name = "hyperliquid"

    def __init__(self, config: Optional[HyperliquidConfig] = None):
        self.config = config or HyperliquidConfig()
        self._info = None
        self._exchange = None
        self._wallet = None
        self._mock_positions: dict[str, Position] = {}
        self._mock_balance = Balance(equity=0, available=0, used=0, currency="USDC")
        self._mock_market_cache: dict[str, MarketSnapshot] = {}

        if not self.config.mock_mode:
            self._initialize_sdk()

    def _initialize_sdk(self):
        """公式 SDK 初期化 (mock_mode=False時のみ)"""
        try:
            from hyperliquid.info import Info  # type: ignore
            self._info = Info(self.config.base_url, skip_ws=self.config.skip_ws)
        except ImportError as e:
            raise ExchangeError(
                f"hyperliquid-python-sdk not installed. "
                f"Run: pip install hyperliquid-python-sdk. Original: {e}"
            )

        if self.config.private_key:
            try:
                from eth_account import Account  # type: ignore
                from hyperliquid.exchange import Exchange  # type: ignore
                self._wallet = Account.from_key(self.config.private_key)
                self._exchange = Exchange(
                    self._wallet, self.config.base_url,
                    account_address=self.config.account_address,
                )
            except ImportError as e:
                raise ExchangeError(
                    f"eth_account not installed. Run: pip install eth_account. Original: {e}"
                )

    # ==================== mock_mode helper (Phase 0テスト用) ====================
    def set_mock_market(self, snapshot: MarketSnapshot):
        """mock_mode で市場データを注入"""
        if not self.config.mock_mode:
            raise ExchangeError("set_mock_market is only available in mock_mode")
        self._mock_market_cache[snapshot.symbol] = snapshot

    def set_mock_balance(self, balance: Balance):
        """mock_mode で残高を注入"""
        if not self.config.mock_mode:
            raise ExchangeError("set_mock_balance is only available in mock_mode")
        self._mock_balance = balance

    # ==================== ExchangeBase 実装 ====================
    def get_balance(self) -> Balance:
        if self.config.mock_mode:
            return self._mock_balance
        if not self._info or not self.config.account_address:
            raise ExchangeError("account_address required for get_balance")
        try:
            user_state = self._info.user_state(self.config.account_address)
            margin = user_state.get("marginSummary", {})
            account_value = float(margin.get("accountValue", 0))
            total_margin_used = float(margin.get("totalMarginUsed", 0))
            return Balance(
                equity=account_value,
                available=account_value - total_margin_used,
                used=total_margin_used,
                currency="USDC",
            )
        except Exception as e:
            raise ExchangeError(f"get_balance failed: {e}")

    def get_position(self, symbol: str) -> Optional[Position]:
        if self.config.mock_mode:
            return self._mock_positions.get(symbol)
        if not self._info or not self.config.account_address:
            raise ExchangeError("account_address required for get_position")
        try:
            user_state = self._info.user_state(self.config.account_address)
            for pos_data in user_state.get("assetPositions", []):
                position = pos_data.get("position", {})
                if position.get("coin") != symbol:
                    continue
                size_abs = abs(float(position.get("szi", 0)))
                if size_abs == 0:
                    continue
                side = "long" if float(position.get("szi", 0)) > 0 else "short"
                return Position(
                    symbol=symbol, side=side, size=size_abs,
                    entry_price=float(position.get("entryPx", 0)),
                    leverage=float(position.get("leverage", {}).get("value", 1)),
                    unrealized_pnl=float(position.get("unrealizedPnl", 0)),
                    liquidation_price=float(position.get("liquidationPx", 0) or 0),
                    sl_price=None, tp_price=None,
                    opened_at=datetime.now(timezone.utc),
                )
            return None
        except Exception as e:
            raise ExchangeError(f"get_position failed: {e}")

    def get_market(self, symbol: str) -> MarketSnapshot:
        if self.config.mock_mode:
            m = self._mock_market_cache.get(symbol)
            if not m:
                raise ExchangeError(f"No mock market data for {symbol}")
            return m
        if not self._info:
            raise ExchangeError("SDK not initialized")
        try:
            # Hyperliquid Info API: all_mids() + l2_book() + meta_and_asset_ctxs()
            mids = self._info.all_mids()
            mid_price = float(mids.get(symbol, 0))
            l2 = self._info.l2_book(symbol)
            bids = l2.get("levels", [[], []])[0][:5]
            asks = l2.get("levels", [[], []])[1][:5]
            bid_depth = sum(float(b.get("sz", 0)) for b in bids)
            ask_depth = sum(float(a.get("sz", 0)) for a in asks)
            top_bid = float(bids[0].get("px", mid_price)) if bids else mid_price
            top_ask = float(asks[0].get("px", mid_price)) if asks else mid_price
            spread = top_ask - top_bid

            meta_ctxs = self._info.meta_and_asset_ctxs()
            asset_ctx = {}
            if isinstance(meta_ctxs, list) and len(meta_ctxs) >= 2:
                universe = meta_ctxs[0].get("universe", [])
                ctxs = meta_ctxs[1]
                for i, u in enumerate(universe):
                    if u.get("name") == symbol and i < len(ctxs):
                        asset_ctx = ctxs[i]
                        break

            return MarketSnapshot(
                symbol=symbol,
                last_price=mid_price,
                mark_price=float(asset_ctx.get("markPx", mid_price)),
                bid_top5_depth=bid_depth,
                ask_top5_depth=ask_depth,
                funding_rate=float(asset_ctx.get("funding", 0)),
                open_interest=float(asset_ctx.get("openInterest", 0)),
                spread=spread,
            )
        except Exception as e:
            raise ExchangeError(f"get_market failed: {e}")

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
    ) -> OrderResult:
        if size < self.config.min_size:
            return OrderResult(
                order_id="", decision_trace_id=decision_trace_id,
                symbol=symbol, side=side, order_type=order_type,
                size=size, price=price, status="rejected",
                error=f"size {size} < min {self.config.min_size}",
            )

        if self.config.mock_mode:
            # mock 発注: paper_client と同じロジック簡略版
            return self._mock_place_order(
                symbol, side, size, order_type, leverage, decision_trace_id,
                price, sl_price, tp_price, sl_reduce_only,
            )

        if not self._exchange:
            return OrderResult(
                order_id="", decision_trace_id=decision_trace_id,
                symbol=symbol, side=side, order_type=order_type,
                size=size, price=price, status="rejected",
                error="private_key required for place_order",
            )

        try:
            is_buy = (side == OrderSide.BUY)
            # Hyperliquid SDK: market_open / order
            # 簡易: order_type=MARKET なら market_open、 LIMIT なら order
            if order_type == OrderType.MARKET:
                response = self._exchange.market_open(symbol, is_buy, size)
            else:
                if price is None:
                    return OrderResult(
                        order_id="", decision_trace_id=decision_trace_id,
                        symbol=symbol, side=side, order_type=order_type,
                        size=size, price=None, status="rejected",
                        error="price required for LIMIT order",
                    )
                response = self._exchange.order(
                    symbol, is_buy, size, price, {"limit": {"tif": "Gtc"}}
                )

            # response から約定価格・order_id 抽出
            status_obj = response.get("response", {}).get("data", {}).get("statuses", [{}])[0]
            filled_info = status_obj.get("filled", {})
            resting_info = status_obj.get("resting", {})

            order_id = str(filled_info.get("oid") or resting_info.get("oid") or uuid.uuid4())
            filled_size = float(filled_info.get("totalSz", 0))
            filled_price = float(filled_info.get("avgPx", 0))
            status_str = "filled" if filled_size > 0 else "open"

            # SL注文 (reduce_only、 R30対策)
            sl_oid = None
            if sl_price and sl_reduce_only and self._exchange:
                try:
                    sl_response = self._exchange.order(
                        symbol, not is_buy, size, sl_price,
                        {"trigger": {"isMarket": True, "triggerPx": sl_price,
                                     "tpsl": "sl"}},
                        reduce_only=True,
                    )
                    sl_status = sl_response.get("response", {}).get("data", {}).get("statuses", [{}])[0]
                    sl_oid = str(sl_status.get("resting", {}).get("oid") or "")
                except Exception:
                    pass  # SL失敗は許容、 Fast Guard が補助

            # 手数料 (推定、 maker/taker)
            is_taker = (order_type == OrderType.MARKET)
            fee_pct = TAKER_FEE_PCT if is_taker else MAKER_FEE_PCT
            fee = abs(filled_size * filled_price) * fee_pct

            return OrderResult(
                order_id=order_id, decision_trace_id=decision_trace_id,
                symbol=symbol, side=side, order_type=order_type,
                size=size, price=price,
                status=status_str, filled_size=filled_size, filled_price=filled_price,
                sl_order_id=sl_oid, fees=fee, slippage=0.0,
            )
        except Exception as e:
            return OrderResult(
                order_id="", decision_trace_id=decision_trace_id,
                symbol=symbol, side=side, order_type=order_type,
                size=size, price=price, status="rejected",
                error=f"place_order failed: {e}",
            )

    def _mock_place_order(
        self, symbol, side, size, order_type, leverage, decision_trace_id,
        price, sl_price, tp_price, sl_reduce_only,
    ) -> OrderResult:
        """mock_mode 発注 (Phase 0 テスト用)"""
        m = self._mock_market_cache.get(symbol)
        if not m:
            return OrderResult(
                order_id="", decision_trace_id=decision_trace_id,
                symbol=symbol, side=side, order_type=order_type,
                size=size, price=price, status="rejected",
                error="No mock market data",
            )
        is_buy = (side == OrderSide.BUY)
        fill_price = m.mark_price * (1.0005 if is_buy else 0.9995)
        is_taker = (order_type == OrderType.MARKET)
        fee = abs(size * fill_price) * (TAKER_FEE_PCT if is_taker else MAKER_FEE_PCT)

        position_side = "long" if is_buy else "short"
        liq_price = fill_price * (1 - 1.0 / leverage * 0.9) if is_buy \
                    else fill_price * (1 + 1.0 / leverage * 0.9)
        self._mock_positions[symbol] = Position(
            symbol=symbol, side=position_side, size=size,
            entry_price=fill_price, leverage=leverage,
            unrealized_pnl=0.0, liquidation_price=liq_price,
            sl_price=sl_price, tp_price=tp_price,
            opened_at=datetime.now(timezone.utc),
        )
        self._mock_balance.equity -= fee
        margin = (size * fill_price) / leverage
        self._mock_balance.available -= margin
        self._mock_balance.used += margin

        return OrderResult(
            order_id=str(uuid.uuid4()), decision_trace_id=decision_trace_id,
            symbol=symbol, side=side, order_type=order_type,
            size=size, price=price,
            status="filled", filled_size=size, filled_price=fill_price,
            sl_order_id=str(uuid.uuid4()) if sl_price else None,
            fees=fee, slippage=abs(fill_price - m.mark_price) * size,
        )

    def close_position(
        self, symbol: str, size: Optional[float] = None,
        decision_trace_id: str = "",
    ) -> OrderResult:
        pos = self.get_position(symbol)
        if not pos:
            return OrderResult(
                order_id="", decision_trace_id=decision_trace_id,
                symbol=symbol, side=OrderSide.SELL,
                order_type=OrderType.MARKET, size=0, price=None,
                status="rejected", error="no position",
            )
        close_size = size if size and size < pos.size else pos.size
        close_side = OrderSide.SELL if pos.side == "long" else OrderSide.BUY

        if self.config.mock_mode:
            m = self._mock_market_cache[symbol]
            fill_price = m.mark_price * (0.9995 if pos.side == "long" else 1.0005)
            fee = abs(close_size * fill_price) * TAKER_FEE_PCT
            pnl = (fill_price - pos.entry_price) * close_size if pos.side == "long" \
                  else (pos.entry_price - fill_price) * close_size
            self._mock_balance.equity += pnl - fee
            margin = (close_size * pos.entry_price) / pos.leverage
            self._mock_balance.available += margin + pnl - fee
            self._mock_balance.used -= margin
            if close_size >= pos.size:
                del self._mock_positions[symbol]
            else:
                pos.size -= close_size
            return OrderResult(
                order_id=str(uuid.uuid4()), decision_trace_id=decision_trace_id,
                symbol=symbol, side=close_side, order_type=OrderType.MARKET,
                size=close_size, price=None, status="filled",
                filled_size=close_size, filled_price=fill_price,
                fees=fee, slippage=abs(fill_price - m.mark_price) * close_size,
            )

        if not self._exchange:
            return OrderResult(
                order_id="", decision_trace_id=decision_trace_id,
                symbol=symbol, side=close_side, order_type=OrderType.MARKET,
                size=close_size, price=None, status="rejected",
                error="private_key required for close_position",
            )

        try:
            is_buy = (close_side == OrderSide.BUY)
            response = self._exchange.market_close(symbol)
            status_obj = response.get("response", {}).get("data", {}).get("statuses", [{}])[0]
            filled_info = status_obj.get("filled", {})
            filled_price = float(filled_info.get("avgPx", 0))
            fee = abs(close_size * filled_price) * TAKER_FEE_PCT
            return OrderResult(
                order_id=str(filled_info.get("oid") or uuid.uuid4()),
                decision_trace_id=decision_trace_id,
                symbol=symbol, side=close_side, order_type=OrderType.MARKET,
                size=close_size, price=None, status="filled",
                filled_size=float(filled_info.get("totalSz", close_size)),
                filled_price=filled_price, fees=fee, slippage=0.0,
            )
        except Exception as e:
            return OrderResult(
                order_id="", decision_trace_id=decision_trace_id,
                symbol=symbol, side=close_side, order_type=OrderType.MARKET,
                size=close_size, price=None, status="rejected",
                error=f"close_position failed: {e}",
            )

    def cancel_order(self, order_id: str) -> bool:
        if self.config.mock_mode:
            return True  # mock では常に成功
        if not self._exchange:
            return False
        try:
            # Hyperliquid cancel API: oid指定
            self._exchange.cancel("", int(order_id))
            return True
        except Exception:
            return False

    def subscribe_market(
        self, symbol: str,
        on_tick: Callable[[MarketSnapshot], None],
    ) -> Any:
        if self.config.mock_mode:
            return on_tick  # mock では subscribe noop
        if not self._info:
            raise ExchangeError("SDK not initialized")
        try:
            from hyperliquid.utils.types import Subscription  # type: ignore
            sub: Subscription = {"type": "l2Book", "coin": symbol}

            def callback(msg):
                try:
                    # msg は l2Book 形式、 MarketSnapshot に変換して on_tick へ
                    snapshot = self.get_market(symbol)
                    on_tick(snapshot)
                except Exception:
                    pass

            handle = self._info.subscribe(sub, callback)
            return handle
        except Exception as e:
            raise ExchangeError(f"subscribe_market failed: {e}")

    def health_check(self) -> bool:
        if self.config.mock_mode:
            return self._mock_balance.equity > 0
        try:
            balance = self.get_balance()
            return balance.equity >= 0  # 残高ゼロでも 接続OK なら True
        except Exception:
            return False
