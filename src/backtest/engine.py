"""Event-driven no-lookahead backtesting engine."""

from collections.abc import Sequence
from decimal import Decimal

from src.analysis.indicators import _decimal_sqrt
from src.analysis.models import MultiTimeframeAnalysis, TimeframeAnalyzer
from src.analysis.regime import RegimeClassifier
from src.backtest.exchange import SimulatedExchange
from src.backtest.models import BacktestConfig, BacktestResult, SimulatedTrade
from src.domain.enums import DecisionState, Timeframe
from src.domain.models import Candle
from src.exchange.metadata import SymbolFilters
from src.market_data.enums import MarketDataHealth
from src.risk.engine import RiskEngine
from src.risk.models import AccountRiskState
from src.risk.sizer import PositionSizer
from src.strategy.engine import ExitManager, StrategyEngine
from src.strategy.entry_families import EntryOrchestrator

DEFAULT_XAU_FILTERS = SymbolFilters(
    symbol="XAUUSDT",
    status="TRADING",
    contract_type="PERPETUAL",
    base_asset="XAU",
    quote_asset="USDT",
    price_precision=2,
    quantity_precision=3,
    tick_size=Decimal("0.01"),
    min_price=Decimal("100.00"),
    max_price=Decimal("100000.00"),
    step_size=Decimal("0.001"),
    min_qty=Decimal("0.001"),
    max_qty=Decimal("1000.000"),
    min_notional=Decimal("5.0"),
)


class StandardLiquidationEstimator:
    """Standard liquidation estimator for backtesting."""

    def estimate_liquidation_price(
        self,
        entry_price: Decimal,
        leverage: Decimal,
        allocated_funds: Decimal,
    ) -> Decimal:
        if leverage <= Decimal("0"):
            return Decimal("0")
        return entry_price * (Decimal("1.0") - (Decimal("1.0") / leverage))


