"""Configuration management with immutable risk parameters and execution safety gates."""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.domain.interfaces import LiquidationEstimator


class ExecutionGateConfig(BaseModel):
    """Controls live execution safety gates. Defaults to False (Disabled)."""

    model_config = ConfigDict(frozen=True)

    live_trading: bool = False
    enable_order_execution: bool = False

    @property
    def can_execute_live(self) -> bool:
        """Both flags must explicitly be True to permit live order dispatch."""
        return bool(self.live_trading and self.enable_order_execution)

    def assert_execution_allowed(self) -> None:
        """Raise RuntimeError if any live gate is disabled."""
        if not self.can_execute_live:
            raise RuntimeError(
                "Live order execution is strictly blocked: "
                f"LIVE_TRADING={self.live_trading}, "
                f"ENABLE_ORDER_EXECUTION={self.enable_order_execution}. "
                "Both flags must explicitly be True to submit live exchange orders."
            )

    def assert_live_execution_allowed(self) -> None:
        """Alias for assert_execution_allowed."""
        self.assert_execution_allowed()


class UserRiskConfig(BaseModel):
    """User-controlled risk parameters. Invariant: immutable by bot logic."""

    model_config = ConfigDict(frozen=True)

    # Mandatory user parameters (Decimal precision)
    allocated_funds: Decimal = Field(gt=Decimal("0"))
    leverage: Decimal = Field(ge=Decimal("1.0"), le=Decimal("20.0"))
    max_acceptable_liquidation_price: Decimal = Field(gt=Decimal("0"))

    # Optional risk parameters
    profit_target_pct: Decimal | None = None
    max_entries: int = Field(default=3, ge=1, le=10)
    max_daily_loss: Decimal | None = Field(default=None, gt=Decimal("0"))
    risk_per_trade_pct: Decimal | None = Field(default=None, gt=Decimal("0"))
    emergency_loss_limit: Decimal | None = Field(default=None, gt=Decimal("0"))
    max_total_exposure: Decimal | None = Field(default=None, gt=Decimal("0"))
    max_holding_time_hours: int | None = Field(default=None, gt=0)
    funding_threshold: Decimal | None = None
    min_entry_score: int = Field(default=85, ge=50, le=100)

    def validate_liquidation_safety(
        self,
        estimator: LiquidationEstimator,
        reference_entry_price: Decimal,
    ) -> Decimal:
        """Validate if user leverage and acceptable liquidation price are compatible.

        Uses the domain LiquidationEstimator protocol without hardcoding Binance formulas.
        If estimated liquidation > max_acceptable_liquidation_price, the configuration
        is rejected without altering user inputs.
        """
        estimated_liq = estimator.estimate_liquidation_price(
            entry_price=reference_entry_price,
            leverage=self.leverage,
            allocated_funds=self.allocated_funds,
        )

        self.validate_estimated_liquidation(estimated_liq)
        return estimated_liq

    def validate_estimated_liquidation(
        self,
        estimated_liquidation_price: Decimal,
    ) -> None:
        """Validate that a computed estimated liquidation price satisfies the floor constraint."""
        if estimated_liquidation_price > self.max_acceptable_liquidation_price:
            raise ValueError(
                "Incompatible risk configuration: Estimated liquidation price "
                f"(${estimated_liquidation_price:.2f}) exceeds user maximum acceptable "
                f"liquidation price (${self.max_acceptable_liquidation_price:.2f}) at "
                f"{self.leverage}x leverage. "
                "Configuration rejected without modifying user parameters."
            )


class BotConfig(BaseSettings):
    """Aggregated bot configuration loaded from environment or parameters."""

    model_config = SettingsConfigDict(arbitrary_types_allowed=True, extra="ignore")

    gates: ExecutionGateConfig = Field(default_factory=ExecutionGateConfig)
    risk: UserRiskConfig

    binance_api_key: SecretStr = Field(default=SecretStr(""))
    binance_api_secret: SecretStr = Field(default=SecretStr(""))
    binance_testnet: bool = True

    database_path: str = "xau_bot.db"
    log_level: str = "INFO"

    def __repr__(self) -> str:
        return (
            f"BotConfig(gates={self.gates}, risk={self.risk}, "
            f"binance_api_key=SecretStr('**********'), "
            f"binance_api_secret=SecretStr('**********'), "
            f"binance_testnet={self.binance_testnet}, "
            f"database_path='{self.database_path}', "
            f"log_level='{self.log_level}')"
        )

    def __str__(self) -> str:
        return self.__repr__()
