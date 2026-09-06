"""Event-driven no-lookahead backtesting engine."""

import statistics
from collections.abc import Sequence
from decimal import Decimal

from src.analysis.indicators import _decimal_sqrt
from src.analysis.models import MultiTimeframeAnalysis, TimeframeAnalyzer
from src.analysis.regime import RegimeClassifier
from src.backtest.exchange import SimulatedExchange
from src.backtest.models import (
    BacktestConfig,
    BacktestResult,
    IntrabarAmbiguityPolicy,
    LiquidationModelPolicy,
    PerTradeDiagnostic,
    SimulatedTrade,
)
from src.domain.enums import DecisionState, Timeframe
from src.domain.models import Candle, OrderIntent
from src.exchange.metadata import SymbolFilters
from src.market_data.enums import MarketDataHealth
from src.risk.engine import RiskEngine
from src.risk.liquidation import (
    ExchangeLiquidationEstimator,
    UnavailableLiquidationEstimator,
)
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
        estimator: ExchangeLiquidationEstimator | None = None,
    ) -> None:
        self.config = config
        self.policy = config.execution_policy
        if estimator is not None:
            liq_estimator = estimator
        elif self.policy.liquidation_policy == LiquidationModelPolicy.UNAVAILABLE:
            liq_estimator = UnavailableLiquidationEstimator(
                reason="Authoritative Binance margin tiers unavailable in backtest"
            )
        else:
            # EXPLICIT_MODEL requested but no explicit estimator provided:
            # strictly fail closed with UnavailableLiquidationEstimator rather than guessing.
            liq_estimator = UnavailableLiquidationEstimator(
                reason="Authoritative Binance margin model not provided for backtest"
            )

        self.liq_estimator = liq_estimator
        self.exchange = SimulatedExchange(config=config, estimator=liq_estimator)
        self.strategy_engine = strategy_engine or StrategyEngine(min_entry_score=80)
        self.exit_manager = exit_manager or ExitManager()
        self.orchestrator = EntryOrchestrator()
        self.regime_classifier = RegimeClassifier()
        self.filters = filters or DEFAULT_XAU_FILTERS

        self.risk_engine = risk_engine or RiskEngine(
            config=config.user_risk_config,
            filters=self.filters,
            estimator=liq_estimator,
        )
        self.risk_sizer = PositionSizer(filters=self.filters)
        self.active_trade_meta: dict[str, dict[str, object]] = {}

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

    def resolve_intrabar_exit(
        self,
        candle: Candle,
        entry_price: Decimal,
        stop_loss: Decimal,
        take_profit: Decimal | None,
        highest_price: Decimal,
        current_atr: Decimal | None,
    ) -> tuple[OrderIntent | None, bool]:
        """Resolve intrabar conflict when stop and take profit are reached in one candle.

        Returns (OrderIntent | None, is_ambiguous).
        """
        hit_stop = candle.low <= stop_loss
        hit_tp = take_profit is not None and candle.high >= take_profit

        hit_trailing = False
        trailing_stop = Decimal("0.0")
        if current_atr is not None and current_atr > Decimal("0"):
            trailing_stop = highest_price - (
                current_atr * self.exit_manager.trailing_atr_multiplier
            )
            hit_trailing = trailing_stop > entry_price and candle.low <= trailing_stop

        if not hit_stop and not hit_trailing and not hit_tp:
            return None, False

        qty = self.exchange.position.size if self.exchange.position else Decimal("0.0")

        # Intrabar Ambiguity Check: candle touches both stop and TP
        if (hit_stop or hit_trailing) and hit_tp:
            if self.policy.intrabar_ambiguity == IntrabarAmbiguityPolicy.OPTIMISTIC_FAVORABLE_FIRST:
                if take_profit is not None:
                    intent = self.risk_sizer.create_exit_intent(
                        price=take_profit,
                        quantity=qty * (self.exit_manager.partial_tp_pct / Decimal("100.0")),
                        client_order_id=f"PARTIAL_TP_{candle.open_time}",
                        reason=(
                            f"Partial TP reached {self.exit_manager.partial_tp_ratio}R "
                            f"({candle.high:.2f} >= {take_profit:.2f}) [Optimistic Intrabar]"
                        ),
                        order_type="LIMIT",
                    )
                    return intent, True
            # Default: CONSERVATIVE_ADVERSE_FIRST triggers the Stop Loss
            fill_p = min(candle.open, stop_loss) if candle.open < stop_loss else stop_loss
            intent = self.risk_sizer.create_exit_intent(
                price=fill_p,
                quantity=qty,
                client_order_id=f"STOP_{candle.open_time}",
                reason=(
                    f"Stop loss breached ({candle.low:.2f} <= {stop_loss:.2f}) "
                    "[Adverse-First Intrabar]"
                ),
                order_type="MARKET",
            )
            return intent, True

        # Unambiguous exit hits
        if hit_stop:
            fill_p = min(candle.open, stop_loss) if candle.open < stop_loss else stop_loss
            intent = self.risk_sizer.create_exit_intent(
                price=fill_p,
                quantity=qty,
                client_order_id=f"STOP_{candle.open_time}",
                reason=f"Stop loss reference breached ({candle.low:.2f} <= {stop_loss:.2f})",
                order_type="MARKET",
            )
            return intent, False

        if hit_trailing:
            fill_p = (
                min(candle.open, trailing_stop) if candle.open < trailing_stop else trailing_stop
            )
            intent = self.risk_sizer.create_exit_intent(
                price=fill_p,
                quantity=qty,
                client_order_id=f"TRAIL_{candle.open_time}",
                reason=f"Trailing stop breached ({candle.low:.2f} <= {trailing_stop:.2f})",
                order_type="MARKET",
            )
            return intent, False

        if hit_tp:
            assert take_profit is not None
            intent = self.risk_sizer.create_exit_intent(
                price=take_profit,
                quantity=qty * (self.exit_manager.partial_tp_pct / Decimal("100.0")),
                client_order_id=f"PARTIAL_TP_{candle.open_time}",
                reason=(
                    f"Partial TP reached {self.exit_manager.partial_tp_ratio}R "
                    f"({candle.high:.2f} >= {take_profit:.2f})"
                ),
                order_type="LIMIT",
            )
            return intent, False

        return None, False

    def run(self, candles: Sequence[Candle]) -> BacktestResult:
        """Run event-driven simulation over chronological candles."""
        if not candles:
            return BacktestResult()

        current_stop_loss: Decimal | None = None
        highest_price_since_entry = Decimal("0.0")
        partial_tp_taken = False
        current_adds = 0
        equity_peak = self.config.initial_balance
        max_drawdown_pct = Decimal("0.0")
        max_exposure = Decimal("0.0")
        max_adds = 0
        active_trade_meta: dict[str, dict[str, object]] = dict(self.active_trade_meta)
        trade_diagnostics: list[PerTradeDiagnostic] = []

        for idx, candle in enumerate(candles):
            if len(candles) >= 5000 and idx % 2500 == 0:
                print(
                    f"  [Backtest] Processed {idx}/{len(candles)} candles "
                    f"({idx * 100 // len(candles)}%)...",
                    flush=True,
                )
            history = self.get_historical_slice(candles, idx)

            recent_history = history[-1000:] if len(history) > 1000 else history

            # Dynamic causal 15M ATR from finalized history (strictly at least 15 bars)
            current_atr: Decimal | None = None
            if len(recent_history) >= 15:
                from src.analysis.indicators import calculate_atr

                atr_val = calculate_atr(recent_history, period=14)
                if atr_val is not None and atr_val > Decimal("0"):
                    current_atr = atr_val

            # 1. Funding check (every 8 hours: at 00:00, 08:00, 16:00 UTC)
            if self.exchange.has_open_position():
                if candle.open_time % 28_800_000 < 900_000:
                    self.exchange.apply_funding(
                        candle.open_time, funding_rate=self.policy.funding_rate_8h
                    )

            # 2. Check liquidation or depleted capital
            if self.exchange.check_liquidation(candle):
                current_stop_loss = None
                partial_tp_taken = False
                current_adds = 0
                continue

            # If wallet balance is completely depleted (<= 0), no further entries are possible
            if self.exchange.wallet_balance <= Decimal("0.0"):
                if not self.exchange.has_open_position():
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

                # 5. Exit evaluation with Causal ATR and Intrabar Ambiguity Resolution
                if current_stop_loss is not None:
                    risk_dist = self.exchange.position.entry_price - current_stop_loss
                    tp_target = (
                        self.exchange.position.entry_price
                        + (risk_dist * self.exit_manager.partial_tp_ratio)
                        if (not partial_tp_taken and risk_dist > Decimal("0"))
                        else None
                    )

                    resolved_intent, _ = self.resolve_intrabar_exit(
                        candle=candle,
                        entry_price=self.exchange.position.entry_price,
                        stop_loss=current_stop_loss,
                        take_profit=tp_target,
                        highest_price=highest_price_since_entry,
                        current_atr=current_atr,
                    )

                    if resolved_intent is not None:
                        if (
                            "PARTIAL_TP" in resolved_intent.client_order_id
                            or "TP" in resolved_intent.client_order_id
                        ):
                            self.exchange.process_order(resolved_intent, candle)
                            partial_tp_taken = True
                        else:
                            # Full position exit
                            self.exchange.process_order(resolved_intent, candle)
                            current_stop_loss = None
                            partial_tp_taken = False
                            current_adds = 0

            # 6. Strategy Evaluation and Entry / DCA
            if not self.is_news_locked(candle.open_time) and len(history) >= 20:
                recent_history = history[-1000:] if len(history) > 1000 else history
                analysis_15m = TimeframeAnalyzer.analyze_timeframe(recent_history, Timeframe.M15)
                candles_1h = resample_candles(recent_history, Timeframe.H1)
                candles_4h = resample_candles(recent_history, Timeframe.H4)
                candles_1d = resample_candles(recent_history, Timeframe.D1)

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

                sup, res = self.orchestrator.identify_levels(recent_history)
                setup = self.orchestrator.evaluate_setups(
                    recent_history,
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
                        if self.exchange.wallet_balance <= Decimal("0.0"):
                            continue

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
                                partial_tp_taken = False
                                current_adds = 0
                                active_trade_meta[trade.trade_id] = {
                                    "entry_score": Decimal("85.0"),
                                    "regime": regime.value,
                                    "entry_family": (
                                        setup.family.value if setup else "TREND_PULLBACK"
                                    ),
                                    "initial_stop": stop_ref,
                                    "initial_r": candle.close - stop_ref,
                                }
                    elif (
                        self.exchange.position is not None
                        and current_adds < (self.config.user_risk_config.max_entries - 1)
                        and self.exchange.wallet_balance > Decimal("0.0")
                    ):
                        dca_notional = min(
                            Decimal("500.00"),
                            self.config.user_risk_config.allocated_funds * Decimal("0.2"),
                        )
                        avail_bal = max(Decimal("0.0"), self.exchange.wallet_balance)
                        acc_state = AccountRiskState(
                            wallet_balance=avail_bal,
                            available_balance=avail_bal,
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

        # Advanced Statistical Metrics
        winners_pnl = [t.realized_pnl for t in trades if t.realized_pnl > Decimal("0.0")]
        losers_pnl = [t.realized_pnl for t in trades if t.realized_pnl < Decimal("0.0")]
        avg_winner = (
            round(sum(winners_pnl) / Decimal(str(len(winners_pnl))), 2)
            if winners_pnl
            else Decimal("0.0")
        )
        avg_loser = (
            round(sum(losers_pnl) / Decimal(str(len(losers_pnl))), 2)
            if losers_pnl
            else Decimal("0.0")
        )
        med_winner = (
            round(Decimal(str(statistics.median(winners_pnl))), 2)
            if winners_pnl
            else Decimal("0.0")
        )
        med_loser = (
            round(Decimal(str(statistics.median(losers_pnl))), 2) if losers_pnl else Decimal("0.0")
        )

        mae_avg = (
            round(
                sum((t.max_adverse_excursion for t in trades), Decimal("0.0"))
                / Decimal(str(total_trades)),
                2,
            )
            if total_trades > 0
            else Decimal("0.0")
        )
        mfe_avg = (
            round(
                sum((t.max_favorable_excursion for t in trades), Decimal("0.0"))
                / Decimal(str(total_trades)),
                2,
            )
            if total_trades > 0
            else Decimal("0.0")
        )
        total_mfe = sum((t.max_favorable_excursion for t in trades), Decimal("0.0"))
        mfe_cap_pct = (
            round((gross_profit / total_mfe) * Decimal("100.0"), 2)
            if total_mfe > Decimal("0.0")
            else Decimal("0.0")
        )

        fee_drag_pct = (
            round((self.exchange.total_fees_paid / gross_profit) * Decimal("100.0"), 2)
            if gross_profit > Decimal("0.0")
            else Decimal("0.0")
        )
        funding_drag_pct = (
            round((self.exchange.total_funding_paid / gross_profit) * Decimal("100.0"), 2)
            if gross_profit > Decimal("0.0")
            else Decimal("0.0")
        )
        fees_per_trade = (
            round(self.exchange.total_fees_paid / Decimal(str(total_trades)), 2)
            if total_trades > 0
            else Decimal("0.0")
        )

        # Build PerTradeDiagnostic records (AGENTS.md Sec 14: No fabricated stops/risk)
        for t in trades:
            meta = active_trade_meta.get(t.trade_id)
            if not meta or "initial_stop" not in meta or "initial_r" not in meta:
                raise ValueError(
                    f"Trade {t.trade_id} missing authoritative initial_stop/initial_r metadata. "
                    "Fallback stops and fabricated risk distances are strictly forbidden."
                )

            init_stop = Decimal(str(meta["initial_stop"]))
            init_r = Decimal(str(meta["initial_r"]))
            if init_r <= Decimal("0.0"):
                raise ValueError(
                    f"Trade {t.trade_id} has non-positive initial_r ({init_r}). "
                    "Risk distance must be strictly positive."
                )

            r_realized = (
                round((t.realized_pnl / (t.size * init_r)), 2)
                if t.size > Decimal("0")
                else Decimal("0.0")
            )
            trade_mfe_r = (
                round((t.max_favorable_excursion / (t.size * init_r)), 2)
                if t.size > Decimal("0")
                else Decimal("0.0")
            )
            mfe_capture = (
                round((t.realized_pnl / t.max_favorable_excursion) * Decimal("100.0"), 1)
                if t.max_favorable_excursion > Decimal("0.0")
                else Decimal("0.0")
            )
            trade_diagnostics.append(
                PerTradeDiagnostic(
                    trade_id=t.trade_id,
                    entry_time=t.entry_time,
                    exit_time=t.exit_time or t.entry_time,
                    holding_duration_ms=(t.exit_time - t.entry_time) if t.exit_time else 0,
                    entry_score=Decimal(str(meta.get("entry_score", Decimal("85.0")))),
                    regime=str(meta.get("regime", "UNKNOWN")),
                    entry_family=str(meta.get("entry_family", "TREND_PULLBACK")),
                    entry_price=t.entry_price,
                    initial_stop=init_stop,
                    initial_r=init_r,
                    exit_price=t.exit_price or t.entry_price,
                    exit_reason=t.exit_reason or "UNKNOWN",
                    realized_r=r_realized,
                    mfe=t.max_favorable_excursion,
                    mae=t.max_adverse_excursion,
                    mfe_r=trade_mfe_r,
                    max_r_reached=trade_mfe_r,
                    mfe_capture_pct=mfe_capture,
                    gross_pnl=t.realized_pnl + t.fees_paid,
                    net_pnl=t.realized_pnl,
                    fees_paid=t.fees_paid,
                    funding_paid=t.funding_paid,
                    dca_count=1 if t.is_dca else 0,
                    partial_tp_taken=False,
                )
            )

        # Compute causal MFE and R analytics across trade diagnostics
        mfe_vals = [d.mfe for d in trade_diagnostics]
        mfe_median = (
            round(Decimal(str(statistics.median(mfe_vals))), 2) if mfe_vals else Decimal("0.0")
        )
        mfe_r_avg = (
            round(
                sum((d.mfe_r for d in trade_diagnostics), Decimal("0.0"))
                / Decimal(str(total_trades)),
                2,
            )
            if total_trades > 0
            else Decimal("0.0")
        )
        max_r_reached = (
            max((d.mfe_r for d in trade_diagnostics), default=Decimal("0.0"))
            if trade_diagnostics
            else Decimal("0.0")
        )
        r_realized_avg = (
            round(
                sum((d.realized_r for d in trade_diagnostics), Decimal("0.0"))
                / Decimal(str(total_trades)),
                2,
            )
            if total_trades > 0
            else Decimal("0.0")
        )
        r_surrendered_avg = (
            round(
                sum(
                    (max(Decimal("0.0"), d.mfe_r - d.realized_r) for d in trade_diagnostics),
                    Decimal("0.0"),
                )
                / Decimal(str(total_trades)),
                2,
            )
            if total_trades > 0
            else Decimal("0.0")
        )

        # MFE realization % for winners: (realized_pnl / mfe) * 100
        winning_diags = [d for d in trade_diagnostics if d.net_pnl > Decimal("0.0")]
        mfe_realization_pct_winners = (
            round(
                sum(
                    (
                        (d.net_pnl / d.mfe) * Decimal("100.0")
                        for d in winning_diags
                        if d.mfe > Decimal("0.0")
                    ),
                    Decimal("0.0"),
                )
                / Decimal(str(len(winning_diags))),
                2,
            )
            if winning_diags
            else Decimal("0.0")
        )

        # Giveback %: average (mfe - net_pnl) / mfe across trades with positive MFE
        pos_mfe_diags = [d for d in trade_diagnostics if d.mfe > Decimal("0.0")]
        giveback_pct = (
            round(
                sum(
                    (
                        max(Decimal("0.0"), (d.mfe - d.net_pnl) / d.mfe) * Decimal("100.0")
                        for d in pos_mfe_diags
                    ),
                    Decimal("0.0"),
                )
                / Decimal(str(len(pos_mfe_diags))),
                2,
            )
            if pos_mfe_diags
            else Decimal("0.0")
        )

        # Target R hit rates: percentage of trades reaching >= 0.5R, 1.0R, 1.5R, 2.0R
        r_target_hit_rates: dict[str, Decimal] = {}
        for r_thresh_str, r_thresh_dec in [
            ("0.5R", Decimal("0.5")),
            ("1.0R", Decimal("1.0")),
            ("1.5R", Decimal("1.5")),
            ("2.0R", Decimal("2.0")),
        ]:
            hits = sum(1 for d in trade_diagnostics if d.mfe_r >= r_thresh_dec)
            r_target_hit_rates[r_thresh_str] = (
                round(Decimal(str(hits)) / Decimal(str(total_trades)), 2)
                if total_trades > 0
                else Decimal("0.0")
            )

        # Percentage of trades with positive MFE that closed as losers
        losers_with_pos_mfe = sum(
            1 for d in trade_diagnostics if d.net_pnl < Decimal("0.0") and d.mfe > Decimal("0.0")
        )
        positive_mfe_closing_loser_pct = (
            round(
                (Decimal(str(losers_with_pos_mfe)) / Decimal(str(total_trades))) * Decimal("100.0"),
                2,
            )
            if total_trades > 0
            else Decimal("0.0")
        )

        # Helper to compute breakdown metrics for diagnostic partitions
        def _compute_partition_metrics(
            partition_diags: list[PerTradeDiagnostic],
        ) -> dict[str, Decimal]:
            p_total = len(partition_diags)
            if p_total == 0:
                return {
                    "total_trades": Decimal("0"),
                    "win_rate": Decimal("0.0"),
                    "net_pnl": Decimal("0.0"),
                    "profit_factor": Decimal("0.0"),
                }
            p_wins = [d for d in partition_diags if d.net_pnl > Decimal("0.0")]
            p_losses = [d for d in partition_diags if d.net_pnl < Decimal("0.0")]
            p_win_rate = round(Decimal(str(len(p_wins))) / Decimal(str(p_total)), 4)
            p_gross_win = sum((d.net_pnl for d in p_wins), Decimal("0.0"))
            p_gross_loss = abs(sum((d.net_pnl for d in p_losses), Decimal("0.0")))
            p_pf = (
                round(p_gross_win / p_gross_loss, 2)
                if p_gross_loss > Decimal("0.0")
                else (Decimal("100.0") if p_gross_win > Decimal("0.0") else Decimal("0.0"))
            )
            return {
                "total_trades": Decimal(str(p_total)),
                "win_rate": p_win_rate,
                "net_pnl": p_gross_win - p_gross_loss,
                "profit_factor": p_pf,
            }

        # Populate Setup Family Performance Breakdown
        setup_family_performance: dict[str, dict[str, Decimal]] = {}
        families = {d.entry_family for d in trade_diagnostics}
        for fam in sorted(families):
            subset = [d for d in trade_diagnostics if d.entry_family == fam]
            setup_family_performance[fam] = _compute_partition_metrics(subset)

        # Populate Regime Performance Breakdown
        regime_performance: dict[str, dict[str, Decimal]] = {}
        regimes = {d.regime for d in trade_diagnostics}
        for reg in sorted(regimes):
            subset = [d for d in trade_diagnostics if d.regime == reg]
            regime_performance[reg] = _compute_partition_metrics(subset)

        # Populate Score Bucket Performance Breakdown
        score_bucket_performance: dict[str, dict[str, Decimal]] = {}
        buckets = [
            ("80-84", Decimal("80.0"), Decimal("85.0")),
            ("85-89", Decimal("85.0"), Decimal("90.0")),
            ("90-100", Decimal("90.0"), Decimal("101.0")),
        ]
        for label, low, high in buckets:
            subset = [d for d in trade_diagnostics if low <= d.entry_score < high]
            if subset:
                score_bucket_performance[label] = _compute_partition_metrics(subset)

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
            liquidation_model_status=(
                "EXPLICIT_MODEL"
                if (
                    self.policy.liquidation_policy == LiquidationModelPolicy.EXPLICIT_MODEL
                    and not isinstance(self.liq_estimator, UnavailableLiquidationEstimator)
                )
                else "UNAVAILABLE"
            ),
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
            expectancy_per_trade=expectancy,
            avg_winner=avg_winner,
            avg_loser=avg_loser,
            median_winner=med_winner,
            median_loser=med_loser,
            mae_avg=mae_avg,
            mfe_avg=mfe_avg,
            mfe_median=mfe_median,
            mfe_r_avg=mfe_r_avg,
            max_r_reached=max_r_reached,
            r_realized_avg=r_realized_avg,
            r_surrendered_avg=r_surrendered_avg,
            mfe_realization_pct_winners=mfe_realization_pct_winners,
            giveback_pct=giveback_pct,
            r_target_hit_rates=r_target_hit_rates,
            positive_mfe_closing_loser_pct=positive_mfe_closing_loser_pct,
            mfe_capture_pct=mfe_cap_pct,
            r_multiple_reached_avg=mfe_r_avg,
            r_multiple_realized_avg=r_realized_avg,
            fee_drag_pct=fee_drag_pct,
            funding_drag_pct=funding_drag_pct,
            fees_per_trade=fees_per_trade,
            setup_family_performance=setup_family_performance,
            regime_performance=regime_performance,
            score_bucket_performance=score_bucket_performance,
            diagnostics=trade_diagnostics,
        )
