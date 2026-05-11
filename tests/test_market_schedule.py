from __future__ import annotations

import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from market_schedule import is_nyse_trading_day, next_four_hour_scan_time

EASTERN = ZoneInfo("America/New_York")


class MarketScheduleTests(unittest.TestCase):
    def test_next_scan_is_first_four_hour_close_during_trading_day(self) -> None:
        now = datetime(2026, 5, 11, 10, 0, tzinfo=EASTERN)

        self.assertEqual(
            next_four_hour_scan_time(now),
            datetime(2026, 5, 11, 13, 30, tzinfo=EASTERN),
        )

    def test_next_scan_uses_market_close_after_first_four_hour_close(self) -> None:
        now = datetime(2026, 5, 11, 14, 0, tzinfo=EASTERN)

        self.assertEqual(
            next_four_hour_scan_time(now),
            datetime(2026, 5, 11, 16, 0, tzinfo=EASTERN),
        )

    def test_next_scan_skips_weekend(self) -> None:
        now = datetime(2026, 5, 9, 12, 0, tzinfo=EASTERN)

        self.assertEqual(
            next_four_hour_scan_time(now),
            datetime(2026, 5, 11, 13, 30, tzinfo=EASTERN),
        )

    def test_nyse_holiday_is_not_trading_day(self) -> None:
        self.assertFalse(is_nyse_trading_day(datetime(2026, 12, 25).date()))


if __name__ == "__main__":
    unittest.main()
