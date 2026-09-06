"""Tests for OrderManager: live gates, pre-submit checks, and idempotency."""

from decimal import Decimal

import pytest

from src.config.settings import ExecutionGateConfig, UserRiskConfig
from src.domain.enums import OrderSide
from src.domain.models import OrderIntent
from src.exchange.metadata import SymbolFilters
from src.execution.adapter import FakeExchangeAdapter
from src.execution.models import ExecutionStatus, OrderExecutionResult
from src.execution.order_manager import OrderManager
from src.risk.engine import RiskEngine


class StubLiquidationEstimator:
    def estimate_liquidation_price(
        self, entry_price: Decimal, leverage: Decimal, allocated_funds: Decimal
    ) -> Decimal:
        return Decimal("2400.00")


@pytest.fixture
def xau_filters() -> SymbolFilters:
    return SymbolFilters(
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


@pytest.fixture
def base_risk_config() -> UserRiskConfig:
    return UserRiskConfig(
        allocated_funds=Decimal("1000.00"),
        leverage=Decimal("5.0"),
        max_acceptable_liquidation_price=Decimal("2500.00"),
        max_entries=3,
        max_daily_loss=Decimal("200.00"),
        emergency_loss_limit=Decimal("400.00"),
        max_total_exposure=Decimal("5000.00"),
    )


@pytest.fixture
def fake_adapter() -> FakeExchangeAdapter:
    return FakeExchangeAdapter()


def make_order_intent(client_id: str = "XAU_BUY_001") -> OrderIntent:
    return OrderIntent(
        symbol="XAUUSDT",
        side=OrderSide.BUY,
        order_type="LIMIT",
        quantity=Decimal("1.0"),
        price=Decimal("2700.00"),
        notional=Decimal("2700.00"),
        is_dca=False,
        is_opening=True,
        client_order_id=client_id,
        reason="Execution test",
    )


@pytest.mark.asyncio
async def test_live_execution_blocked_by_default(
    base_risk_config: UserRiskConfig,
    xau_filters: SymbolFilters,
    fake_adapter: FakeExchangeAdapter,
) -> None:
    """When gates are default (disabled), dispatching raises RuntimeError."""
    risk_engine = RiskEngine(
        config=base_risk_config,
        filters=xau_filters,
        estimator=StubLiquidationEstimator(),
    )
    # Default gates: live_trading=False, enable_order_execution=False
    order_manager = OrderManager(
        gates=ExecutionGateConfig(),
        risk_engine=risk_engine,
        adapter=fake_adapter,
    )

    intent = make_order_intent()
    with pytest.raises(RuntimeError, match="Live order execution is strictly blocked"):
        await order_manager.dispatch_order(intent)


@pytest.mark.asyncio
async def test_idempotent_order_submission(
    base_risk_config: UserRiskConfig,
    xau_filters: SymbolFilters,
    fake_adapter: FakeExchangeAdapter,
) -> None:
    """Submitting order with same client_order_id twice raises duplicate error."""
    risk_engine = RiskEngine(
        config=base_risk_config,
        filters=xau_filters,
        estimator=StubLiquidationEstimator(),
    )
    # Testing mode: enabled gates for fake adapter
    order_manager = OrderManager(
        gates=ExecutionGateConfig(live_trading=True, enable_order_execution=True),
        risk_engine=risk_engine,
        adapter=fake_adapter,
    )

    intent = make_order_intent("UNIQUE_ORDER_ID_1")
    result = await order_manager.dispatch_order(intent)
    assert result.status == ExecutionStatus.FILLED

    # Second submission with identical client_order_id must be rejected
    with pytest.raises(ValueError, match="Duplicate order intent detected"):
        await order_manager.dispatch_order(intent)


@pytest.mark.asyncio
async def test_orders_blocked_during_reconciliation(
    base_risk_config: UserRiskConfig,
    xau_filters: SymbolFilters,
    fake_adapter: FakeExchangeAdapter,
) -> None:
    """While reconciliation is active, order dispatch is blocked."""
    risk_engine = RiskEngine(
        config=base_risk_config,
        filters=xau_filters,
        estimator=StubLiquidationEstimator(),
    )
    order_manager = OrderManager(
        gates=ExecutionGateConfig(live_trading=True, enable_order_execution=True),
        risk_engine=risk_engine,
        adapter=fake_adapter,
    )

    order_manager.set_reconciling(True)
    intent = make_order_intent("RECON_ORDER_1")

    with pytest.raises(RuntimeError, match="Order submission blocked: state reconciliation active"):
        await order_manager.dispatch_order(intent)


@pytest.mark.asyncio
async def test_dispatch_with_protective_stop_success(
    base_risk_config: UserRiskConfig,
    xau_filters: SymbolFilters,
    fake_adapter: FakeExchangeAdapter,
) -> None:
    """When entry fills, protective stop order is immediately placed."""
    risk_engine = RiskEngine(
        config=base_risk_config,
        filters=xau_filters,
        estimator=StubLiquidationEstimator(),
    )
    order_manager = OrderManager(
        gates=ExecutionGateConfig(live_trading=True, enable_order_execution=True),
        risk_engine=risk_engine,
        adapter=fake_adapter,
    )

    intent = make_order_intent("ENTRY_WITH_STOP_1")
    entry_res, stop_res = await order_manager.dispatch_with_protective_stop(
        entry_intent=intent,
        stop_price=Decimal("2685.00"),
    )

    assert entry_res.status == ExecutionStatus.FILLED
    assert stop_res is not None
    assert stop_res.status == ExecutionStatus.FILLED
    assert "STOP_ENTRY_WITH_STOP_1" in stop_res.client_order_id


@pytest.mark.asyncio
async def test_dispatch_with_protective_stop_failure_emergency(
    base_risk_config: UserRiskConfig,
    xau_filters: SymbolFilters,
) -> None:
    """If entry fills but protective stop fails, system raises emergency protection failure."""

    class FailingStopAdapter(FakeExchangeAdapter):
        async def submit_order(self, intent: OrderIntent) -> OrderExecutionResult:
            if "STOP_" in intent.client_order_id:
                raise RuntimeError("Binance rejected stop order: filter failure")
            return await super().submit_order(intent)

    risk_engine = RiskEngine(
        config=base_risk_config,
        filters=xau_filters,
        estimator=StubLiquidationEstimator(),
    )
    order_manager = OrderManager(
        gates=ExecutionGateConfig(live_trading=True, enable_order_execution=True),
        risk_engine=risk_engine,
        adapter=FailingStopAdapter(),
    )

    intent = make_order_intent("ENTRY_PROT_FAIL")
    with pytest.raises(RuntimeError, match="Emergency protection failure"):
        await order_manager.dispatch_with_protective_stop(
            entry_intent=intent,
            stop_price=Decimal("2685.00"),
        )