def resample_candles(
    candles_15m: Sequence[Candle],
    target_timeframe: Timeframe,
) -> list[Candle]:
    """Resample 15M candles into strictly completed target timeframe candles.

    Zero-lookahead guarantee: A target candle is only emitted once its constituent
    15M candles have fully completed. Incomplete target buckets are never emitted.
    """
    duration_map = {
        Timeframe.M15: 900_000,
        Timeframe.H1: 3_600_000,
        Timeframe.H4: 14_400_000,
        Timeframe.D1: 86_400_000,
    }
    target_ms = duration_map.get(target_timeframe)
    if target_ms is None or target_timeframe == Timeframe.M15:
        return list(candles_15m)

    if not candles_15m:
        return []

    buckets: dict[int, list[Candle]] = {}
    for c in candles_15m:
        bucket_start = (c.open_time // target_ms) * target_ms
        buckets.setdefault(bucket_start, []).append(c)

    resampled: list[Candle] = []
    symbol = candles_15m[0].symbol

    for b_start, c_list in sorted(buckets.items()):
        b_end = b_start + target_ms - 1
        if c_list[-1].close_time >= b_end:
            resampled.append(
                Candle(
                    symbol=symbol,
                    timeframe=target_timeframe,
                    open_time=b_start,
                    open=c_list[0].open,
                    high=max(c.high for c in c_list),
                    low=min(c.low for c in c_list),
                    close=c_list[-1].close,
                    volume=sum((c.volume for c in c_list), Decimal("0.0")),
                    close_time=b_end,
                    is_closed=True,
                )
            )

    return resampled


class BacktestEngine:
    """Orchestrates chronological forward simulation across historical candles."""

    def __init__(
        self,
        config: BacktestConfig,
        strategy_engine: StrategyEngine | None = None,
        risk_engine: RiskEngine | None = None,
        exit_manager: ExitManager | None = None,
        filters: SymbolFilters | None = None,
    ) -> None:
        self.config = config
        self.exchange = SimulatedExchange(config=config)
        self.strategy_engine = strategy_engine or StrategyEngine(min_entry_score=80)
        self.exit_manager = exit_manager or ExitManager()
        self.orchestrator = EntryOrchestrator()
        self.regime_classifier = RegimeClassifier()
        self.filters = filters or DEFAULT_XAU_FILTERS
        self.risk_engine = risk_engine or RiskEngine(
            config=config.user_risk_config,
            filters=self.filters,
            estimator=StandardLiquidationEstimator(),
        )
        self.risk_sizer = PositionSizer(filters=self.filters)

    def get_historical_slice(
        self,
        candles: Sequence[Candle],
        current_idx: int,
    ) -> list[Candle]:
        """Return finalized candles strictly up to current_idx with zero future data."""
        if current_idx < 0 or current_idx >= len(candles):
            raise ValueError(f"Invalid index {current_idx} for sequence of length {len(candles)}")
        return list(candles[: current_idx + 1])

    def is_news_locked(self, timestamp: int) -> bool:
        """Check if timestamp is within [event - 24h, event + 24h] for any event."""
        lock_window_ms = 24 * 3600 * 1000  # 24 hours in milliseconds
        for event_time in self.config.news_event_timestamps:
            if (event_time - lock_window_ms) <= timestamp <= (event_time + lock_window_ms):
                return True
        return False

    def run(self, candles: Sequence[Candle]) -> BacktestResult:
        """Run event-driven simulation over chronological candles."""
        if not candles:
            return BacktestResult()

        current_stop_loss: Decimal | None = None
        highest_price_since_entry = Decimal("0.0")
        entry_timestamp = 0
        partial_tp_taken = False
        current_adds = 0
        equity_peak = self.config.initial_balance
        max_drawdown_pct = Decimal("0.0")
        max_exposure = Decimal("0.0")
        max_adds = 0

        for idx, candle in enumerate(candles):
            history = self.get_historical_slice(candles, idx)

            # 1. Funding check (every 8 hours: at 00:00, 08:00, 16:00 UTC)
            if self.exchange.has_open_position():
                if candle.open_time % 28_800_000 < 900_000:
                    self.exchange.apply_funding(candle.open_time, funding_rate=Decimal("0.0001"))

            # 2. Check liquidation
            if self.exchange.check_liquidation(candle):
                current_stop_loss = None
                partial_tp_taken = False
                current_adds = 0
                continue

            # 3. Excursions and exposure tracking
            if self.exchange.has_open_position() and self.exchange.position is not None:
                self.exchange.update_excursions(candle)
                highest_price_since_entry = max(highest_price_since_entry, candle.high)
                exposure = self.exchange.position.size * candle.close
                max_exposure = max(max_exposure, exposure)

                # 4. Emergency loss check
                if self.risk_engine.is_emergency_loss_breached(
                    self.exchange.position,
                    self.exchange.total_fees_paid,
                    self.exchange.total_funding_paid,
                ):
                    exit_intent = self.risk_sizer.create_exit_intent(
                        price=candle.close,
                        quantity=self.exchange.position.size,
                        client_order_id=f"EMERGENCY_{candle.open_time}",
                        reason="EMERGENCY_STOP_LOSS_BREACHED",
                        order_type="MARKET",
                    )
                    self.exchange.process_order(exit_intent, candle)
                    current_stop_loss = None
                    partial_tp_taken = False
                    current_adds = 0
                    continue

                # 5. Exit evaluation (Stops, Trailing Stop, Partial TP)
                if current_stop_loss is not None:
                    exit_decision = self.exit_manager.evaluate_position(
                        current_price=candle.close,
                        entry_price=self.exchange.position.entry_price,
                        stop_loss_ref=current_stop_loss,
                        atr=Decimal("15.0"),
                        highest_price_since_entry=highest_price_since_entry,
                        entry_timestamp=entry_timestamp,
                        current_timestamp=candle.open_time,
                        partial_tp_already_taken=partial_tp_taken,
                    )

                    if exit_decision.should_exit:
                        if exit_decision.exit_state == DecisionState.PARTIAL_TP:
                            exit_qty = self.exchange.position.size * (
                                exit_decision.portion_pct / Decimal("100.0")
                            )
                            exit_intent = self.risk_sizer.create_exit_intent(
                                price=candle.close,
                                quantity=exit_qty,
                                client_order_id=f"PARTIAL_TP_{candle.open_time}",
                                reason=exit_decision.reason,
                                order_type="LIMIT",
                            )
                            self.exchange.process_order(exit_intent, candle)
                            partial_tp_taken = True
                        elif exit_decision.exit_state == DecisionState.EXIT:
                            fill_p = (
                                min(candle.close, current_stop_loss)
                                if candle.low <= current_stop_loss
                                else candle.close
                            )
                            exit_intent = self.risk_sizer.create_exit_intent(
                                price=fill_p,
                                quantity=self.exchange.position.size,
                                client_order_id=f"EXIT_{candle.open_time}",
                                reason=exit_decision.reason,
                                order_type="MARKET",
                            )
                            self.exchange.process_order(exit_intent, candle)
                            current_stop_loss = None
                            partial_tp_taken = False
                            current_adds = 0

            # 6. Strategy Evaluation and Entry / DCA
            if not self.is_news_locked(candle.open_time) and len(history) >= 20:
                analysis_15m = TimeframeAnalyzer.analyze_timeframe(history, Timeframe.M15)
                candles_1h = resample_candles(history, Timeframe.H1)
                candles_4h = resample_candles(history, Timeframe.H4)
                candles_1d = resample_candles(history, Timeframe.D1)

                analysis_1h = (
                    TimeframeAnalyzer.analyze_timeframe(candles_1h, Timeframe.H1)
                    if candles_1h
                    else analysis_15m.model_copy(update={"timeframe": Timeframe.H1})
                )
                analysis_4h = (
                    TimeframeAnalyzer.analyze_timeframe(candles_4h, Timeframe.H4)
                    if candles_4h
                    else analysis_15m.model_copy(update={"timeframe": Timeframe.H4})
                )
                analysis_1d = (
                    TimeframeAnalyzer.analyze_timeframe(candles_1d, Timeframe.D1)
                    if candles_1d
                    else analysis_15m.model_copy(update={"timeframe": Timeframe.D1})
                )

                regime = self.regime_classifier.classify(
                    analysis_15m.ema_10,
                    analysis_15m.ema_20,
                    analysis_15m.ema_50,
                    analysis_15m.ema_200,
                    analysis_15m.current_close,
                    analysis_15m.atr,
                    analysis_15m.atr,
                    analysis_15m.is_bullish,
                )

                mtf = MultiTimeframeAnalysis(
                    symbol=candle.symbol,
                    regime=regime,
                    analysis_1d=analysis_1d,
                    analysis_4h=analysis_4h,
                    analysis_1h=analysis_1h,
                    analysis_15m=analysis_15m,
                    timestamp=candle.close_time,
                )

                sup, res = self.orchestrator.identify_levels(history)
                setup = self.orchestrator.evaluate_setups(
                    history,
                    analysis_15m.ema_20,
                    analysis_15m.ema_50,
                    support_level=sup,
                    resistance_level=res,
                )

                decision = self.strategy_engine.evaluate(
                    mtf=mtf,
                    data_health=MarketDataHealth.HEALTHY,
                    has_setup=setup is not None,
                    favorable_rr=True,
                    use_gradient_scoring=True,
                )

                if decision.decision_state == DecisionState.BUY:
                    if not self.exchange.has_open_position():
                        stop_ref = (
                            setup.stop_loss_ref
                            if setup
                            else candle.close - (analysis_15m.atr * Decimal("1.5"))
                        )
                        if stop_ref >= candle.close:
                            stop_ref = candle.close - Decimal("10.0")

                        target_notional = self.risk_sizer.calculate_risk_based_notional(
                            entry_price=candle.close,
                            stop_price=stop_ref,
                            allocated_funds=self.config.user_risk_config.allocated_funds,
                            risk_per_trade_pct=Decimal("1.0"),
                            leverage=self.config.user_risk_config.leverage,
                        )
                        acc_state = AccountRiskState(
                            wallet_balance=self.exchange.wallet_balance,
                            available_balance=self.exchange.wallet_balance,
                            total_open_exposure=Decimal("0.0"),
                            realized_daily_loss=Decimal("0.0"),
                            unrealized_pnl=Decimal("0.0"),
                            open_entries_count=0,
                        )
                        risk_check = self.risk_engine.evaluate_entry(
                            decision, candle.close, acc_state, target_notional
                        )
                        if risk_check.is_approved:
                            intent = self.risk_sizer.create_entry_intent(
                                price=candle.close,
                                target_notional=target_notional,
                                client_order_id=f"ENTRY_{candle.open_time}",
                                reason="Strategy Confluence Buy",
                            )
                            trade = self.exchange.process_order(intent, candle)
                            if trade:
                                current_stop_loss = stop_ref
                                highest_price_since_entry = candle.high
                                entry_timestamp = candle.open_time
                                partial_tp_taken = False
                                current_adds = 0
                    elif self.exchange.position is not None and current_adds < (
                        self.config.user_risk_config.max_entries - 1
                    ):
                        dca_notional = min(
                            Decimal("500.00"),
                            self.config.user_risk_config.allocated_funds * Decimal("0.2"),
                        )
                        acc_state = AccountRiskState(
                            wallet_balance=self.exchange.wallet_balance,
                            available_balance=self.exchange.wallet_balance,
                            total_open_exposure=self.exchange.position.size * candle.close,
                            realized_daily_loss=Decimal("0.0"),
                            unrealized_pnl=Decimal("0.0"),
                            open_entries_count=current_adds + 1,
                        )
                        dca_check = self.risk_engine.evaluate_dca(
                            decision,
                            candle.close,
                            acc_state,
                            dca_notional,
                        )
                        if dca_check.is_approved:
                            intent = self.risk_sizer.create_dca_intent(
                                price=candle.close,
                                requested_notional=dca_notional,
                                client_order_id=f"DCA_{candle.open_time}_{current_adds}",
                                reason="Strategy Confluence DCA",
                            )
                            dca_trade = self.exchange.process_order(intent, candle)
                            if dca_trade:
                                current_adds += 1
                                max_adds = max(max_adds, current_adds)

            # 7. Track equity and drawdown
            current_equity = self.exchange.wallet_balance
            if self.exchange.position is not None:
                pnl = (candle.close - self.exchange.position.entry_price) * (
                    self.exchange.position.size
                )
                current_equity += pnl

            equity_peak = max(equity_peak, current_equity)
            if equity_peak > Decimal("0.0"):
                dd = (equity_peak - current_equity) / equity_peak
                max_drawdown_pct = max(max_drawdown_pct, dd)

        # 8. Close any remaining open position at end of backtest
        if self.exchange.has_open_position() and self.exchange.position is not None:
            last_candle = candles[-1]
            close_intent = self.risk_sizer.create_exit_intent(
                price=last_candle.close,
                quantity=self.exchange.position.size,
                client_order_id=f"FINAL_CLOSE_{last_candle.close_time}",
                reason="BACKTEST_END",
                order_type="MARKET",
            )
            self.exchange.process_order(close_intent, last_candle)

        # 9. Compute summary metrics
        trades: list[SimulatedTrade] = list(self.exchange.closed_trades)
        total_trades = len(trades)
        wins = [t for t in trades if t.realized_pnl > Decimal("0.0")]
        losses = [t for t in trades if t.realized_pnl < Decimal("0.0")]

        winning_trades = len(wins)
        losing_trades = len(losses)
        win_rate = (
            Decimal(str(winning_trades)) / Decimal(str(total_trades))
            if total_trades > 0
            else Decimal("0.0")
        )

        gross_profit = sum((t.realized_pnl for t in wins), Decimal("0.0"))
        gross_loss = abs(sum((t.realized_pnl for t in losses), Decimal("0.0")))
        net_profit = gross_profit - gross_loss
        profit_factor = (
            gross_profit / gross_loss
            if gross_loss > Decimal("0.0")
            else (Decimal("100.0") if gross_profit > Decimal("0.0") else Decimal("0.0"))
        )

        avg_win = (
            gross_profit / Decimal(str(winning_trades)) if winning_trades > 0 else Decimal("0.0")
        )
        avg_loss = gross_loss / Decimal(str(losing_trades)) if losing_trades > 0 else Decimal("0.0")
        loss_rate = Decimal("1.0") - win_rate if total_trades > 0 else Decimal("0.0")
        expectancy = round((win_rate * avg_win) - (loss_rate * avg_loss), 2)

        max_consecutive_wins = 0
        max_consecutive_losses = 0
        cur_wins = 0
        cur_losses = 0
        for t in trades:
            if t.realized_pnl > Decimal("0.0"):
                cur_wins += 1
                cur_losses = 0
                max_consecutive_wins = max(max_consecutive_wins, cur_wins)
            elif t.realized_pnl < Decimal("0.0"):
                cur_losses += 1
                cur_wins = 0
                max_consecutive_losses = max(max_consecutive_losses, cur_losses)

        sharpe = Decimal("0.0")
        sortino = Decimal("0.0")
        if total_trades >= 2:
            pnls = [t.realized_pnl for t in trades]
            mean_pnl = net_profit / Decimal(str(total_trades))
            variance = sum((p - mean_pnl) ** 2 for p in pnls) / Decimal(str(total_trades))
            if variance > Decimal("0.0"):
                std_dev = _decimal_sqrt(variance)
                if std_dev > Decimal("0.0"):
                    sharpe = round(mean_pnl / std_dev, 2)

                downside_variance = sum(
                    min(Decimal("0.0"), p - mean_pnl) ** 2 for p in pnls
                ) / Decimal(str(total_trades))
                if downside_variance > Decimal("0.0"):
                    downside_dev = _decimal_sqrt(downside_variance)
                    if downside_dev > Decimal("0.0"):
                        sortino = round(mean_pnl / downside_dev, 2)

        # Calmar ratio
        calmar = Decimal("0.0")
        if max_drawdown_pct > Decimal("0.0") and self.config.initial_balance > Decimal("0.0"):
            calmar = round(net_profit / (self.config.initial_balance * max_drawdown_pct), 2)

        # Target hit rates ($5, $10, $20, $30, $50 moves in price)
        target_hit_rates: dict[str, Decimal] = {}
        for target_dollars in [5, 10, 20, 30, 50]:
            target_dec = Decimal(str(target_dollars))
            hits = sum(
                1
                for t in trades
                if t.size > Decimal("0") and (t.max_favorable_excursion / t.size) >= target_dec
            )
            target_hit_rates[f"${target_dollars}"] = (
                round(Decimal(str(hits)) / Decimal(str(total_trades)), 2)
                if total_trades > 0
                else Decimal("0.0")
            )

        # Average holding time
        holding_times = [(t.exit_time - t.entry_time) for t in trades if t.exit_time is not None]
        avg_holding_time_ms = sum(holding_times) // len(holding_times) if holding_times else 0

        return BacktestResult(
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            net_profit=net_profit,
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            profit_factor=profit_factor,
            max_drawdown_pct=round(max_drawdown_pct, 4),
            total_fees=self.exchange.total_fees_paid,
            total_funding=self.exchange.total_funding_paid,
            liquidations_count=self.exchange.liquidations_count,
            expectancy=expectancy,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            calmar_ratio=calmar,
            consecutive_wins=max_consecutive_wins,
            consecutive_losses=max_consecutive_losses,
            max_exposure=max_exposure,
            max_adds=max_adds,
            avg_holding_time_ms=avg_holding_time_ms,
            target_hit_rates=target_hit_rates,
            trades=trades,
        )
