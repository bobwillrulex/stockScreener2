"""Concurrent stock screener orchestration."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from typing import Iterable

from data_loader import (
    load_earnings_dates,
    load_ohlcv,
    load_russell1000_tickers,
    load_ticker_metadata,
)
from strategy import SignalResult, evaluate_ticker

LOGGER = logging.getLogger(__name__)


def _diagnostic(message: str) -> None:
    """Emit a diagnostic message to the console immediately."""
    print(message, flush=True)


def scan_ticker(ticker: str, threshold: float = 0.1) -> SignalResult | None:
    """Scan a single ticker and return it only when it has a current signal."""
    _diagnostic(f"Fetching {ticker}...")
    try:
        bars = load_ohlcv(ticker)
        if bars is None or bars.empty:
            _diagnostic(f"Fetching {ticker} failed: no OHLCV data returned.")
            return None
        _diagnostic(f"Fetching {ticker} success.")

        earnings_dates = load_earnings_dates(ticker, bars)
        result = evaluate_ticker(ticker, bars, earnings_dates, threshold=threshold)
    except Exception as exc:  # noqa: BLE001 - continue scanning other tickers
        _diagnostic(f"Fetching {ticker} failed: {exc}")
        LOGGER.warning("Failed to scan %s: %s", ticker, exc)
        return None

    if result is None:
        _diagnostic(f"Proximity detection failed for {ticker}: no evaluable proximity result.")
        return None

    _diagnostic(f"Proximity detection success for {ticker}.")
    if result.near_earnings or result.near_yearly:
        try:
            metadata = load_ticker_metadata(ticker)
        except Exception as exc:  # noqa: BLE001 - metadata is display-only
            _diagnostic(f"Metadata lookup failed for {ticker}: {exc}")
            LOGGER.warning("Failed to load metadata for %s: %s", ticker, exc)
            metadata = {}
        return replace(
            result,
            company_name=metadata.get("company_name"),
            market_cap=metadata.get("market_cap"),
        )
    return None


def run_scan(
    threshold: float = 0.1,
    max_workers: int = 4,
    tickers: Iterable[str] | None = None,
) -> list[dict[str, object]]:
    """Run the Russell 1000 screener concurrently and return ranked results."""
    _diagnostic("Loading ticker list...")
    try:
        ticker_list = list(tickers) if tickers is not None else load_russell1000_tickers()
    except Exception as exc:  # noqa: BLE001 - surface ticker-list load failures clearly
        _diagnostic(f"Loading ticker list failed: {exc}")
        raise
    _diagnostic(f"Loading ticker list success: {len(ticker_list)} tickers ready.")
    _diagnostic("Running proximity list...")
    results: list[SignalResult] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(scan_ticker, ticker, threshold): ticker for ticker in ticker_list}
        for future in as_completed(futures):
            ticker = futures[future]
            try:
                result = future.result()
            except Exception as exc:  # noqa: BLE001 - defensive guard
                _diagnostic(f"Proximity detection failed for {ticker}: {exc}")
                LOGGER.warning("Unhandled scan failure for %s: %s", ticker, exc)
                continue
            if result is not None:
                results.append(result)

    results.sort(
        key=lambda item: (
            item.market_cap is None,
            -(item.market_cap or 0),
            item.ticker,
        )
    )
    _diagnostic(f"Proximity list success: {len(results)} matching tickers found.")
    return [result.as_dict() for result in results]
