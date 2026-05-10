"""Data access helpers for Russell 1000 constituents and market data."""

from __future__ import annotations

import io
import logging
import os
import re
import threading
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import TypeVar
from urllib.request import Request, urlopen

import pandas as pd
import yfinance as yf

LOGGER = logging.getLogger(__name__)

T = TypeVar("T")
YFINANCE_REQUEST_DELAY_SECONDS = float(os.getenv("YFINANCE_REQUEST_DELAY_SECONDS", "1.0"))
YFINANCE_EARNINGS_ENABLED = os.getenv("YFINANCE_EARNINGS_ENABLED", "false").lower() in {
    "1",
    "true",
    "yes",
    "on",
}
_LAST_YFINANCE_REQUEST_AT = 0.0
_YFINANCE_REQUEST_LOCK = threading.Lock()

BASE_DIR = Path(__file__).resolve().parent
RUSSELL_CACHE = BASE_DIR / "russell1000.csv"
DATA_CACHE_DIR = BASE_DIR / "data_cache"
TRUSTED_RUSSELL_SOURCES = {"ishares"}
RUSSELL_MIN_TICKERS = 900
TICKER_PATTERN = re.compile(r"^[A-Z]{1,5}(?:-[A-Z]{1,2})?$")
ISHARES_HOLDINGS_URL = (
    "https://www.ishares.com/us/products/239707/ishares-russell-1000-etf/"
    "1467271812596.ajax?fileType=csv&fileName=IWB_holdings&dataType=fund"
)
ISHARES_REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/csv,application/csv,text/plain,*/*",
}


def _normalize_ticker(ticker: object) -> str | None:
    if pd.isna(ticker):
        return None
    value = str(ticker).strip().upper().replace(".", "-")
    if not value or value in {"NAN", "CASH", "--", "-"}:
        return None
    if not TICKER_PATTERN.fullmatch(value):
        return None
    return value


def _download_ishares_holdings_csv() -> str:
    request = Request(ISHARES_HOLDINGS_URL, headers=ISHARES_REQUEST_HEADERS)
    with urlopen(request, timeout=30) as response:  # noqa: S310 - fixed trusted HTTPS URL
        return response.read().decode("utf-8-sig")


def _read_ishares_holdings() -> pd.DataFrame:
    csv_text = _download_ishares_holdings_csv()
    lines = csv_text.splitlines()
    header_index = next(
        (
            index
            for index, line in enumerate(lines)
            if line.strip().lower().startswith("ticker,") or ",ticker," in line.strip().lower()
        ),
        None,
    )
    if header_index is None:
        raise RuntimeError("Unable to locate Ticker header in iShares holdings CSV")
    return pd.read_csv(io.StringIO("\n".join(lines[header_index:])))


def _fetch_tickers_from_ishares() -> list[str]:
    """Fetch Russell 1000 tickers from the iShares IWB holdings CSV."""
    raw = _read_ishares_holdings()
    normalized_columns = {str(column).strip().lower(): column for column in raw.columns}
    symbol_column = normalized_columns.get("ticker")
    if symbol_column is None:
        raise RuntimeError("iShares holdings CSV does not contain a Ticker column")
    tickers = raw[symbol_column].map(_normalize_ticker).dropna().tolist()
    return sorted(dict.fromkeys(tickers))


def _load_cached_russell_tickers() -> list[str]:
    frame = pd.read_csv(RUSSELL_CACHE)
    if "ticker" not in frame.columns:
        return []

    cached_tickers = frame["ticker"].map(_normalize_ticker).dropna().tolist()
    if len(cached_tickers) < RUSSELL_MIN_TICKERS:
        LOGGER.warning(
            "Ignoring Russell 1000 cache with only %s valid tickers; refreshing from iShares.",
            len(cached_tickers),
        )
        return []

    if "source" not in frame.columns:
        LOGGER.warning("Ignoring Russell 1000 cache without source metadata; refreshing from iShares.")
        return []

    sources = {str(source).strip().lower() for source in frame["source"].dropna().unique()}
    if not sources <= TRUSTED_RUSSELL_SOURCES:
        LOGGER.warning(
            "Ignoring Russell 1000 cache from untrusted source(s) %s; refreshing from iShares.",
            ", ".join(sorted(sources)) or "unknown",
        )
        return []

    return cached_tickers


def load_russell1000_tickers(force_refresh: bool = False) -> list[str]:
    """Load Russell 1000 tickers, creating the local CSV cache if needed."""
    if RUSSELL_CACHE.exists() and not force_refresh:
        cached_tickers = _load_cached_russell_tickers()
        if cached_tickers:
            return cached_tickers

    tickers = _fetch_tickers_from_ishares()
    if len(tickers) < RUSSELL_MIN_TICKERS:
        raise RuntimeError(f"Only loaded {len(tickers)} Russell 1000 tickers from iShares")

    pd.DataFrame({"ticker": tickers, "source": "ishares"}).to_csv(RUSSELL_CACHE, index=False)
    return tickers


def _flatten_yfinance_columns(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = [col[0] if isinstance(col, tuple) else col for col in data.columns]
    return data


def _cache_path(ticker: str, interval: str) -> Path:
    safe_ticker = ticker.replace("/", "-")
    return DATA_CACHE_DIR / f"{safe_ticker}_{interval}.pkl"


def _read_cached_bars(ticker: str, interval: str, max_age_hours: int) -> pd.DataFrame | None:
    path = _cache_path(ticker, interval)
    if not path.exists():
        return None
    modified = datetime.fromtimestamp(path.stat().st_mtime)
    if datetime.now() - modified > timedelta(hours=max_age_hours):
        return None
    try:
        return pd.read_pickle(path)
    except Exception as exc:  # noqa: BLE001 - bad cache should not break scans
        LOGGER.warning("Unable to read cache for %s: %s", ticker, exc)
        return None


def _write_cached_bars(ticker: str, interval: str, frame: pd.DataFrame) -> None:
    DATA_CACHE_DIR.mkdir(exist_ok=True)
    try:
        frame.to_pickle(_cache_path(ticker, interval))
    except Exception as exc:  # noqa: BLE001 - cache failures are non-fatal
        LOGGER.warning("Unable to write cache for %s: %s", ticker, exc)


def _call_yfinance_with_delay(operation: Callable[[], T]) -> T:
    """Run a yfinance request after a small global delay to reduce rate limits."""
    global _LAST_YFINANCE_REQUEST_AT

    with _YFINANCE_REQUEST_LOCK:
        elapsed = time.monotonic() - _LAST_YFINANCE_REQUEST_AT
        sleep_for = YFINANCE_REQUEST_DELAY_SECONDS - elapsed
        if sleep_for > 0:
            time.sleep(sleep_for)
        _LAST_YFINANCE_REQUEST_AT = time.monotonic()

    return operation()


def load_ohlcv(ticker: str, period: str = "2y", max_age_hours: int = 6) -> pd.DataFrame:
    """Load OHLCV bars and return 4-hour candles.

    yfinance supports recent intraday bars only. The loader first requests hourly bars
    and resamples them to 4 hours. If that fails, it falls back to daily bars so the
    screener can still run with coarser candles.
    """
    cached = _read_cached_bars(ticker, "4h", max_age_hours)
    if cached is not None and not cached.empty:
        return cached

    symbol = ticker.replace(".", "-")
    hourly = _call_yfinance_with_delay(
        lambda: yf.download(
            symbol,
            period=period,
            interval="60m",
            auto_adjust=False,
            progress=False,
            threads=False,
        )
    )
    data = _flatten_yfinance_columns(hourly)

    if data.empty:
        daily = _call_yfinance_with_delay(
            lambda: yf.download(
                symbol,
                period=period,
                interval="1d",
                auto_adjust=False,
                progress=False,
                threads=False,
            )
        )
        data = _flatten_yfinance_columns(daily)

    if data.empty:
        return data

    data = data.rename(columns={col: str(col).title() for col in data.columns})
    required = ["Open", "High", "Low", "Close", "Volume"]
    data = data[[col for col in required if col in data.columns]].dropna()
    if not isinstance(data.index, pd.DatetimeIndex):
        data.index = pd.to_datetime(data.index)
    if data.index.tz is not None:
        data.index = data.index.tz_convert(None)

    if len(data) > 1 and (data.index[1:] - data.index[:-1]).median() < pd.Timedelta(days=1):
        data = data.resample("4h").agg(
            {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
        ).dropna()

    _write_cached_bars(ticker, "4h", data)
    return data


def _mock_earnings_dates_from_bars(bars: pd.DataFrame | None = None) -> list[pd.Timestamp]:
    """Create quarterly earnings-anchor dates without contacting a remote provider."""
    if bars is None or bars.empty:
        start = pd.Timestamp.utcnow().tz_localize(None) - pd.DateOffset(years=2)
        end = pd.Timestamp.utcnow().tz_localize(None)
    else:
        start = pd.Timestamp(bars.index.min()).tz_localize(None)
        end = pd.Timestamp(bars.index.max()).tz_localize(None)
    return list(pd.date_range(start=start, end=end, freq="QS"))


def load_earnings_dates(ticker: str, bars: pd.DataFrame | None = None) -> list[pd.Timestamp]:
    """Load earnings-anchor dates.

    The default path intentionally avoids yfinance's earnings endpoint because it is
    prone to aggressive rate limiting during broad Russell 1000 scans. Set
    ``YFINANCE_EARNINGS_ENABLED=true`` to opt back into provider earnings dates;
    otherwise quarterly anchors are generated from the available bar range.
    """
    if not YFINANCE_EARNINGS_ENABLED:
        return _mock_earnings_dates_from_bars(bars)

    symbol = ticker.replace(".", "-")
    try:
        earnings = _call_yfinance_with_delay(lambda: yf.Ticker(symbol).get_earnings_dates(limit=24))
        if earnings is not None and not earnings.empty:
            index = pd.to_datetime(earnings.index, errors="coerce")
            index = index[~pd.isna(index)]
            return [pd.Timestamp(value).tz_localize(None) for value in index]
    except Exception as exc:  # noqa: BLE001 - yfinance earnings are often unavailable
        LOGGER.info("Using generated quarterly earnings anchors for %s: %s", ticker, exc)

    return _mock_earnings_dates_from_bars(bars)
