"""Deterministic Binance test fixtures for offline testing."""

from typing import Any

EXCHANGE_INFO_RAW: dict[str, Any] = {
    "timezone": "UTC",
    "serverTime": 1700000000000,
    "symbols": [
        {
            "symbol": "XAUUSDT",
            "pair": "XAUUSDT",
            "contractType": "PERPETUAL",
            "status": "TRADING",
            "baseAsset": "XAU",
            "quoteAsset": "USDT",
            "pricePrecision": 2,
            "quantityPrecision": 3,
            "filters": [
                {
                    "filterType": "PRICE_FILTER",
                    "minPrice": "100.00",
                    "maxPrice": "100000.00",
                    "tickSize": "0.01",
                },
                {
                    "filterType": "LOT_SIZE",
                    "minQty": "0.001",
                    "maxQty": "1000.000",
                    "stepSize": "0.001",
                },
                {
                    "filterType": "MIN_NOTIONAL",
                    "notional": "5.0",
                },
            ],
        },
        {
            "symbol": "BTCUSDT",
            "pair": "BTCUSDT",
            "contractType": "PERPETUAL",
            "status": "TRADING",
            "baseAsset": "BTC",
            "quoteAsset": "USDT",
            "pricePrecision": 1,
            "quantityPrecision": 3,
            "filters": [
                {
                    "filterType": "PRICE_FILTER",
                    "minPrice": "100.0",
                    "maxPrice": "1000000.0",
                    "tickSize": "0.1",
                },
                {
                    "filterType": "LOT_SIZE",
                    "minQty": "0.001",
                    "maxQty": "1000.000",
                    "stepSize": "0.001",
                },
                {
                    "filterType": "MIN_NOTIONAL",
                    "notional": "5.0",
                },
            ],
        },
    ],
}

KLINES_RAW_15M: list[list[Any]] = [
    [
        1700000000000,  # Open time (10:00)
        "2700.00",  # Open
        "2710.50",  # High
        "2695.20",  # Low
        "2705.00",  # Close
        "150.250",  # Volume
        1700000899999,  # Close time (10:14:59.999)
        "406426.25",  # Quote asset volume
        1250,  # Number of trades
        "80.100",  # Taker buy base asset volume
        "216670.50",  # Taker buy quote asset volume
        "0",
    ],
    [
        1700000900000,  # Open time (10:15)
        "2705.00",
        "2715.00",
        "2702.00",
        "2712.30",
        "180.500",
        1700001799999,  # Close time (10:29:59.999)
        "489110.15",
        1420,
        "95.200",
        "257850.30",
        "0",
    ],
    [
        1700001800000,  # Open time (10:30)
        "2712.30",
        "2720.00",
        "2708.00",
        "2718.50",
        "210.000",
        1700002699999,  # Close time (10:44:59.999)
        "570150.00",
        1600,
        "110.000",
        "298450.00",
        "0",
    ],
]

PREMIUM_INDEX_RAW: dict[str, Any] = {
    "symbol": "XAUUSDT",
    "markPrice": "2704.80000000",
    "indexPrice": "2704.50000000",
    "estimatedSettlePrice": "2704.75000000",
    "lastFundingRate": "0.00010000",
    "interestRate": "0.00010000",
    "nextFundingTime": 1700006400000,
    "time": 1700000900000,
}

TICKER_PRICE_RAW: dict[str, Any] = {
    "symbol": "XAUUSDT",
    "price": "2705.10",
    "time": 1700000900000,
}

WS_KLINE_PAYLOAD_CLOSED: dict[str, Any] = {
    "e": "kline",
    "E": 1700000900050,
    "s": "XAUUSDT",
    "k": {
        "t": 1700000000000,
        "T": 1700000899999,
        "s": "XAUUSDT",
        "i": "15m",
        "f": 100,
        "L": 200,
        "o": "2700.00",
        "c": "2705.00",
        "h": "2710.50",
        "l": "2695.20",
        "v": "150.250",
        "n": 101,
        "x": True,  # Final candle
        "q": "406426.25",
        "V": "80.100",
        "Q": "216670.50",
        "B": "0",
    },
}

WS_KLINE_PAYLOAD_OPEN: dict[str, Any] = {
    "e": "kline",
    "E": 1700000450000,
    "s": "XAUUSDT",
    "k": {
        "t": 1700000000000,
        "T": 1700000899999,
        "s": "XAUUSDT",
        "i": "15m",
        "f": 100,
        "L": 150,
        "o": "2700.00",
        "c": "2703.10",
        "h": "2708.00",
        "l": "2698.00",
        "v": "75.000",
        "n": 51,
        "x": False,  # In-progress
        "q": "202732.50",
        "V": "40.000",
        "Q": "108124.00",
        "B": "0",
    },
}
