"""Tests for domain models, enums, immutability, and safety invariants."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.domain.enums import (
    DecisionState,
    MarketRegime,
    NewsFactLabel,
    NewsImpact,
    OrderSide,
    PositionSide,
    Timeframe,
)
from src.domain.models import (
    MAX_DCA_NOTIONAL,
    Candle,
    DecisionSnapshot,
    MarketSnapshot,
    OrderIntent,
    PositionSnapshot,
)


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
    assert expected_states == actual_states


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
    assert expected_regimes == actual_regimes


def test_long_only_position_side() -> None:
    """The domain supports LONG only. Short positions are strictly forbidden."""
    assert PositionSide.LONG == "LONG"
    assert len(list(PositionSide)) == 1
    with pytest.raises(ValueError):
        PositionSide("SHORT")


def test_dca_hard_limit_invariant() -> None:
    """Every individual DCA/additional order must be <= $500 notional."""
    assert MAX_DCA_NOTIONAL == Decimal("500")

    # $300 -> PASS
    order_300 = OrderIntent(
        symbol="XAUUSDT",
        side=OrderSide.BUY,
        order_type="LIMIT",
        quantity=Decimal("0.11"),
        price=Decimal("2700.00"),
        notional=Decimal("300.00"),
        is_dca=True,
        is_opening=True,
        client_order_id="dca_300",
        reason="Pullback add",
    )
    assert order_300.notional == Decimal("300.00")

    # $500 -> PASS
    order_500 = OrderIntent(
        symbol="XAUUSDT",
        side=OrderSide.BUY,
        order_type="LIMIT",
        quantity=Decimal("0.2"),
        price=Decimal("2500.00"),
        notional=Decimal("500.00"),
        is_dca=True,
        is_opening=True,
        client_order_id="dca_500",
        reason="Structure add",
    )
    assert order_500.notional == Decimal("500.00")

    # $500.01 -> FAIL
    with pytest.raises(ValidationError, match="DCA order notional cannot exceed \\$500"):
        OrderIntent(
            symbol="XAUUSDT",
            side=OrderSide.BUY,
            order_type="LIMIT",
            quantity=Decimal("0.2"),
            price=Decimal("2500.05"),
            notional=Decimal("500.01"),
            is_dca=True,
            is_opening=True,
            client_order_id="dca_500_01",
            reason="Exceeds cap by 1 cent",
        )

    # $700 -> FAIL
    with pytest.raises(ValidationError, match="DCA order notional cannot exceed \\$500"):
        OrderIntent(
            symbol="XAUUSDT",
            side=OrderSide.BUY,
            order_type="LIMIT",
            quantity=Decimal("0.25"),
            price=Decimal("2800.00"),
            notional=Decimal("700.00"),
            is_dca=True,
            is_opening=True,
            client_order_id="dca_700",
            reason="Exceeds cap",
        )

    # $1,000 -> FAIL
    with pytest.raises(ValidationError, match="DCA order notional cannot exceed \\$500"):
        OrderIntent(
            symbol="XAUUSDT",
            side=OrderSide.BUY,
            order_type="LIMIT",
            quantity=Decimal("0.4"),
            price=Decimal("2500.00"),
            notional=Decimal("1000.00"),
            is_dca=True,
            is_opening=True,
            client_order_id="dca_1000",
            reason="Exceeds cap",
        )


def test_order_opening_and_closing_sides() -> None:
    """Opening orders must be BUY; closing/TP orders must be SELL."""
    # Valid opening BUY
    OrderIntent(
        symbol="XAUUSDT",
        side=OrderSide.BUY,
        order_type="LIMIT",
        quantity=Decimal("0.5"),
        price=Decimal("2700.00"),
        notional=Decimal("1350.00"),
        is_dca=False,
        is_opening=True,
        client_order_id="open_buy_1",
        reason="Initial entry",
    )

    # Invalid opening SELL (Shorting prohibited)
    with pytest.raises(ValidationError, match="Opening orders must use BUY"):
        OrderIntent(
            symbol="XAUUSDT",
            side=OrderSide.SELL,
            order_type="LIMIT",
            quantity=Decimal("0.5"),
            price=Decimal("2700.00"),
            notional=Decimal("1350.00"),
            is_dca=False,
            is_opening=True,
            client_order_id="open_sell_illegal",
            reason="Illegal short attempt",
        )

    # Valid closing SELL
    OrderIntent(
        symbol="XAUUSDT",
        side=OrderSide.SELL,
        order_type="LIMIT",
        quantity=Decimal("0.2"),
        price=Decimal("2750.00"),
        notional=Decimal("550.00"),
        is_dca=False,
        is_opening=False,
        client_order_id="close_sell_1",
        reason="Take profit partial",
    )

    # Invalid closing BUY
    with pytest.raises(ValidationError, match="Closing orders must use SELL"):
        OrderIntent(
            symbol="XAUUSDT",
            side=OrderSide.BUY,
            order_type="LIMIT",
            quantity=Decimal("0.2"),
            price=Decimal("2750.00"),
            notional=Decimal("550.00"),
            is_dca=False,
            is_opening=False,
            client_order_id="close_buy_illegal",
            reason="Invalid close",
        )


def test_candle_validates_ohlc_relationships() -> None:
    """Candle model must reject impossible/invalid OHLC relationships."""
    valid_candle = Candle(
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
    assert valid_candle.high >= valid_candle.low

    # high < low
    with pytest.raises(ValidationError, match="high must be greater than or equal to low"):
        Candle(
            symbol="XAUUSDT",
            timeframe=Timeframe.M15,
            open_time=1700000000000,
            open=Decimal("2700.0"),
            high=Decimal("2690.0"),
            low=Decimal("2710.0"),
            close=Decimal("2700.0"),
            volume=Decimal("100.0"),
            close_time=1700000900000,
            is_closed=True,
        )

    # high < open
    with pytest.raises(ValidationError, match="high cannot be less than open"):
        Candle(
            symbol="XAUUSDT",
            timeframe=Timeframe.M15,
            open_time=1700000000000,
            open=Decimal("2715.0"),
            high=Decimal("2710.0"),
            low=Decimal("2695.0"),
            close=Decimal("2705.0"),
            volume=Decimal("100.0"),
            close_time=1700000900000,
            is_closed=True,
        )

    # low > close
    with pytest.raises(ValidationError, match="low cannot be greater than close"):
        Candle(
            symbol="XAUUSDT",
            timeframe=Timeframe.M15,
            open_time=1700000000000,
            open=Decimal("2705.0"),
            high=Decimal("2710.0"),
            low=Decimal("2702.0"),
            close=Decimal("2698.0"),
            volume=Decimal("100.0"),
            close_time=1700000900000,
            is_closed=True,
        )

    # negative volume
    with pytest.raises(ValidationError):
        Candle(
            symbol="XAUUSDT",
            timeframe=Timeframe.M15,
            open_time=1700000000000,
            open=Decimal("2700.0"),
            high=Decimal("2710.0"),
            low=Decimal("2695.0"),
            close=Decimal("2705.0"),
            volume=Decimal("-1.0"),
            close_time=1700000900000,
            is_closed=True,
        )


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


def test_market_snapshot_immutable() -> None:
    """MarketSnapshot represents canonical market state and is immutable."""
    candle = Candle(
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
    snapshot = MarketSnapshot(
        symbol="XAUUSDT",
        timestamp=1700000900000,
        last_price=Decimal("2705.00"),
        mark_price=Decimal("2704.80"),
        index_price=Decimal("2704.50"),
        funding_rate=Decimal("0.0001"),
        candles={Timeframe.M15: candle},
    )
    with pytest.raises(ValidationError):
        snapshot.last_price = Decimal("2800.00")


def test_position_snapshot_is_long_only() -> None:
    """PositionSnapshot side is strictly LONG and immutable."""
    pos = PositionSnapshot(
        symbol="XAUUSDT",
        side=PositionSide.LONG,
        size=Decimal("1.5"),
        entry_price=Decimal("2680.00"),
        leverage=Decimal("5.0"),
        margin=Decimal("804.00"),
        liquidation_price=Decimal("2150.00"),
    )
    assert pos.side == PositionSide.LONG
    with pytest.raises(ValidationError):
        pos.size = Decimal("2.0")


def test_decision_snapshot_is_immutable() -> None:
    """DecisionSnapshot holds audit state and is immutable."""
    decision = DecisionSnapshot(
        decision_id="dec_01",
        timestamp=1700000000000,
        decision_state=DecisionState.WAIT,
        regime=MarketRegime.BULL,
        reason="Waiting for pullback retest",
    )
    with pytest.raises(ValidationError):
        decision.reason = "Mutated"


def test_news_fact_labels_and_impact() -> None:
    """Enums for news fact labels and impacts."""
    assert NewsFactLabel.FACT == "FACT"
    assert NewsFactLabel.EXPECTATION == "EXPECTATION"
    assert NewsFactLabel.ANALYSIS == "ANALYSIS"
    assert NewsFactLabel.AI_INTERPRETATION == "AI_INTERPRETATION"

    assert NewsImpact.HIGH == "HIGH"
    assert NewsImpact.MEDIUM == "MEDIUM"
    assert NewsImpact.LOW == "LOW"
