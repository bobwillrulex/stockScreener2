"""NYSE-aware scheduling helpers for automated 4-hour candle scans."""

from __future__ import annotations

import calendar
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

MARKET_TIMEZONE = ZoneInfo("America/New_York")
SESSION_OPEN = time(9, 30)
SESSION_CLOSE = time(16, 0)
FOUR_HOUR_CANDLE_CLOSES = (time(13, 30), SESSION_CLOSE)


def _observed_date(month: int, day: int, year: int) -> date:
    holiday = date(year, month, day)
    if holiday.weekday() == 5:
        return holiday - timedelta(days=1)
    if holiday.weekday() == 6:
        return holiday + timedelta(days=1)
    return holiday


def _nth_weekday(year: int, month: int, weekday: int, occurrence: int) -> date:
    current = date(year, month, 1)
    days_until_weekday = (weekday - current.weekday()) % 7
    return current + timedelta(days=days_until_weekday + (occurrence - 1) * 7)


def _last_weekday(year: int, month: int, weekday: int) -> date:
    last_day = date(year, month, calendar.monthrange(year, month)[1])
    return last_day - timedelta(days=(last_day.weekday() - weekday) % 7)


def _easter_sunday(year: int) -> date:
    """Return Gregorian Easter Sunday using the Anonymous Gregorian algorithm."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def nyse_holidays(year: int) -> set[date]:
    """Return the standard full-day NYSE holidays for a year."""
    holidays = {
        _observed_date(1, 1, year),
        _nth_weekday(year, 1, calendar.MONDAY, 3),
        _nth_weekday(year, 2, calendar.MONDAY, 3),
        _easter_sunday(year) - timedelta(days=2),
        _last_weekday(year, 5, calendar.MONDAY),
        _observed_date(6, 19, year),
        _observed_date(7, 4, year),
        _nth_weekday(year, 9, calendar.MONDAY, 1),
        _nth_weekday(year, 11, calendar.THURSDAY, 4),
        _observed_date(12, 25, year),
    }
    return {holiday for holiday in holidays if holiday.year == year}


def is_nyse_trading_day(day: date) -> bool:
    """Return whether NYSE has a regular trading session on the given date."""
    return day.weekday() < 5 and day not in nyse_holidays(day.year)


def four_hour_candle_close_datetimes(day: date) -> list[datetime]:
    """Return automated scan times for completed NYSE 4-hour candles on a trading day."""
    if not is_nyse_trading_day(day):
        return []
    return [datetime.combine(day, close_time, MARKET_TIMEZONE) for close_time in FOUR_HOUR_CANDLE_CLOSES]


def next_four_hour_scan_time(now: datetime | None = None) -> datetime:
    """Return the next NYSE 4-hour candle close after ``now``."""
    current = now or datetime.now(MARKET_TIMEZONE)
    if current.tzinfo is None:
        current = current.replace(tzinfo=MARKET_TIMEZONE)
    current = current.astimezone(MARKET_TIMEZONE)

    for offset in range(366):
        day = current.date() + timedelta(days=offset)
        for scan_time in four_hour_candle_close_datetimes(day):
            if scan_time > current:
                return scan_time

    raise RuntimeError("Unable to find the next NYSE 4-hour scan time within one year")


def seconds_until_next_four_hour_scan(now: datetime | None = None) -> float:
    """Return seconds until the next automated scan should run."""
    current = now or datetime.now(MARKET_TIMEZONE)
    if current.tzinfo is None:
        current = current.replace(tzinfo=MARKET_TIMEZONE)
    current = current.astimezone(MARKET_TIMEZONE)
    return max(0.0, (next_four_hour_scan_time(current) - current).total_seconds())
