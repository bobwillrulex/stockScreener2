"""Data access helpers for Russell 1000 constituents and market data."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

LOGGER = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
RUSSELL_CACHE = BASE_DIR / "russell1000.csv"
DATA_CACHE_DIR = BASE_DIR / "data_cache"
WIKIPEDIA_URLS = (
    "https://en.wikipedia.org/wiki/Russell_1000_Index",
    "https://en.wikipedia.org/wiki/Russell_1000",
)
ISHARES_HOLDINGS_URL = (
    "https://www.ishares.com/us/products/239707/ishares-russell-1000-etf/"
    "1467271812596.ajax?fileType=csv&fileName=IWB_holdings&dataType=fund"
)


def _normalize_ticker(ticker: object) -> str | None:
    if pd.isna(ticker):
        return None
    value = str(ticker).strip().upper().replace(".", "-")
    if not value or value in {"NAN", "CASH", "--", "-"}:
        return None
    return value


def _extract_tickers_from_tables(tables: list[pd.DataFrame]) -> list[str]:
    candidates: list[str] = []
    ticker_column_names = {"ticker", "symbol", "ticker symbol", "stock symbol"}
    for table in tables:
        normalized_columns = {str(col).strip().lower(): col for col in table.columns}
        selected_column = None
        for column_name, original_column in normalized_columns.items():
            if column_name in ticker_column_names or "ticker" in column_name or "symbol" in column_name:
                selected_column = original_column
                break
        if selected_column is None:
            continue
        candidates.extend(table[selected_column].map(_normalize_ticker).dropna().tolist())
    return sorted(dict.fromkeys(candidates))


def _fetch_tickers_from_wikipedia() -> list[str]:
    for url in WIKIPEDIA_URLS:
        try:
            tables = pd.read_html(url)
        except Exception as exc:  # noqa: BLE001 - keep fallback path resilient
            LOGGER.warning("Unable to read Russell 1000 tickers from %s: %s", url, exc)
            continue
        tickers = _extract_tickers_from_tables(tables)
        if len(tickers) >= 900:
            LOGGER.info("Loaded %s Russell 1000 tickers from %s", len(tickers), url)
            return tickers[:1000]
        if tickers:
            LOGGER.warning("Only found %s candidate tickers at %s", len(tickers), url)
    return []


def _fetch_tickers_from_ishares() -> list[str]:
    raw = pd.read_csv(ISHARES_HOLDINGS_URL, skiprows=9)
    symbol_column = "Ticker" if "Ticker" in raw.columns else raw.columns[0]
    tickers = raw[symbol_column].map(_normalize_ticker).dropna().tolist()
    return sorted(dict.fromkeys(tickers))[:1000]


def load_russell1000_tickers(force_refresh: bool = False) -> list[str]:
    """Load Russell 1000 tickers, creating the local CSV cache if needed."""
    if RUSSELL_CACHE.exists() and not force_refresh:
        frame = pd.read_csv(RUSSELL_CACHE)
        cached_tickers = frame["ticker"].map(_normalize_ticker).dropna().tolist()
        if cached_tickers:
            return cached_tickers

    tickers = _fetch_tickers_from_wikipedia()
    source = "wikipedia"
    if len(tickers) < 900:
        tickers = _fetch_tickers_from_ishares()
        source = "ishares"

    if not tickers:
        raise RuntimeError("Unable to load Russell 1000 ticker list")

    pd.DataFrame({"ticker": tickers, "source": source}).to_csv(RUSSELL_CACHE, index=False)
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
    hourly = yf.download(
        symbol,
        period=period,
        interval="60m",
        auto_adjust=False,
        progress=False,
        threads=False,
    )
    data = _flatten_yfinance_columns(hourly)

    if data.empty:
        daily = yf.download(
            symbol,
            period=period,
            interval="1d",
            auto_adjust=False,
            progress=False,
            threads=False,
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


def load_earnings_dates(ticker: str, bars: pd.DataFrame | None = None) -> list[pd.Timestamp]:
    """Load earnings dates, mocking quarterly anchors if provider data is unavailable."""
    symbol = ticker.replace(".", "-")
    try:
        earnings = yf.Ticker(symbol).get_earnings_dates(limit=24)
        if earnings is not None and not earnings.empty:
            index = pd.to_datetime(earnings.index, errors="coerce")
            index = index[~pd.isna(index)]
            return [pd.Timestamp(value).tz_localize(None) for value in index]
    except Exception as exc:  # noqa: BLE001 - yfinance earnings are often unavailable
        LOGGER.info("Using mocked earnings dates for %s: %s", ticker, exc)

    if bars is None or bars.empty:
        start = pd.Timestamp.utcnow().tz_localize(None) - pd.DateOffset(years=2)
        end = pd.Timestamp.utcnow().tz_localize(None)
    else:
        start = pd.Timestamp(bars.index.min()).tz_localize(None)
        end = pd.Timestamp(bars.index.max()).tz_localize(None)
    return list(pd.date_range(start=start, end=end, freq="QS"))
