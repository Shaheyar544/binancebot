"""Adaptive long-only strategy evaluation engine."""

import uuid
from decimal import Decimal

from src.analysis.models import MultiTimeframeAnalysis
from src.domain.enums import DecisionState, MarketRegime
from src.domain.models import DecisionSnapshot
from src.market_data.enums import MarketDataHealth
from src.strategy.scoring import StrategyScorer


class StrategyEngine:
    """Evaluates multi-timeframe analysis and produces candidate trade decisions."""

    def __init__(self, min_entry_score: int | Decimal = 85) -> None:
        self.min_entry_score = Decimal(str(min_entry_score))
        self.scorer = StrategyScorer()

    def evaluate(
        self,
        mtf: MultiTimeframeAnalysis,
        data_health: MarketDataHealth,
        has_setup: bool,
        favorable_rr: bool,
        use_gradient_scoring: bool = False,
        reward_ratio: Decimal | None = None,
    ) -> DecisionSnapshot:
        """Evaluate market conditions against rules and generate a decision snapshot."""
        # Safety gate 1: Unsafe market data
        if data_health != MarketDataHealth.HEALTHY:
            return DecisionSnapshot(
                decision_id=str(uuid.uuid4()),
                symbol=mtf.symbol,
                decision_state=DecisionState.DATA_UNSAFE,
                regime=mtf.regime,
                reason=f"Market data health is unsafe ({data_health.value})",
                timestamp=mtf.timestamp,
            )

        # Safety gate 2: Higher timeframe structure must not be bearish
        if not mtf.analysis_1d.is_bullish or not mtf.analysis_4h.is_bullish:
            return DecisionSnapshot(
                decision_id=str(uuid.uuid4()),
                symbol=mtf.symbol,
                decision_state=DecisionState.BLOCKED,
                regime=mtf.regime,
                reason="Higher-timeframe structure is bearish; long entries prohibited",
                timestamp=mtf.timestamp,
            )

        # Safety gate 3: Regime-aware blocks (BEAR, STRONG_BEAR, BEARISH_RANGE, EVENT_RISK)
        # BEARISH_RANGE blocked: PF 0.02, 12.77% WR in Phase 4A diagnostics — toxic for longs
        if mtf.regime in {
            MarketRegime.BEAR,
            MarketRegime.STRONG_BEAR,
            MarketRegime.BEARISH_RANGE,
        }:
            return DecisionSnapshot(
                decision_id=str(uuid.uuid4()),
                symbol=mtf.symbol,
                decision_state=DecisionState.BLOCKED,
                regime=mtf.regime,
                reason=f"Regime {mtf.regime.value} is hostile to long entries; blocked",
                timestamp=mtf.timestamp,
            )

        if mtf.regime == MarketRegime.EVENT_RISK:
            return DecisionSnapshot(
                decision_id=str(uuid.uuid4()),
                symbol=mtf.symbol,
                decision_state=DecisionState.NEWS_LOCK,
                regime=mtf.regime,
                reason="Event risk is active; news lock enforced",
                timestamp=mtf.timestamp,
            )

        # Calculate effective entry threshold based on regime
        # BULLISH_RANGE elevated: PF 0.23, 18.52% WR — require stronger confluence
        effective_threshold = self.min_entry_score
        if mtf.regime in {
            MarketRegime.NEUTRAL,
            MarketRegime.HIGH_VOLATILITY,
            MarketRegime.BULLISH_RANGE,
        }:
            effective_threshold = max(self.min_entry_score, Decimal("90.0"))

        # Calculate multi-timeframe alignment score
        if use_gradient_scoring:
            breakdown = self.scorer.calculate_gradient(
                htf_1d_bullish=mtf.analysis_1d.is_bullish,
                htf_4h_bullish=mtf.analysis_4h.is_bullish,
                htf_1h_bullish=mtf.analysis_1h.is_bullish,
                setup_15m_bullish=has_setup,
                close_15m=mtf.analysis_15m.current_close,
                ema_10=mtf.analysis_15m.ema_10,
                ema_20=mtf.analysis_15m.ema_20,
                ema_50=mtf.analysis_15m.ema_50,
                ema_200=mtf.analysis_15m.ema_200,
                rsi_1h=mtf.analysis_1h.rsi,
                volume_ratio_15m=mtf.analysis_15m.volume_ratio,
                favorable_rr=favorable_rr,
                reward_ratio=reward_ratio,
            )
        else:
            breakdown = self.scorer.calculate(
                htf_1d_bullish=mtf.analysis_1d.is_bullish,
                htf_4h_bullish=mtf.analysis_4h.is_bullish,
                htf_1h_bullish=mtf.analysis_1h.is_bullish,
                setup_15m_bullish=has_setup,
                ema_aligned=(
                    mtf.analysis_15m.current_close > mtf.analysis_15m.ema_10
                    and mtf.analysis_15m.ema_10 > mtf.analysis_15m.ema_20
                    and mtf.analysis_15m.ema_20 > mtf.analysis_15m.ema_50
                ),
                momentum_aligned=mtf.analysis_1h.rsi > Decimal("50.0"),
                volume_confirmed=mtf.analysis_15m.volume_ratio >= Decimal("1.2"),
                favorable_rr=favorable_rr,
            )

        total_score = breakdown.total_score

        if breakdown.is_actionable(effective_threshold) and has_setup:
            return DecisionSnapshot(
                decision_id=str(uuid.uuid4()),
                symbol=mtf.symbol,
                decision_state=DecisionState.BUY,
                regime=mtf.regime,
                reason=f"High conviction bullish setup aligned (score={total_score})",
                indicators={
                    "score": total_score,
                    "score_breakdown": breakdown.model_dump(),
                },
                timestamp=mtf.timestamp,
            )

        return DecisionSnapshot(
            decision_id=str(uuid.uuid4()),
            symbol=mtf.symbol,
            decision_state=DecisionState.WAIT,
            regime=mtf.regime,
            reason=f"Score below entry threshold ({total_score} < {effective_threshold})",
            indicators={
                "score": total_score,
                "score_breakdown": breakdown.model_dump(),
            },
            timestamp=mtf.timestamp,
        )

    def evaluate_dca(
        self,
        mtf: MultiTimeframeAnalysis,
        current_position_r: Decimal,
        data_health: MarketDataHealth,
        has_setup: bool,
        favorable_rr: bool = False,
    ) -> DecisionSnapshot:
        """High-conviction DCA qualification requiring multi-timeframe confirmation.

        Requirements:
        - Market data must be HEALTHY
        - 1D, 4H, and 1H must all be bullish (strict trend alignment)
        - Regime: STRONG_BULL or BULL only (no ranging / neutral)
        - Position drawdown must not exceed -0.5R
        - 15M: must have a fresh tactical setup
        - Score threshold: >= 85.0 (identical to primary entry)
        """
        if data_health != MarketDataHealth.HEALTHY:
            return DecisionSnapshot(
                decision_id=str(uuid.uuid4()),
                symbol=mtf.symbol,
                decision_state=DecisionState.DATA_UNSAFE,
                regime=mtf.regime,
                reason=f"Market data health is unsafe ({data_health.value})",
                timestamp=mtf.timestamp,
            )

        if (
            not mtf.analysis_1d.is_bullish
            or not mtf.analysis_4h.is_bullish
            or not mtf.analysis_1h.is_bullish
        ):
            return DecisionSnapshot(
                decision_id=str(uuid.uuid4()),
                symbol=mtf.symbol,
                decision_state=DecisionState.BLOCKED,
                regime=mtf.regime,
                reason="Higher-timeframe structure (1D/4H/1H) is not bullish; DCA prohibited",
                timestamp=mtf.timestamp,
            )

        if mtf.regime not in {MarketRegime.STRONG_BULL, MarketRegime.BULL}:
            return DecisionSnapshot(
                decision_id=str(uuid.uuid4()),
                symbol=mtf.symbol,
                decision_state=DecisionState.BLOCKED,
                regime=mtf.regime,
                reason=f"Regime {mtf.regime.value} does not qualify for DCA",
                timestamp=mtf.timestamp,
            )

        if current_position_r < Decimal("-0.5"):
            return DecisionSnapshot(
                decision_id=str(uuid.uuid4()),
                symbol=mtf.symbol,
                decision_state=DecisionState.BLOCKED,
                regime=mtf.regime,
                reason=f"Position drawdown too deep for DCA ({current_position_r:.2f}R < -0.5R)",
                timestamp=mtf.timestamp,
            )

        if not has_setup:
            return DecisionSnapshot(
                decision_id=str(uuid.uuid4()),
                symbol=mtf.symbol,
                decision_state=DecisionState.WAIT,
                regime=mtf.regime,
                reason="No fresh tactical setup for DCA",
                timestamp=mtf.timestamp,
            )

        breakdown = self.scorer.calculate_gradient(
            htf_1d_bullish=mtf.analysis_1d.is_bullish,
            htf_4h_bullish=mtf.analysis_4h.is_bullish,
            htf_1h_bullish=mtf.analysis_1h.is_bullish,
            setup_15m_bullish=has_setup,
            close_15m=mtf.analysis_15m.current_close,
            ema_10=mtf.analysis_15m.ema_10,
            ema_20=mtf.analysis_15m.ema_20,
            ema_50=mtf.analysis_15m.ema_50,
            ema_200=mtf.analysis_15m.ema_200,
            rsi_1h=mtf.analysis_1h.rsi,
            volume_ratio_15m=mtf.analysis_15m.volume_ratio,
            favorable_rr=favorable_rr,
        )

        total_score = breakdown.total_score
        dca_threshold = max(self.min_entry_score, Decimal("85.0"))

        if total_score >= dca_threshold:
            return DecisionSnapshot(
                decision_id=str(uuid.uuid4()),
                symbol=mtf.symbol,
                decision_state=DecisionState.ADD,
                regime=mtf.regime,
                reason=f"DCA qualification approved (score={total_score})",
                indicators={"score": total_score, "score_breakdown": breakdown.model_dump()},
                timestamp=mtf.timestamp,
            )

        return DecisionSnapshot(
            decision_id=str(uuid.uuid4()),
            symbol=mtf.symbol,
            decision_state=DecisionState.WAIT,
            regime=mtf.regime,
            reason=f"DCA score below threshold ({total_score} < {dca_threshold})",
            indicators={"score": total_score, "score_breakdown": breakdown.model_dump()},
            timestamp=mtf.timestamp,
        )


