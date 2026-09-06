"""Simulated exchange matching engine with fees, slippage, margin, and liquidation."""

import uuid
from decimal import Decimal

from src.backtest.models import BacktestConfig, SimulatedTrade
from src.domain.enums import OrderSide, PositionSide
from src.domain.models import Candle, OrderIntent, PositionSnapshot


class SimulatedExchange:
    """Simulates realistic Binance Futures execution without network calls."""

    def __init__(self, config: BacktestConfig) -> None:
        self.config = config
        self.wallet_balance = config.initial_balance
        self.position: PositionSnapshot | None = None
        self.closed_trades: list[SimulatedTrade] = []
        self.total_fees_paid = Decimal("0.0")
        self.total_funding_paid = Decimal("0.0")
        self.liquidations_count = 0
        self.active_trade: SimulatedTrade | None = None

    def has_open_position(self) -> bool:
        """Return True if there is currently an open position."""
        return self.position is not None and self.position.size > Decimal("0")

    def process_order(self, intent: OrderIntent, candle: Candle) -> SimulatedTrade | None:
        """Process an OrderIntent against candle price bounds."""
        # Limit buy check: candle low must reach or dip below order price
        if intent.side == OrderSide.BUY:
            if candle.low <= intent.price:
                # Fill price adjusted for slippage (slippage pushes buy price slightly higher)
                slippage_multiplier = Decimal("1.0") + self.config.slippage_pct
                fill_price = intent.price * slippage_multiplier
                fee = intent.notional * self.config.taker_fee
                self.total_fees_paid += fee
                self.wallet_balance -= fee

                # Open or add to position
                if self.position is None:
                    # Estimated liquidation price based on leverage
                    margin = intent.notional / self.config.user_risk_config.leverage
                    liq_price = fill_price * (
                        Decimal("1.0") - (Decimal("1.0") / self.config.user_risk_config.leverage)
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
                else:
                    # DCA addition: average entry price
                    new_size = self.position.size + intent.quantity
                    new_notional = (self.position.size * self.position.entry_price) + (
                        intent.quantity * fill_price
                    )
                    avg_entry = new_notional / new_size
                    new_margin = new_notional / self.config.user_risk_config.leverage
                    liq_price = avg_entry * (
                        Decimal("1.0") - (Decimal("1.0") / self.config.user_risk_config.leverage)
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

                trade = SimulatedTrade(
                    trade_id=str(uuid.uuid4())[:8],
                    entry_time=candle.open_time,
                    entry_price=fill_price,
                    size=intent.quantity,
                    notional=intent.notional,
                    fees_paid=fee,
                    is_dca=intent.is_dca,
                )
                self.active_trade = trade
                return trade

        # Sell order execution (closing or reducing existing long position)
        if intent.side == OrderSide.SELL and self.position is not None:
            # For LIMIT sells, candle high must reach or exceed order price
            can_fill = candle.high >= intent.price if intent.order_type == "LIMIT" else True
            if can_fill:
                slippage_multiplier = Decimal("1.0") - self.config.slippage_pct
                fill_price = intent.price * slippage_multiplier
                executed_qty = min(intent.quantity, self.position.size)
                notional = executed_qty * fill_price
                fee_rate = (
                    self.config.maker_fee if intent.order_type == "LIMIT" else self.config.taker_fee
                )
                fee = notional * fee_rate
                self.total_fees_paid += fee
                self.wallet_balance -= fee

                realized_pnl = (fill_price - self.position.entry_price) * executed_qty
                self.wallet_balance += realized_pnl

                remaining_qty = self.position.size - executed_qty
                if remaining_qty <= Decimal("0"):
                    # Position completely closed
                    if self.active_trade is not None:
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
                    # Partial exit
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
                        self.active_trade = self.active_trade.model_copy(
                            update={
                                "realized_pnl": self.active_trade.realized_pnl + realized_pnl,
                                "fees_paid": self.active_trade.fees_paid + fee,
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
        if self.position is None:
            return False

        if candle.low <= self.position.liquidation_price:
            # Forced liquidation
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
