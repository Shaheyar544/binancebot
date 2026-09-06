"""Tests for domain models, enums, immutability, and safety invariants."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.domain.enums import (
    DecisionState,
    MarketRegime,
    NewsFactLabel,
    OrderSide,
    PositionSide,
    Timeframe,
)
from src.domain.models import Candle, OrderIntent


def test_required_decision_states_exist() -> None:
    """Ensure all required decision states are defined in DecisionState enum."""
    expected_states = {
        "WAIT",
        "BUY",
        "ADD",
        "PARTIAL_TP",
        "EXIT",
        "BLOCKED",
        "NEWS_LOCK",
        "POST_NEWS_REASSESSMENT",
        "EMERGENCY_STOP",
        "RECONCILING",
        "DATA_UNSAFE",
    }
    actual_states = {s.value for s in DecisionState}
    assert expected_states.issubset(actual_states)


def test_required_market_regimes_exist() -> None:
    """Ensure all required regimes are defined."""
    expected_regimes = {
        "STRONG_BULL",
        "BULL",
        "BULLISH_RANGE",
        "NEUTRAL",
        "BEARISH_RANGE",
        "BEAR",
        "STRONG_BEAR",
        "HIGH_VOLATILITY",
        "EVENT_RISK",
    }
    actual_regimes = {r.value for r in MarketRegime}
    assert expected_regimes.issubset(actual_regimes)


def test_long_only_position_side() -> None:
    """The bot is strictly long-only; PositionSide must only permit LONG."""
    assert PositionSide.LONG == "LONG"
    assert len(list(PositionSide)) == 1


def test_dca_cap_invariant() -> None:
    """Every individual DCA order must be <= $500 notional."""
    # Non-DCA initial order can be > $500
    initial_order = OrderIntent(
        symbol="XAUUSDT",
        side=OrderSide.BUY,
        quantity=Decimal("0.5"),
        price=Decimal("2700.00"),
        notional=Decimal("1350.00"),
        is_dca=False,
        client_order_id="xau_init_1",
        reason="Initial high-conviction breakout",
    )
    assert initial_order.notional == Decimal("1350.00")

    # DCA order <= $500 passes
    valid_dca = OrderIntent(
        symbol="XAUUSDT",
        side=OrderSide.BUY,
        quantity=Decimal("0.18"),
        price=Decimal("2700.00"),
        notional=Decimal("486.00"),
        is_dca=True,
        client_order_id="xau_dca_1",
        reason="Pullback reclaim",
    )
    assert valid_dca.notional == Decimal("486.00")

    # DCA exactly $500 passes
    exact_dca = OrderIntent(
        symbol="XAUUSDT",
        side=OrderSide.BUY,
        quantity=Decimal("0.2"),
        price=Decimal("2500.00"),
        notional=Decimal("500.00"),
        is_dca=True,
        client_order_id="xau_dca_exact",
        reason="Pullback reclaim",
    )
    assert exact_dca.notional == Decimal("500.00")

    # DCA > $500 must fail with ValidationError
    with pytest.raises(ValidationError, match="DCA order notional cannot exceed \\$500"):
        OrderIntent(
            symbol="XAUUSDT",
            side=OrderSide.BUY,
            quantity=Decimal("0.25"),
            price=Decimal("2700.00"),
            notional=Decimal("675.00"),
            is_dca=True,
            client_order_id="xau_dca_invalid",
            reason="Illegal oversized DCA",
        )


def test_domain_models_are_immutable() -> None:
    """Domain models must be frozen and cannot be modified after creation."""
    order = OrderIntent(
        symbol="XAUUSDT",
        side=OrderSide.BUY,
        quantity=Decimal("0.1"),
        price=Decimal("2700.00"),
        notional=Decimal("270.00"),
        is_dca=False,
        client_order_id="xau_immut_1",
        reason="Test immutability",
    )
    with pytest.raises(ValidationError):
        setattr(order, "notional", Decimal("300.00"))


def test_candle_completed_invariant() -> None:
    """Incomplete candles must be rejected when completed candle analysis is performed."""
    incomplete_candle = Candle(
        symbol="XAUUSDT",
        timeframe=Timeframe.M15,
        open_time=1700000000000,
        open=Decimal("2700.0"),
        high=Decimal("2710.0"),
        low=Decimal("2695.0"),
        close=Decimal("2705.0"),
        volume=Decimal("100.0"),
        close_time=1700000900000,
        is_closed=False,
    )
    with pytest.raises(ValueError, match="Incomplete candle cannot be used"):
        incomplete_candle.assert_completed()

    completed_candle = Candle(
        symbol="XAUUSDT",
        timeframe=Timeframe.M15,
        open_time=1700000000000,
        open=Decimal("2700.0"),
        high=Decimal("2710.0"),
        low=Decimal("2695.0"),
        close=Decimal("2705.0"),
        volume=Decimal("100.0"),
        close_time=1700000900000,
        is_closed=True,
    )
    # Should not raise
    completed_candle.assert_completed()


def test_news_fact_labels() -> None:
    """AI/news must support required fact labels."""
    assert NewsFactLabel.FACT == "FACT"
    assert NewsFactLabel.EXPECTATION == "EXPECTATION"
    assert NewsFactLabel.ANALYSIS == "ANALYSIS"
    assert NewsFactLabel.AI_INTERPRETATION == "AI_INTERPRETATION"
