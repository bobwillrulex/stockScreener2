from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import app


class ScanRouteTests(unittest.TestCase):
    def test_scan_route_returns_results_and_database_status(self) -> None:
        persisted_scan = Mock()
        persisted_scan.as_dict.return_value = {
            "run_id": 1,
            "previous_database_found": True,
            "new_tickers": ["NVDA"],
            "new_results": [{"ticker": "NVDA"}],
            "message": "Found 1 new ticker(s) compared with the previous scan.",
        }

        with app.app.test_client() as client, patch.object(
            app,
            "run_scan",
            return_value=[{"ticker": "NVDA"}],
        ) as run_scan, patch.object(
            app,
            "persist_scan_results",
            return_value=persisted_scan,
        ) as persist_scan_results:
            response = client.post("/scan", json={"threshold": 0.2, "max_workers": 2})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {
                "results": [{"ticker": "NVDA"}],
                "scan_database": {
                    "run_id": 1,
                    "previous_database_found": True,
                    "new_tickers": ["NVDA"],
                    "new_results": [{"ticker": "NVDA"}],
                    "message": "Found 1 new ticker(s) compared with the previous scan.",
                },
            },
        )
        run_scan.assert_called_once_with(threshold=0.2, max_workers=2)
        persist_scan_results.assert_called_once_with([{"ticker": "NVDA"}])


if __name__ == "__main__":
    unittest.main()
