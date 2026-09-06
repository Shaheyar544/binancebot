"""Walk-forward and out-of-sample validation engine for trading strategies."""

from collections.abc import Sequence
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from src.backtest.engine import BacktestEngine
from src.backtest.models import BacktestConfig, BacktestResult
from src.domain.models import Candle


class WalkForwardFold(BaseModel):
    """Immutable representation of an individual train/test fold."""

    model_config = ConfigDict(frozen=True)

    fold_index: int
    train_start_time: int
    train_end_time: int
    test_start_time: int
    test_end_time: int
    in_sample_result: BacktestResult
    out_of_sample_result: BacktestResult
    profit_factor_retention: Decimal = Decimal("0.0")
    win_rate_retention: Decimal = Decimal("0.0")


class WalkForwardResult(BaseModel):
    """Aggregate summary of walk-forward validation across all folds."""

    model_config = ConfigDict(frozen=True)

    total_folds: int
    folds: list[WalkForwardFold] = Field(default_factory=list)
    overall_in_sample_profit: Decimal = Decimal("0.0")
    overall_out_of_sample_profit: Decimal = Decimal("0.0")
    profitable_folds: int = 0
    stability_score: Decimal = Decimal("0.0")
    is_robust: bool = False


class WalkForwardEngine:
    """Performs rigorous out-of-sample validation without lookahead bias.

    Splits historical candle sequences into chronological train (in-sample)
    and test (out-of-sample) windows to assess strategy stability across regimes.
    """

    def __init__(
        self,
        config: BacktestConfig,
        train_candles_count: int = 100,
        test_candles_count: int = 30,
        step_candles_count: int = 30,
        anchored: bool = False,
    ) -> None:
        if train_candles_count <= 0 or test_candles_count <= 0 or step_candles_count <= 0:
            raise ValueError("All candle count parameters must be strictly positive")

        self.config = config
        self.train_candles_count = train_candles_count
        self.test_candles_count = test_candles_count
        self.step_candles_count = step_candles_count
        self.anchored = anchored

    def generate_folds(
        self,
        candles: Sequence[Candle],
    ) -> list[tuple[Sequence[Candle], Sequence[Candle]]]:
        """Generate chronological (train, test) slices with zero lookahead overlap."""
        total_len = len(candles)
        min_required = self.train_candles_count + self.test_candles_count
        if total_len < min_required:
            return []

        folds: list[tuple[Sequence[Candle], Sequence[Candle]]] = []
        current_train_start = 0

        while True:
            train_start = 0 if self.anchored else current_train_start
            train_end = current_train_start + self.train_candles_count
            test_end = train_end + self.test_candles_count

            if test_end > total_len:
                break

            train_slice = candles[train_start:train_end]
            test_slice = candles[train_end:test_end]

            # Invariant: train strictly precedes test
            assert train_slice[-1].close_time < test_slice[0].open_time, (
                f"Lookahead violation: train close {train_slice[-1].close_time} >= "
                f"test open {test_slice[0].open_time}"
            )

            folds.append((train_slice, test_slice))
            current_train_start += self.step_candles_count

        return folds

    def run(self, candles: Sequence[Candle]) -> WalkForwardResult:
        """Execute walk-forward evaluation across all chronological splits."""
        data_folds = self.generate_folds(candles)
        if not data_folds:
            return WalkForwardResult(total_folds=0)

        evaluated_folds: list[WalkForwardFold] = []
        overall_is_profit = Decimal("0.0")
        overall_oos_profit = Decimal("0.0")
        profitable_oos_count = 0

        for fold_idx, (train_slice, test_slice) in enumerate(data_folds):
            if fold_idx % 10 == 0 or fold_idx == len(data_folds) - 1:
                print(
                    f"  [WalkForward] Fold {fold_idx + 1}/{len(data_folds)} "
                    f"({(fold_idx + 1) * 100 // len(data_folds)}%)...",
                    flush=True,
                )

            # 1. Run in-sample backtest
            engine_is = BacktestEngine(config=self.config)
            result_is = engine_is.run(train_slice)

            # 2. Run out-of-sample backtest
            engine_oos = BacktestEngine(config=self.config)
            result_oos = engine_oos.run(test_slice)

            # 3. Compute retention ratios
            pf_retention = (
                round(result_oos.profit_factor / result_is.profit_factor, 2)
                if result_is.profit_factor > Decimal("0.0")
                else Decimal("0.0")
            )
            wr_retention = (
                round(result_oos.win_rate / result_is.win_rate, 2)
                if result_is.win_rate > Decimal("0.0")
                else Decimal("0.0")
            )

            fold = WalkForwardFold(
                fold_index=fold_idx,
                train_start_time=train_slice[0].open_time,
                train_end_time=train_slice[-1].close_time,
                test_start_time=test_slice[0].open_time,
                test_end_time=test_slice[-1].close_time,
                in_sample_result=result_is,
                out_of_sample_result=result_oos,
                profit_factor_retention=pf_retention,
                win_rate_retention=wr_retention,
            )
            evaluated_folds.append(fold)

            overall_is_profit += result_is.net_profit
            overall_oos_profit += result_oos.net_profit
            if result_oos.net_profit >= Decimal("0.0"):
                profitable_oos_count += 1

        total_folds = len(evaluated_folds)
        stability_score = (
            round(Decimal(str(profitable_oos_count)) / Decimal(str(total_folds)), 2)
            if total_folds > 0
            else Decimal("0.0")
        )
        is_robust = stability_score >= Decimal("0.50") and overall_oos_profit >= Decimal("0.0")

        return WalkForwardResult(
            total_folds=total_folds,
            folds=evaluated_folds,
            overall_in_sample_profit=overall_is_profit,
            overall_out_of_sample_profit=overall_oos_profit,
            profitable_folds=profitable_oos_count,
            stability_score=stability_score,
            is_robust=is_robust,
        )
