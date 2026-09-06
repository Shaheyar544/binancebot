"""Fetch historical XAUUSDT candlestick data from Binance Futures."""

import asyncio
import json
from decimal import Decimal
from pathlib import Path

import httpx

from src.domain.enums import Timeframe
from src.domain.models import Candle


async def fetch_all_klines(
    symbol: str = "XAUUSDT",
    interval: str = "15m",
    start_time: int = 1765411200000,  # 2025-12-11
    output_file: str = "data/xauusdt_15m.json",
) -> list[Candle]:
    """Download chronological 15m candles from Binance Futures without gaps."""
    base_url = "https://fapi.binance.com/fapi/v1/klines"
    current_start = start_time
    all_candles: list[Candle] = []
    seen_open_times: set[int] = set()

    Path(output_file).parent.mkdir(parents=True, exist_ok=True)

    print(f"Starting historical data download for {symbol} ({interval})...")

    async with httpx.AsyncClient(timeout=15.0) as client:
        while True:
            params: dict[str, str | int] = {
                "symbol": symbol,
                "interval": interval,
                "startTime": current_start,
                "limit": 1500,
            }
            resp = await client.get(base_url, params=params)
            resp.raise_for_status()
            raw_bars = resp.json()

            if not raw_bars:
                break

            new_bars_count = 0
            for bar in raw_bars:
                open_t = int(bar[0])
                if open_t in seen_open_times:
                    continue
                seen_open_times.add(open_t)

                candle = Candle(
                    symbol=symbol,
                    timeframe=Timeframe.M15,
                    open_time=open_t,
                    open=Decimal(str(bar[1])),
                    high=Decimal(str(bar[2])),
                    low=Decimal(str(bar[3])),
                    close=Decimal(str(bar[4])),
                    volume=Decimal(str(bar[5])),
                    close_time=int(bar[6]),
                    is_closed=True,
                )
                all_candles.append(candle)
                new_bars_count += 1

            last_open = int(raw_bars[-1][0])
            print(
                f"Fetched {len(raw_bars)} bars up to timestamp {last_open}. "
                f"Total valid candles: {len(all_candles)}"
            )

            if len(raw_bars) < 1500:
                break

            current_start = last_open + (15 * 60 * 1000)
            await asyncio.sleep(0.1)  # Respect Binance API rate limits

    # Sort strictly by open_time
    all_candles.sort(key=lambda c: c.open_time)

    # Save to JSON
    serialized = [c.model_dump(mode="json") for c in all_candles]
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(serialized, f)

    print(f"Successfully saved {len(all_candles)} candles to {output_file}")
    return all_candles


if __name__ == "__main__":
    asyncio.run(fetch_all_klines())
