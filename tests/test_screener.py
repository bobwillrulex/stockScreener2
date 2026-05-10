from __future__ import annotations

import unittest
from unittest.mock import patch

import screener
from strategy import SignalResult


class ScreenerRankingTests(unittest.TestCase):
    def test_run_scan_defaults_to_largest_market_cap_first(self) -> None:
        results_by_ticker = {
            "SMALL": SignalResult(
                ticker="SMALL",
                company_name="Small Co.",
                market_cap=100,
                near_earnings=True,
                near_yearly=False,
                min_distance_earnings=0.05,
                min_distance_yearly=0.5,
                last_price=10,
            ),
            "LARGE": SignalResult(
                ticker="LARGE",
                company_name="Large Co.",
                market_cap=1000,
                near_earnings=False,
                near_yearly=True,
                min_distance_earnings=0.5,
                min_distance_yearly=0.05,
                last_price=100,
            ),
            "UNKNOWN": SignalResult(
                ticker="UNKNOWN",
                company_name=None,
                market_cap=None,
                near_earnings=True,
                near_yearly=False,
                min_distance_earnings=0.01,
                min_distance_yearly=0.5,
                last_price=20,
            ),
        }

        with patch.object(
            screener,
            "scan_ticker",
            side_effect=lambda ticker, threshold: results_by_ticker[ticker],
        ):
            ranked = screener.run_scan(tickers=["SMALL", "UNKNOWN", "LARGE"], max_workers=1)

        self.assertEqual(
            [row["ticker"] for row in ranked],
            ["LARGE", "SMALL", "UNKNOWN"],
        )


if __name__ == "__main__":
    unittest.main()
