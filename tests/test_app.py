from __future__ import annotations

import unittest
from unittest.mock import patch

import app


class ScanRouteTests(unittest.TestCase):
    def test_scan_route_returns_results_and_database_status(self) -> None:
        scan_payload = {
            "results": [{"ticker": "NVDA"}],
            "scan_database": {
                "run_id": 1,
                "created_at": "2026-05-11T16:00:00+00:00",
                "result_count": 1,
                "previous_database_found": True,
                "new_tickers": ["NVDA"],
                "new_results": [{"ticker": "NVDA"}],
                "message": "Found 1 new ticker(s) compared with the previous scan.",
            },
        }

        with app.app.test_client() as client, patch.object(
            app,
            "execute_scan",
            return_value=scan_payload,
        ) as execute_scan:
            response = client.post("/scan", json={"threshold": 0.2, "max_workers": 2})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), scan_payload)
        execute_scan.assert_called_once_with(threshold=0.2, max_workers=2)

    def test_scan_status_route_returns_runtime_snapshot(self) -> None:
        with app.app.test_client() as client, patch.object(
            app.STATE,
            "snapshot",
            return_value={"is_running": False, "next_scheduled_scan_at": None},
        ) as snapshot:
            response = client.get("/scan/status")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"is_running": False, "next_scheduled_scan_at": None})
        snapshot.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
