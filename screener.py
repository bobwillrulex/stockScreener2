"""Concurrent stock screener orchestration."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterable

from data_loader import load_earnings_dates, load_ohlcv, load_russell1000_tickers
from strategy import SignalResult, evaluate_ticker

LOGGER = logging.getLogger(__name__)


def scan_ticker(ticker: str, threshold: float = 0.1) -> SignalResult | None:
    """Scan a single ticker and return it only when it has a current signal."""
    try:
        bars = load_ohlcv(ticker)
        earnings_dates = load_earnings_dates(ticker, bars)
        result = evaluate_ticker(ticker, bars, earnings_dates, threshold=threshold)
    except Exception as exc:  # noqa: BLE001 - continue scanning other tickers
        LOGGER.warning("Failed to scan %s: %s", ticker, exc)
        return None

    if result and (result.near_earnings or result.near_yearly):
        return result
    return None


def run_scan(
    threshold: float = 0.1,
    max_workers: int = 12,
    tickers: Iterable[str] | None = None,
) -> list[dict[str, object]]:
    """Run the Russell 1000 screener concurrently and return ranked results."""
    ticker_list = list(tickers) if tickers is not None else load_russell1000_tickers()
    results: list[SignalResult] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(scan_ticker, ticker, threshold): ticker for ticker in ticker_list}
        for future in as_completed(futures):
            ticker = futures[future]
            try:
                result = future.result()
            except Exception as exc:  # noqa: BLE001 - defensive guard
                LOGGER.warning("Unhandled scan failure for %s: %s", ticker, exc)
                continue
            if result is not None:
                results.append(result)

    results.sort(
        key=lambda item: (
            item.distance_score is None,
            item.distance_score if item.distance_score is not None else float("inf"),
            item.ticker,
        )
    )
    return [result.as_dict() for result in results]
