from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import data_loader


def _ticker_symbols(count: int) -> list[str]:
    symbols: list[str] = []
    for first in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        for second in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            for third in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
                symbols.append(f"{first}{second}{third}")
                if len(symbols) == count:
                    return symbols
    raise ValueError("count is too large")


class RussellTickerLoaderTests(unittest.TestCase):
    def test_normalize_ticker_rejects_wikipedia_words_and_metadata(self) -> None:
        self.assertEqual(data_loader._normalize_ticker("brk.b"), "BRK-B")
        self.assertEqual(data_loader._normalize_ticker("AAPL"), "AAPL")
        self.assertIsNone(data_loader._normalize_ticker("$LOSS"))
        self.assertIsNone(data_loader._normalize_ticker("NON-COMMERCIAL"))
        self.assertIsNone(data_loader._normalize_ticker("Cash"))
        self.assertIsNone(data_loader._normalize_ticker("TOO-LONG"))

    def test_ishares_parser_skips_disclaimer_rows_and_filters_non_tickers(self) -> None:
        csv_text = """iShares disclaimer row
more metadata
Ticker,Name,Sector
AAPL,Apple Inc.,Information Technology
BRK.B,Berkshire Hathaway Inc.,Financials
$LOSS,Not a ticker,Other
NON-COMMERCIAL,Not a ticker,Other
CASH,Cash,Other
"""
        with patch.object(data_loader, "_download_ishares_holdings_csv", return_value=csv_text):
            self.assertEqual(data_loader._fetch_tickers_from_ishares(), ["AAPL", "BRK-B"])

    def test_load_tickers_ignores_old_wikipedia_cache_and_refreshes_from_ishares(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache_path = Path(directory) / "russell1000.csv"
            stale_tickers = _ticker_symbols(data_loader.RUSSELL_MIN_TICKERS)
            cache_path.write_text(
                "ticker,source\n" + "".join(f"{ticker},wikipedia\n" for ticker in stale_tickers)
            )
            fresh_tickers = _ticker_symbols(data_loader.RUSSELL_MIN_TICKERS + 1)[1:]

            with patch.object(data_loader, "RUSSELL_CACHE", cache_path), patch.object(
                data_loader, "_fetch_tickers_from_ishares", return_value=fresh_tickers
            ):
                self.assertEqual(data_loader.load_russell1000_tickers(), fresh_tickers)
                rewritten = cache_path.read_text()

        self.assertIn("ishares", rewritten)
        self.assertNotIn("wikipedia", rewritten)

    def test_load_ticker_metadata_uses_fresh_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache_path = Path(directory) / "ticker_metadata.json"
            cache_path.write_text(
                json.dumps(
                    {
                        "AAPL": {
                            "company_name": "Apple Inc.",
                            "market_cap": 2500000000000,
                            "fetched_at": datetime.now().isoformat(),
                        }
                    }
                )
            )

            with patch.object(data_loader, "METADATA_CACHE", cache_path), patch.object(
                data_loader, "_metadata_from_yfinance"
            ) as fetch_metadata:
                metadata = data_loader.load_ticker_metadata("aapl")

        self.assertEqual(
            metadata,
            {"company_name": "Apple Inc.", "market_cap": 2500000000000},
        )
        fetch_metadata.assert_not_called()

    def test_load_ticker_metadata_refreshes_stale_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache_path = Path(directory) / "ticker_metadata.json"
            cache_path.write_text(
                json.dumps(
                    {
                        "MSFT": {
                            "company_name": "Old Name",
                            "market_cap": 1,
                            "fetched_at": "2000-01-01T00:00:00",
                        }
                    }
                )
            )

            with patch.object(data_loader, "METADATA_CACHE", cache_path), patch.object(
                data_loader,
                "_metadata_from_yfinance",
                return_value={
                    "company_name": "Microsoft Corporation",
                    "market_cap": 3000000000000,
                },
            ) as fetch_metadata:
                metadata = data_loader.load_ticker_metadata("MSFT")
                rewritten = json.loads(cache_path.read_text())

        self.assertEqual(
            metadata,
            {"company_name": "Microsoft Corporation", "market_cap": 3000000000000},
        )
        self.assertEqual(rewritten["MSFT"]["company_name"], "Microsoft Corporation")
        fetch_metadata.assert_called_once_with("MSFT")


if __name__ == "__main__":
    unittest.main()
