from decimal import Decimal

import pytest

from scripts.build_watchlist import build_watchlist


def test_watchlist_ranks_turnover_and_filters_ineligible_contracts():
    contracts = [
        {"symbol": f"{name}_USDT", "state": 0, "futureType": 1,
         "settleCoin": "USDT", "priceUnit": "0.001"}
        for name in ("BTC", "ETH", "SOL", "XRP", "ADA")
    ]
    contracts[3]["preMarket"] = True
    contracts[4]["state"] = 1
    tickers = [
        {"symbol": f"{name}_USDT", "amount24": turnover}
        for name, turnover in (("BTC", 1000), ("ETH", 12), ("SOL", 25),
                               ("SOL", 1), ("XRP", 500), ("ADA", 400))
    ]
    assert build_watchlist(contracts, tickers, 3, "BTC_USDT") == "SOL_USDT:0.001,ETH_USDT:0.001"
    with pytest.raises(ValueError, match="Insufficient"):
        build_watchlist(contracts, tickers, 4, "BTC_USDT")
    with pytest.raises(ValueError, match="not an eligible"):
        build_watchlist(contracts, tickers, 2, "XRP_USDT")
    assert build_watchlist(contracts, tickers, 2, "BTC_USDT", Decimal(25)) == "SOL_USDT:0.001"
    with pytest.raises(ValueError, match="Insufficient"):
        build_watchlist(contracts, tickers, 3, "BTC_USDT", Decimal(25))
    with pytest.raises(ValueError, match="nonnegative"):
        build_watchlist(contracts, tickers, 2, "BTC_USDT", Decimal("NaN"))
