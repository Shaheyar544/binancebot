"""Simulated exchange matching engine with fees, slippage, margin, and liquidation."""

import uuid
from decimal import Decimal

from src.backtest.models import (
    BacktestConfig,
    LimitFillModel,
    LiquidationModelPolicy,
    SimulatedTrade,
)
from src.domain.enums import LiquidityRole, OrderSide, PositionSide
from src.domain.models import Candle, OrderIntent, PositionSnapshot
from src.risk.liquidation import ExchangeLiquidationEstimator


class SimulatedExchange:
    """Simulates realistic Binance Futures execution without network calls."""

    def __init__(
        self,
        config: BacktestConfig,
        estimator: ExchangeLiquidationEstimator | None = None,
    ) -> None:
        self.config = config
        self.policy = config.execution_policy
        self.fee_profile = self.policy.fee_profile
        self.estimator = estimator
        self.wallet_balance = config.initial_balance
        self.position: PositionSnapshot | None = None
        self.closed_trades: list[SimulatedTrade] = []
        self.total_fees_paid = Decimal("0.0")
        self.total_maker_fees_paid = Decimal("0.0")
        self.total_taker_fees_paid = Decimal("0.0")
        self.total_funding_paid = Decimal("0.0")
        self.liquidations_count = 0
        self.active_trade: SimulatedTrade | None = None
        self.dca_fills_count = 0
        self.maker_entry_count = 0
        self.taker_entry_count = 0
        self.maker_exit_count = 0
        self.taker_exit_count = 0

    def has_open_position(self) -> bool:
        """Return True if there is currently an open position."""
        return self.position is not None and self.position.size > Decimal("0")

    def can_fill_order(self, intent: OrderIntent, candle: Candle) -> bool:
        """Determine whether an order satisfies fill criteria against candle bounds."""
        if intent.side == OrderSide.BUY:
            if intent.order_type == "MARKET":
                return True
            # Limit Buy
            if self.policy.limit_fill_model == LimitFillModel.CROSS:
                return candle.low < intent.price
            return candle.low <= intent.price

        if intent.side == OrderSide.SELL:
            if intent.order_type == "MARKET":
                return True
            # Limit Sell
            if self.policy.limit_fill_model == LimitFillModel.CROSS:
                return candle.high > intent.price
            return candle.high >= intent.price

        return False

    def determine_liquidity_role(self, intent: OrderIntent, candle: Candle) -> LiquidityRole:
        """Distinguish liquidity role based on marketability rather than order type alone.

        A MARKET order always removes liquidity (TAKER).
        A LIMIT order is marketable (TAKER) if:
        - BUY: limit price > candle.open (crosses available liquidity above open)
        - SELL: limit price < candle.open (marketable sell below open)

        Passive resting orders:
        - BUY LIMIT at or below candle.open rests in order book -> MAKER (0.02% fee)
        - SELL TP LIMIT placed above candle.open rests in order book -> MAKER (0.02% fee)
        - Stop loss / emergency exits -> TAKER (0.05% fee + slippage)
        """
        if intent.order_type == "MARKET":
            return LiquidityRole.TAKER

        # Take Profit limit orders resting above market
        if intent.side == OrderSide.SELL:
            if "TP" in intent.client_order_id or "PARTIAL_TP" in intent.client_order_id:
                if intent.price >= candle.open:
                    return LiquidityRole.MAKER
                return LiquidityRole.TAKER
            # Other limit sells (e.g. stop loss limit)
            if intent.price <= candle.open:
                return LiquidityRole.TAKER
            return LiquidityRole.MAKER

        if intent.side == OrderSide.BUY:
            # Passive entry or DCA limit order resting on the bid
            if intent.price <= candle.open:
                return LiquidityRole.MAKER
            return LiquidityRole.TAKER

        return LiquidityRole.TAKER

    def process_order(self, intent: OrderIntent, candle: Candle) -> SimulatedTrade | None:
        """Process an OrderIntent against candle price bounds preserving multi-fill lifecycle."""
        if not self.can_fill_order(intent, candle):
            return None

        liquidity_role = self.determine_liquidity_role(intent, candle)
        is_taker = liquidity_role == LiquidityRole.TAKER

        # Use fee profile as single authoritative source of fee configuration
        fee_rate = self.fee_profile.taker_fee if is_taker else self.fee_profile.maker_fee

        # BUY execution (opening new position or DCA scale-in)
        if intent.side == OrderSide.BUY:
            slippage_mult = (
                Decimal("1.0") + self.policy.slippage_pct if is_taker else Decimal("1.0")
            )
            fill_price = intent.price * slippage_mult
            actual_notional = intent.quantity * fill_price
            fee = actual_notional * fee_rate

            self.total_fees_paid += fee
            if is_taker:
                self.total_taker_fees_paid += fee
                self.taker_entry_count += 1
            else:
                self.total_maker_fees_paid += fee
                self.maker_entry_count += 1
            self.wallet_balance -= fee

            if self.position is None:
                # Initial position entry
                self.dca_fills_count = 0
                margin = actual_notional / self.config.user_risk_config.leverage
                liq_price = None
                if (
                    self.policy.liquidation_policy == LiquidationModelPolicy.EXPLICIT_MODEL
                    and self.estimator is not None
                ):
                    liq_price = self.estimator.estimate_liquidation_price(
                        entry_price=fill_price,
                        leverage=self.config.user_risk_config.leverage,
                        allocated_funds=self.config.user_risk_config.allocated_funds,
                    )
                self.position = PositionSnapshot(
                    symbol=intent.symbol,
                    side=PositionSide.LONG,
                    size=intent.quantity,
                    entry_price=fill_price,
                    leverage=self.config.user_risk_config.leverage,
                    margin=margin,
                    liquidation_price=liq_price,
                    unrealized_pnl=Decimal("0.0"),
                    updated_at=candle.open_time,
                )
                trade = SimulatedTrade(
                    trade_id=str(uuid.uuid4())[:8],
                    entry_time=candle.open_time,
                    entry_price=fill_price,
                    size=intent.quantity,
                    notional=actual_notional,
                    fees_paid=fee,
                    maker_fees_paid=fee if not is_taker else Decimal("0.0"),
                    taker_fees_paid=fee if is_taker else Decimal("0.0"),
                    is_dca=False,
                )
                self.active_trade = trade
                return trade
            else:
                # DCA Scale-In: update parent trade and position without replacing active trade ID
                self.dca_fills_count += 1
                new_size = self.position.size + intent.quantity
                new_notional = (self.position.size * self.position.entry_price) + actual_notional
                avg_entry = new_notional / new_size
                new_margin = new_notional / self.config.user_risk_config.leverage
                liq_price = None
                if (
                    self.policy.liquidation_policy == LiquidationModelPolicy.EXPLICIT_MODEL
                    and self.estimator is not None
                ):
                    liq_price = self.estimator.estimate_liquidation_price(
                        entry_price=avg_entry,
                        leverage=self.config.user_risk_config.leverage,
                        allocated_funds=self.config.user_risk_config.allocated_funds,
                    )
                self.position = PositionSnapshot(
                    symbol=intent.symbol,
                    side=PositionSide.LONG,
                    size=new_size,
                    entry_price=avg_entry,
                    leverage=self.config.user_risk_config.leverage,
                    margin=new_margin,
                    liquidation_price=liq_price,
                    unrealized_pnl=Decimal("0.0"),
                    updated_at=candle.open_time,
                )
                if self.active_trade is not None:
                    trade_maker = self.active_trade.maker_fees_paid + (
                        fee if not is_taker else Decimal("0.0")
                    )
                    trade_taker = self.active_trade.taker_fees_paid + (
                        fee if is_taker else Decimal("0.0")
                    )
                    self.active_trade = self.active_trade.model_copy(
                        update={
                            "size": new_size,
                            "notional": new_notional,
                            "entry_price": avg_entry,
                            "fees_paid": self.active_trade.fees_paid + fee,
                            "maker_fees_paid": trade_maker,
                            "taker_fees_paid": trade_taker,
                            "is_dca": True,
                        }
                    )
                return self.active_trade

        # SELL execution (partial take profit or full position exit)
        if intent.side == OrderSide.SELL and self.position is not None:
            slippage_mult = (
                Decimal("1.0") - self.policy.slippage_pct if is_taker else Decimal("1.0")
            )
            fill_price = intent.price * slippage_mult
            executed_qty = min(intent.quantity, self.position.size)
            notional = executed_qty * fill_price
            fee = notional * fee_rate

            self.total_fees_paid += fee
            if is_taker:
                self.total_taker_fees_paid += fee
                self.taker_exit_count += 1
            else:
                self.total_maker_fees_paid += fee
                self.maker_exit_count += 1
            self.wallet_balance -= fee

            # Realized PnL strictly on the executed portion
            realized_pnl = (fill_price - self.position.entry_price) * executed_qty
            self.wallet_balance += realized_pnl

            remaining_qty = self.position.size - executed_qty

            if remaining_qty <= Decimal("0"):
                # Position completely closed
                if self.active_trade is not None:
                    trade_maker = self.active_trade.maker_fees_paid + (
                        fee if not is_taker else Decimal("0.0")
                    )
                    trade_taker = self.active_trade.taker_fees_paid + (
                        fee if is_taker else Decimal("0.0")
                    )
                    closed = SimulatedTrade(
                        trade_id=self.active_trade.trade_id,
                        entry_time=self.active_trade.entry_time,
                        exit_time=candle.close_time,
                        entry_price=self.active_trade.entry_price,
                        exit_price=fill_price,
                        size=self.active_trade.size,
                        notional=self.active_trade.notional,
                        realized_pnl=self.active_trade.realized_pnl + realized_pnl,
                        fees_paid=self.active_trade.fees_paid + fee,
                        maker_fees_paid=trade_maker,
                        taker_fees_paid=trade_taker,
                        funding_paid=self.active_trade.funding_paid,
                        is_dca=self.active_trade.is_dca,
                        exit_reason=intent.reason,
                        max_favorable_excursion=self.active_trade.max_favorable_excursion,
                        max_adverse_excursion=self.active_trade.max_adverse_excursion,
                    )
                    self.closed_trades.append(closed)
                    self.active_trade = None
                self.position = None
            else:
                # Partial exit: maintain open position and update active trade metrics
                new_margin = self.position.margin * (remaining_qty / self.position.size)
                self.position = PositionSnapshot(
                    symbol=self.position.symbol,
                    side=self.position.side,
                    size=remaining_qty,
                    entry_price=self.position.entry_price,
                    leverage=self.position.leverage,
                    margin=new_margin,
                    liquidation_price=self.position.liquidation_price,
                    unrealized_pnl=self.position.unrealized_pnl,
                    updated_at=candle.open_time,
                )
                if self.active_trade is not None:
                    trade_maker = self.active_trade.maker_fees_paid + (
                        fee if not is_taker else Decimal("0.0")
                    )
                    trade_taker = self.active_trade.taker_fees_paid + (
                        fee if is_taker else Decimal("0.0")
                    )
                    self.active_trade = self.active_trade.model_copy(
                        update={
                            "realized_pnl": self.active_trade.realized_pnl + realized_pnl,
                            "fees_paid": self.active_trade.fees_paid + fee,
                            "maker_fees_paid": trade_maker,
                            "taker_fees_paid": trade_taker,
                        }
                    )
            return self.active_trade

        return None

    def update_excursions(self, candle: Candle) -> None:
        """Update max favorable and adverse excursions for the active position."""
        if self.position is not None and self.active_trade is not None:
            favorable = max(
                Decimal("0.0"),
                (candle.high - self.position.entry_price) * self.position.size,
            )
            adverse = max(
                Decimal("0.0"),
                (self.position.entry_price - candle.low) * self.position.size,
            )
            new_fav = max(self.active_trade.max_favorable_excursion, favorable)
            new_adv = max(self.active_trade.max_adverse_excursion, adverse)
            self.active_trade = self.active_trade.model_copy(
                update={
                    "max_favorable_excursion": new_fav,
                    "max_adverse_excursion": new_adv,
                }
            )

    def check_liquidation(self, candle: Candle) -> bool:
        """Check if candle low breaches liquidation threshold."""
        if self.position is None or self.position.liquidation_price is None:
            return False

        if candle.low <= self.position.liquidation_price:
            self.liquidations_count += 1
            loss = self.position.margin
            self.wallet_balance -= loss

            if self.active_trade is not None:
                closed = SimulatedTrade(
                    trade_id=self.active_trade.trade_id,
                    entry_time=self.active_trade.entry_time,
                    exit_time=candle.close_time,
                    entry_price=self.active_trade.entry_price,
                    exit_price=self.position.liquidation_price,
                    size=self.position.size,
                    notional=self.position.size * self.active_trade.entry_price,
                    realized_pnl=-loss,
                    fees_paid=self.active_trade.fees_paid,
                    funding_paid=self.active_trade.funding_paid,
                    is_dca=self.active_trade.is_dca,
                    exit_reason="LIQUIDATION",
                )
                self.closed_trades.append(closed)
                self.active_trade = None

            self.position = None
            return True

        return False

    def apply_funding(self, timestamp: int, funding_rate: Decimal) -> None:
        """Debit or credit funding every 8 hours."""
        if self.position is not None:
            notional = self.position.size * self.position.entry_price
            funding_payment = notional * funding_rate
            self.total_funding_paid += funding_payment
            self.wallet_balance -= funding_payment
            if self.active_trade is not None:
                new_funding = self.active_trade.funding_paid + funding_payment
                self.active_trade = self.active_trade.model_copy(
                    update={"funding_paid": new_funding}
                )
