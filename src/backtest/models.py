"""Backtesting domain models, configuration, and comprehensive performance summaries."""

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from src.config.settings import UserRiskConfig


class IntrabarAmbiguityPolicy(StrEnum):
    """Explicit policy for resolving simultaneous Stop and TP hits within the same OHLC bar."""

    CONSERVATIVE_ADVERSE_FIRST = "CONSERVATIVE_ADVERSE_FIRST"  # Default: Stop triggers before TP
    FAVORABLE_FIRST = "FAVORABLE_FIRST"  # Aggressive: TP triggers before Stop
    OPTIMISTIC_FAVORABLE_FIRST = "FAVORABLE_FIRST"  # Alias for FAVORABLE_FIRST
    OPEN_PROXIMITY = "OPEN_PROXIMITY"  # Whichever target is closer to bar Open triggers first


class LimitFillModel(StrEnum):
    """Model for limit order execution in backtesting."""

    CROSS = "CROSS"  # Price must strictly penetrate past order price
    TOUCH = "TOUCH"  # Touching order price is sufficient for fill
    PASSIVE_POST_ONLY = "PASSIVE_POST_ONLY"  # Rejects if crosses spread, earns maker fee


class LiquidationModelPolicy(StrEnum):
    """Policy for liquidation handling during backtesting."""

    UNAVAILABLE = "UNAVAILABLE"  # Authoritative inputs missing; liquidation safety unverified
    EXPLICIT_MODEL = "EXPLICIT_MODEL"  # Evaluated using defined test/exchange margin model


class BacktestExecutionPolicy(BaseModel):
    """Execution realism configuration for historical simulation."""

    model_config = ConfigDict(frozen=True)

    intrabar_ambiguity: IntrabarAmbiguityPolicy = Field(
        default=IntrabarAmbiguityPolicy.CONSERVATIVE_ADVERSE_FIRST
    )
    limit_fill_model: LimitFillModel = Field(default=LimitFillModel.TOUCH)
    maker_fee: Decimal = Field(default=Decimal("0.0002"), ge=Decimal("0"))
    taker_fee: Decimal = Field(default=Decimal("0.0005"), ge=Decimal("0"))
    slippage_pct: Decimal = Field(default=Decimal("0.0001"), ge=Decimal("0"))
    funding_rate_8h: Decimal = Field(default=Decimal("0.0001"), ge=Decimal("0"))
    liquidation_policy: LiquidationModelPolicy = Field(
        default=LiquidationModelPolicy.EXPLICIT_MODEL
    )


class BacktestConfig(BaseModel):
    """Configuration for historical simulation environment."""

    model_config = ConfigDict(frozen=True)

    initial_balance: Decimal = Field(default=Decimal("10000.00"), gt=Decimal("0"))
    maker_fee: Decimal = Field(default=Decimal("0.0002"), ge=Decimal("0"))
    taker_fee: Decimal = Field(default=Decimal("0.0005"), ge=Decimal("0"))
    slippage_pct: Decimal = Field(default=Decimal("0.0001"), ge=Decimal("0"))
    user_risk_config: UserRiskConfig
    news_event_timestamps: list[int] = Field(default_factory=list)
    execution_policy: BacktestExecutionPolicy = Field(default_factory=BacktestExecutionPolicy)


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


class PerTradeDiagnostic(BaseModel):
    """Fine-grained trade diagnostic record for auditable execution telemetry."""

    model_config = ConfigDict(frozen=True)

    trade_id: str
    entry_time: int
    exit_time: int
    holding_duration_ms: int
    entry_score: Decimal
    regime: str
    entry_family: str
    entry_price: Decimal
    initial_stop: Decimal
    initial_r: Decimal
    exit_price: Decimal
    exit_reason: str
    realized_r: Decimal
    mfe: Decimal
    mae: Decimal
    mfe_capture_pct: Decimal
    gross_pnl: Decimal
    net_pnl: Decimal
    fees_paid: Decimal
    funding_paid: Decimal
    dca_count: int
    partial_tp_taken: bool


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

    # Expanded statistical and execution metrics
    expectancy_per_trade: Decimal = Decimal("0.0")
    avg_winner: Decimal = Decimal("0.0")
    avg_loser: Decimal = Decimal("0.0")
    median_winner: Decimal = Decimal("0.0")
    median_loser: Decimal = Decimal("0.0")
    mae_avg: Decimal = Decimal("0.0")
    mfe_avg: Decimal = Decimal("0.0")
    mfe_capture_pct: Decimal = Decimal("0.0")
    r_multiple_reached_avg: Decimal = Decimal("0.0")
    r_multiple_realized_avg: Decimal = Decimal("0.0")
    fee_drag_pct: Decimal = Decimal("0.0")
    funding_drag_pct: Decimal = Decimal("0.0")
    fees_per_trade: Decimal = Decimal("0.0")

    # Granular performance breakdowns
    setup_family_performance: dict[str, dict[str, Decimal]] = Field(default_factory=dict)
    regime_performance: dict[str, dict[str, Decimal]] = Field(default_factory=dict)
    score_bucket_performance: dict[str, dict[str, Decimal]] = Field(default_factory=dict)
    diagnostics: list[PerTradeDiagnostic] = Field(default_factory=list)
