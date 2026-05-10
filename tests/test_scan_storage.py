from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from scan_storage import persist_scan_results


def _result(ticker: str) -> dict[str, object]:
    return {
        "ticker": ticker,
        "company_name": f"{ticker} Inc.",
        "market_cap": 100,
        "near_earnings": True,
        "near_yearly": False,
        "min_distance_earnings": 0.05,
        "min_distance_yearly": 0.50,
        "distance_score": 0.05,
        "last_price": 10.0,
    }


class ScanStorageTests(unittest.TestCase):
    def test_first_scan_creates_database_without_new_tickers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "scan_results.sqlite3"

            persisted = persist_scan_results([_result("AAPL"), _result("MSFT")], database_path)

            self.assertTrue(database_path.exists())
            self.assertFalse(persisted.previous_database_found)
            self.assertEqual(persisted.new_tickers, [])
            self.assertIn("No previous database found", persisted.message)

            with sqlite3.connect(database_path) as connection:
                run_count = connection.execute("SELECT COUNT(*) FROM scan_runs").fetchone()[0]
                result_count = connection.execute("SELECT COUNT(*) FROM scan_results").fetchone()[0]

        self.assertEqual(run_count, 1)
        self.assertEqual(result_count, 2)

    def test_next_scan_reports_only_tickers_not_in_previous_scan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "scan_results.sqlite3"

            persist_scan_results([_result("AAPL"), _result("MSFT")], database_path)
            persisted = persist_scan_results(
                [_result("MSFT"), _result("NVDA"), _result("AAPL")],
                database_path,
            )

            self.assertTrue(persisted.previous_database_found)
            self.assertEqual(persisted.new_tickers, ["NVDA"])
            self.assertIn("Found 1 new ticker", persisted.message)

            with sqlite3.connect(database_path) as connection:
                latest_run_id = connection.execute("SELECT MAX(id) FROM scan_runs").fetchone()[0]
                latest_tickers = [
                    row[0]
                    for row in connection.execute(
                        "SELECT ticker FROM scan_results WHERE run_id = ? ORDER BY id",
                        (latest_run_id,),
                    ).fetchall()
                ]

        self.assertEqual(latest_tickers, ["MSFT", "NVDA", "AAPL"])

    def test_next_scan_reports_empty_list_when_no_tickers_are_new(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "scan_results.sqlite3"

            persist_scan_results([_result("AAPL"), _result("MSFT")], database_path)
            persisted = persist_scan_results([_result("MSFT"), _result("AAPL")], database_path)

        self.assertTrue(persisted.previous_database_found)
        self.assertEqual(persisted.new_tickers, [])
        self.assertIn("No new tickers found", persisted.message)


if __name__ == "__main__":
    unittest.main()
