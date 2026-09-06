"""Backtesting domain models, configuration, and performance summaries."""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from src.config.settings import UserRiskConfig


class BacktestConfig(BaseModel):
    """Configuration for historical simulation environment."""

    model_config = ConfigDict(frozen=True)

    initial_balance: Decimal = Field(default=Decimal("10000.00"), gt=Decimal("0"))
    maker_fee: Decimal = Field(default=Decimal("0.0002"), ge=Decimal("0"))
    taker_fee: Decimal = Field(default=Decimal("0.0005"), ge=Decimal("0"))
    slippage_pct: Decimal = Field(default=Decimal("0.0001"), ge=Decimal("0"))
    user_risk_config: UserRiskConfig
    news_event_timestamps: list[int] = Field(default_factory=list)


class SimulatedTrade(BaseModel):
    """Record of a closed or open simulated trade."""

    model_config = ConfigDict(frozen=True)

    trade_id: str
    entry_time: int
    exit_time: int | None = None
    entry_price: Decimal
    exit_price: Decimal | None = None
    size: Decimal
    notional: Decimal
    realized_pnl: Decimal = Decimal("0.0")
    fees_paid: Decimal = Decimal("0.0")
    funding_paid: Decimal = Decimal("0.0")
    is_dca: bool = False
    exit_reason: str | None = None
    max_favorable_excursion: Decimal = Decimal("0.0")
    max_adverse_excursion: Decimal = Decimal("0.0")


class BacktestResult(BaseModel):
    """Comprehensive performance statistics resulting from a backtest run."""

    model_config = ConfigDict(frozen=True)

    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: Decimal = Decimal("0.0")
    net_profit: Decimal = Decimal("0.0")
    gross_profit: Decimal = Decimal("0.0")
    gross_loss: Decimal = Decimal("0.0")
    profit_factor: Decimal = Decimal("0.0")
    max_drawdown_pct: Decimal = Decimal("0.0")
    total_fees: Decimal = Decimal("0.0")
    total_funding: Decimal = Decimal("0.0")
    liquidations_count: int = 0
    expectancy: Decimal = Decimal("0.0")
    sharpe_ratio: Decimal = Decimal("0.0")
    sortino_ratio: Decimal = Decimal("0.0")
    calmar_ratio: Decimal = Decimal("0.0")
    consecutive_wins: int = 0
    consecutive_losses: int = 0
    max_exposure: Decimal = Decimal("0.0")
    max_adds: int = 0
    avg_holding_time_ms: int = 0
    target_hit_rates: dict[str, Decimal] = Field(default_factory=dict)
    trades: list[SimulatedTrade] = Field(default_factory=list)