class ExitDecision:
    """Immutable record of an exit evaluation decision."""

    def __init__(
        self,
        should_exit: bool,
        exit_state: DecisionState,
        reason: str,
        trigger_price: Decimal,
        current_price: Decimal,
        portion_pct: Decimal = Decimal("100.0"),
        trailing_stop_price: Decimal | None = None,
        r_multiple: Decimal | None = None,
    ) -> None:
        self.should_exit = should_exit
        self.exit_state = exit_state
        self.reason = reason
        self.trigger_price = trigger_price
        self.current_price = current_price
        self.portion_pct = portion_pct
        self.trailing_stop_price = trailing_stop_price
        self.r_multiple = r_multiple

    def __repr__(self) -> str:
        return (
            f"ExitDecision(should_exit={self.should_exit}, state={self.exit_state.value}, "
            f"portion={self.portion_pct}%, reason='{self.reason}')"
        )


class ExitManager:
    """Evaluates open positions for protective stops, targets, and invalidation."""

    def __init__(
        self,
        partial_tp_ratio: Decimal = Decimal("1.5"),
        partial_tp_pct: Decimal = Decimal("50.0"),
        final_tp_ratio: Decimal = Decimal("3.0"),
        trailing_atr_multiplier: Decimal = Decimal("2.0"),
        max_holding_hours: int | None = None,
        enable_breakeven: bool = False,
        breakeven_r_multiple: Decimal = Decimal("1.0"),
        breakeven_buffer: Decimal = Decimal("0.50"),
        enable_partial_tp: bool = True,
    ) -> None:
        self.partial_tp_ratio = partial_tp_ratio
        self.partial_tp_pct = partial_tp_pct
        self.final_tp_ratio = final_tp_ratio
        self.trailing_atr_multiplier = trailing_atr_multiplier
        self.max_holding_hours = max_holding_hours
        self.enable_breakeven = enable_breakeven
        self.breakeven_r_multiple = breakeven_r_multiple
        self.breakeven_buffer = breakeven_buffer
        self.enable_partial_tp = enable_partial_tp

    def evaluate_position(
        self,
        current_price: Decimal,
        entry_price: Decimal,
        stop_loss_ref: Decimal,
        atr: Decimal,
        highest_price_since_entry: Decimal,
        entry_timestamp: int,
        current_timestamp: int,
        is_structure_broken: bool = False,
        partial_tp_already_taken: bool = False,
    ) -> ExitDecision:
        """Evaluate open position against safety stops, targets, and invalidation."""
        # 1. Structural Stop-Loss (strictly fail-closed protective exit)
        if current_price <= stop_loss_ref:
            return ExitDecision(
                should_exit=True,
                exit_state=DecisionState.EXIT,
                reason=f"Stop loss reference breached ({current_price:.2f} <= {stop_loss_ref:.2f})",
                trigger_price=stop_loss_ref,
                current_price=current_price,
                portion_pct=Decimal("100.0"),
            )

        # 2. Structural Invalidation (e.g. 4H or 1H structure break)
        if is_structure_broken:
            return ExitDecision(
                should_exit=True,
                exit_state=DecisionState.EXIT,
                reason="Market structure invalidated on intermediate timeframe",
                trigger_price=current_price,
                current_price=current_price,
                portion_pct=Decimal("100.0"),
            )

        # 3. Trailing Stop
        risk_distance = entry_price - stop_loss_ref
        if risk_distance > Decimal("0"):
            trailing_stop = highest_price_since_entry - (atr * self.trailing_atr_multiplier)
            # Only trail above entry price (protecting gains)
            if trailing_stop > entry_price and current_price <= trailing_stop:
                r_mult = (current_price - entry_price) / risk_distance
                return ExitDecision(
                    should_exit=True,
                    exit_state=DecisionState.EXIT,
                    reason=f"Trailing stop breached ({current_price:.2f} <= {trailing_stop:.2f})",
                    trigger_price=trailing_stop,
                    current_price=current_price,
                    portion_pct=Decimal("100.0"),
                    trailing_stop_price=trailing_stop,
                    r_multiple=round(r_mult, 2),
                )

        # 4. Partial Take Profit (TP1)
        if self.enable_partial_tp and not partial_tp_already_taken and risk_distance > Decimal("0"):
            target_price = entry_price + (risk_distance * self.partial_tp_ratio)
            if current_price >= target_price:
                r_mult = (current_price - entry_price) / risk_distance
                return ExitDecision(
                    should_exit=True,
                    exit_state=DecisionState.PARTIAL_TP,
                    reason=(
                        f"Partial TP reached {self.partial_tp_ratio}R "
                        f"({current_price:.2f} >= {target_price:.2f})"
                    ),
                    trigger_price=target_price,
                    current_price=current_price,
                    portion_pct=self.partial_tp_pct,
                    r_multiple=round(r_mult, 2),
                )

        # 4b. Final Take Profit (TP2) — runner target after partial TP taken
        if partial_tp_already_taken and risk_distance > Decimal("0"):
            final_target = entry_price + (risk_distance * self.final_tp_ratio)
            if current_price >= final_target:
                r_mult = (current_price - entry_price) / risk_distance
                return ExitDecision(
                    should_exit=True,
                    exit_state=DecisionState.EXIT,
                    reason=(
                        f"Final TP reached {self.final_tp_ratio}R "
                        f"({current_price:.2f} >= {final_target:.2f})"
                    ),
                    trigger_price=final_target,
                    current_price=current_price,
                    portion_pct=Decimal("100.0"),
                    r_multiple=round(r_mult, 2),
                )

        # 5. Time-based Expiration (if configured)
        if self.max_holding_hours is not None:
            elapsed_ms = current_timestamp - entry_timestamp
            max_ms = self.max_holding_hours * 3600 * 1000
            if elapsed_ms >= max_ms:
                return ExitDecision(
                    should_exit=True,
                    exit_state=DecisionState.EXIT,
                    reason=f"Maximum holding duration reached ({self.max_holding_hours} hours)",
                    trigger_price=current_price,
                    current_price=current_price,
                    portion_pct=Decimal("100.0"),
                )

        # 6. Position remains healthy
        return ExitDecision(
            should_exit=False,
            exit_state=DecisionState.WAIT,
            reason="Position within safety boundaries; holding",
            trigger_price=stop_loss_ref,
            current_price=current_price,
            portion_pct=Decimal("0.0"),
        )
