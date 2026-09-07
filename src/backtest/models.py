from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

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


class FeeProfile(BaseModel):
    """Explicit versioned exchange fee configuration."""

    model_config = ConfigDict(frozen=True)

    profile_name: str = "BINANCE_STANDARD_ASSUMED"
    maker_fee: Decimal = Field(default=Decimal("0.0002"), ge=Decimal("0"))
    taker_fee: Decimal = Field(default=Decimal("0.0005"), ge=Decimal("0"))
    funding_rate_8h: Decimal = Field(default=Decimal("0.0001"))
    effective_from: int | None = None
    effective_to: int | None = None
    is_assumed: bool = True
    account_tier: str = "VIP0"


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
    funding_rate_8h: Decimal = Field(default=Decimal("0.0001"))
    liquidation_policy: LiquidationModelPolicy = Field(
        default=LiquidationModelPolicy.EXPLICIT_MODEL
    )
    fee_profile: FeeProfile = Field(default_factory=FeeProfile)


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

    @model_validator(mode="before")
    @classmethod
    def sync_execution_policy(cls, data: Any) -> Any:
        """Route top-level fee/slippage kwargs into execution_policy as single source of truth."""
        if isinstance(data, dict):
            pol = data.get("execution_policy")
            pol_dict = (
                pol.model_dump()
                if isinstance(pol, BaseModel)
                else (dict(pol) if isinstance(pol, dict) else {})
            )
            for key in ("maker_fee", "taker_fee", "slippage_pct"):
                if key in data:
                    val = data[key]
                    if key not in pol_dict:
                        pol_dict[key] = val
                elif key in pol_dict:
                    data[key] = pol_dict[key]
            if pol_dict:
                data["execution_policy"] = BacktestExecutionPolicy(**pol_dict)
                for key in ("maker_fee", "taker_fee", "slippage_pct"):
                    if key in pol_dict:
                        data[key] = pol_dict[key]
        return data


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
    maker_fees_paid: Decimal = Decimal("0.0")
    taker_fees_paid: Decimal = Decimal("0.0")
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
    mfe_r: Decimal = Decimal("0.0")
    max_r_reached: Decimal = Decimal("0.0")
    mfe_capture_pct: Decimal
    gross_pnl: Decimal
    net_pnl: Decimal
    fees_paid: Decimal
    maker_fees_paid: Decimal = Decimal("0.0")
    taker_fees_paid: Decimal = Decimal("0.0")
    funding_paid: Decimal
    dca_count: int
    partial_tp_taken: bool
    breakeven_activated: bool = False
    configured_risk: Decimal = Decimal("10.00")
    theoretical_risk: Decimal = Decimal("0.0")
    actual_risk: Decimal = Decimal("0.0")
    actual_risk_pct: Decimal = Decimal("0.0")
    atr_at_entry: Decimal = Decimal("0.0")
    r_over_atr: Decimal = Decimal("0.0")


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
    total_maker_fees: Decimal = Decimal("0.0")
    total_taker_fees: Decimal = Decimal("0.0")
    total_funding: Decimal = Decimal("0.0")
    fee_profile: FeeProfile = Field(default_factory=FeeProfile)
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

    # Liquidation model audit status
    liquidation_model_status: str = "UNAVAILABLE"

    # Expanded statistical and execution metrics
    expectancy_per_trade: Decimal = Decimal("0.0")
    avg_winner: Decimal = Decimal("0.0")
    avg_loser: Decimal = Decimal("0.0")
    median_winner: Decimal = Decimal("0.0")
    median_loser: Decimal = Decimal("0.0")
    mae_avg: Decimal = Decimal("0.0")
    mfe_avg: Decimal = Decimal("0.0")
    mfe_median: Decimal = Decimal("0.0")
    mfe_r_avg: Decimal = Decimal("0.0")
    max_r_reached: Decimal = Decimal("0.0")
    r_realized_avg: Decimal = Decimal("0.0")
    r_surrendered_avg: Decimal = Decimal("0.0")
    mfe_realization_pct_winners: Decimal = Decimal("0.0")
    giveback_pct: Decimal = Decimal("0.0")
    r_target_hit_rates: dict[str, Decimal] = Field(default_factory=dict)
    positive_mfe_closing_loser_pct: Decimal = Decimal("0.0")
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
