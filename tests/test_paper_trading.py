"""Tests for PaperTradingRunner: real-time simulation with zero real orders."""

from decimal import Decimal
from pathlib import Path

import pytest

from src.config.settings import ExecutionGateConfig, UserRiskConfig
from src.exchange.metadata import SymbolFilters
from src.execution.adapter import FakeExchangeAdapter
from src.paper.models import TradingMode
from src.paper.runner import PaperTradingRunner
from src.risk.engine import RiskEngine
from src.storage.db import DatabaseManager
from src.strategy.engine import StrategyEngine


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
def user_risk_config() -> UserRiskConfig:
    return UserRiskConfig(
        allocated_funds=Decimal("1000.00"),
        leverage=Decimal("5.0"),
        max_acceptable_liquidation_price=Decimal("2500.00"),
    )


@pytest.fixture
async def temp_db(tmp_path: Path) -> DatabaseManager:
    db = DatabaseManager(str(tmp_path / "paper.db"))
    await db.initialize()
    return db


@pytest.mark.asyncio
async def test_paper_runner_mode_and_zero_live_orders(
    user_risk_config: UserRiskConfig,
    xau_filters: SymbolFilters,
    temp_db: DatabaseManager,
) -> None:
    """Paper runner operates in PAPER mode with fake adapter and disabled live flags."""
    fake_adapter = FakeExchangeAdapter()
    gates = ExecutionGateConfig(live_trading=False, enable_order_execution=False)
    risk_engine = RiskEngine(
        config=user_risk_config,
        filters=xau_filters,
        estimator=StubLiquidationEstimator(),
    )
    strategy_engine = StrategyEngine(min_entry_score=85)

    runner = PaperTradingRunner(
        mode=TradingMode.PAPER,
        gates=gates,
        strategy_engine=strategy_engine,
        risk_engine=risk_engine,
        adapter=fake_adapter,
        db=temp_db,
    )

    assert runner.mode == TradingMode.PAPER
    assert runner.gates.can_execute_live is False
    assert runner.account.paper_wallet_balance == user_risk_config.allocated_funds
