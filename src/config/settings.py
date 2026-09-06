"""Configuration management with immutable risk parameters and execution safety gates."""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.utils.security import mask_secret


class ExecutionGateConfig(BaseModel):
    """Controls live execution safety gates. Defaults to False (Disabled)."""

    model_config = ConfigDict(frozen=True)

    live_trading: bool = False
    enable_order_execution: bool = False

    @property
    def can_execute_live(self) -> bool:
        """Both flags must explicitly be True to permit live order dispatch."""
        return self.live_trading and self.enable_order_execution

    def assert_live_execution_allowed(self) -> None:
        """Raise RuntimeError if any live gate is disabled."""
        if not self.can_execute_live:
            raise RuntimeError(
                "Live order execution is strictly blocked: "
                f"LIVE_TRADING={self.live_trading}, "
                f"ENABLE_ORDER_EXECUTION={self.enable_order_execution}. "
                "Both flags must explicitly be True to submit live exchange orders."
            )


class UserRiskConfig(BaseModel):
    """User-controlled risk parameters. Invariant: immutable by bot logic."""

    model_config = ConfigDict(frozen=True)

    # Mandatory user parameters
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

    def validate_liquidation_compatibility(
        self,
        reference_entry_price: Decimal,
        maintenance_margin_rate: Decimal = Decimal("0.004"),
    ) -> Decimal:
        """Validate if user leverage and acceptable liquidation price are compatible.

        For a Long position:
        Estimated Liquidation Price ~= EntryPrice * (1 - 1/Leverage + MMR).

        If Estimated Liquidation Price > max_acceptable_liquidation_price, the position
        would liquidate prematurely before the user's acceptable price threshold is reached.
        In this case, the configuration must be rejected without altering user inputs.
        """
        # Est Liq = P_entry * (1 - (1/L) + MMR)
        margin_buffer = Decimal("1.0") - (Decimal("1.0") / self.leverage) + maintenance_margin_rate
        estimated_liq_price = reference_entry_price * margin_buffer

        if estimated_liq_price > self.max_acceptable_liquidation_price:
            raise ValueError(
                "Incompatible risk configuration: Estimated liquidation price "
                f"(${estimated_liq_price:.2f}) is higher than user maximum acceptable "
                f"liquidation price (${self.max_acceptable_liquidation_price:.2f}) at "
                f"{self.leverage}x leverage and reference entry ${reference_entry_price:.2f}. "
                "Reduce leverage or adjust maximum acceptable liquidation price."
            )

        return estimated_liq_price


class BotConfig(BaseSettings):
    """Aggregated bot configuration loaded from environment or parameters."""

    model_config = SettingsConfigDict(arbitrary_types_allowed=True, extra="ignore")

    gates: ExecutionGateConfig = Field(default_factory=ExecutionGateConfig)
    risk: UserRiskConfig

    binance_api_key: str = ""
    binance_api_secret: str = ""
    binance_testnet: bool = True

    database_path: str = "xau_bot.db"
    log_level: str = "INFO"

    def __repr__(self) -> str:
        masked_key = mask_secret(self.binance_api_key) if self.binance_api_key else ""
        masked_secret = mask_secret(self.binance_api_secret) if self.binance_api_secret else ""
        return (
            f"BotConfig(gates={self.gates}, risk={self.risk}, "
            f"binance_api_key='{masked_key}', binance_api_secret='{masked_secret}', "
            f"binance_testnet={self.binance_testnet}, database_path='{self.database_path}', "
            f"log_level='{self.log_level}')"
        )

    def __str__(self) -> str:
        return self.__repr__()
