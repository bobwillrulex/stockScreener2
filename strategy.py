"""Anchored VWAP strategy primitives for the stock screener."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class SignalResult:
    """Screener result for one ticker."""

    ticker: str
    company_name: str | None
    market_cap: int | None
    near_earnings: bool
    near_yearly: bool
    min_distance_earnings: float | None
    min_distance_yearly: float | None
    last_price: float | None

    @property
    def distance_score(self) -> float | None:
        """Smallest available distance for ranking."""
        distances = [
            value
            for value in (self.min_distance_earnings, self.min_distance_yearly)
            if value is not None and np.isfinite(value)
        ]
        return min(distances) if distances else None

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return {
            "ticker": self.ticker,
            "company_name": self.company_name,
            "market_cap": self.market_cap,
            "near_earnings": self.near_earnings,
            "near_yearly": self.near_yearly,
            "min_distance_earnings": self.min_distance_earnings,
            "min_distance_yearly": self.min_distance_yearly,
            "distance_score": self.distance_score,
            "last_price": self.last_price,
        }


def _normalize_datetime_index(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    if not isinstance(data.index, pd.DatetimeIndex):
        data.index = pd.to_datetime(data.index)
    if data.index.tz is not None:
        data.index = data.index.tz_convert(None)
    return data.sort_index()


def anchored_vwap(frame: pd.DataFrame, groups: pd.Series) -> pd.DataFrame:
    """Compute anchored VWAP and weighted standard deviation by reset group.

    The weighted variance is calculated with cumulative weighted moments:
    E[x^2] - E[x]^2, where x is HLC3 and weights are volume.
    """
    if frame.empty:
        return pd.DataFrame(index=frame.index, columns=["vwap", "stdev"])

    required = {"High", "Low", "Close", "Volume"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Missing columns required for VWAP: {sorted(missing)}")

    data = _normalize_datetime_index(frame)
    groups = pd.Series(groups, index=data.index).ffill().fillna(0).astype(int)

    hlc3 = (data["High"] + data["Low"] + data["Close"]) / 3.0
    volume = data["Volume"].clip(lower=0).fillna(0)
    weighted_price = hlc3 * volume
    weighted_price_sq = (hlc3**2) * volume

    cumulative_volume = volume.groupby(groups).cumsum()
    cumulative_weighted_price = weighted_price.groupby(groups).cumsum()
    cumulative_weighted_price_sq = weighted_price_sq.groupby(groups).cumsum()

    vwap = cumulative_weighted_price / cumulative_volume.replace(0, np.nan)
    second_moment = cumulative_weighted_price_sq / cumulative_volume.replace(0, np.nan)
    variance = (second_moment - (vwap**2)).clip(lower=0)
    stdev = np.sqrt(variance)

    return pd.DataFrame({"vwap": vwap, "stdev": stdev}, index=data.index)


def yearly_groups(frame: pd.DataFrame) -> pd.Series:
    """Create reset groups anchored to the first bar of each calendar year."""
    data = _normalize_datetime_index(frame)
    return pd.Series(data.index.year, index=data.index).astype(int)


def earnings_groups(frame: pd.DataFrame, earnings_dates: Iterable[pd.Timestamp]) -> pd.Series:
    """Create reset groups that increment at each earnings event timestamp."""
    data = _normalize_datetime_index(frame)
    if data.empty:
        return pd.Series(dtype=int, index=data.index)

    cleaned_dates = pd.to_datetime(list(earnings_dates), errors="coerce")
    cleaned_dates = cleaned_dates[~pd.isna(cleaned_dates)]
    if hasattr(cleaned_dates, "tz") and cleaned_dates.tz is not None:
        cleaned_dates = cleaned_dates.tz_convert(None)
    anchors = pd.DatetimeIndex(cleaned_dates).tz_localize(None).sort_values().unique()

    if len(anchors) == 0:
        return pd.Series(0, index=data.index, dtype=int)

    group_ids = np.searchsorted(anchors.to_numpy(), data.index.to_numpy(), side="right")
    return pd.Series(group_ids, index=data.index, dtype=int)


def proximity_distance(frame: pd.DataFrame, vwap_frame: pd.DataFrame) -> pd.Series:
    """Distance from each candle's high/low range to VWAP measured in stdev units."""
    data = _normalize_datetime_index(frame)
    stdev = vwap_frame["stdev"].replace(0, np.nan)
    raw_distance = np.minimum(
        (data["High"] - vwap_frame["vwap"]).abs(),
        (data["Low"] - vwap_frame["vwap"]).abs(),
    )
    return raw_distance / stdev


def evaluate_ticker(
    ticker: str,
    bars: pd.DataFrame,
    earnings_dates: Iterable[pd.Timestamp],
    threshold: float = 0.1,
    company_name: str | None = None,
    market_cap: int | None = None,
) -> SignalResult | None:
    """Evaluate latest candle against earnings and yearly anchored VWAP signals."""
    if bars is None or bars.empty:
        return None

    data = _normalize_datetime_index(bars).dropna(subset=["High", "Low", "Close", "Volume"])
    if data.empty:
        return None

    earnings_vwap = anchored_vwap(data, earnings_groups(data, earnings_dates))
    yearly_vwap = anchored_vwap(data, yearly_groups(data))

    earnings_distance = proximity_distance(data, earnings_vwap)
    yearly_distance = proximity_distance(data, yearly_vwap)

    last_earnings_distance = earnings_distance.iloc[-1]
    last_yearly_distance = yearly_distance.iloc[-1]

    earnings_value = (
        float(last_earnings_distance) if pd.notna(last_earnings_distance) else None
    )
    yearly_value = float(last_yearly_distance) if pd.notna(last_yearly_distance) else None

    near_earnings = earnings_value is not None and earnings_value <= threshold
    near_yearly = yearly_value is not None and yearly_value <= threshold

    return SignalResult(
        ticker=ticker,
        company_name=company_name,
        market_cap=market_cap,
        near_earnings=near_earnings,
        near_yearly=near_yearly,
        min_distance_earnings=earnings_value,
        min_distance_yearly=yearly_value,
        last_price=float(data["Close"].iloc[-1]),
    )
