"""SQLite persistence for stock screener scan results."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from data_loader import DATA_CACHE_DIR

SCAN_DATABASE = DATA_CACHE_DIR / "scan_results.sqlite3"


@dataclass(frozen=True)
class PersistedScan:
    """Result of saving one scan and comparing it to the previous stored scan."""

    database_path: Path
    run_id: int
    previous_database_found: bool
    new_tickers: list[str]

    @property
    def message(self) -> str:
        """Human-readable persistence status for API/UI callers."""
        if not self.previous_database_found:
            return "No previous database found. Created a new scan database."
        if self.new_tickers:
            return f"Found {len(self.new_tickers)} new ticker(s) compared with the previous scan."
        return "No new tickers found compared with the previous scan."

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return {
            "database_path": str(self.database_path),
            "run_id": self.run_id,
            "previous_database_found": self.previous_database_found,
            "new_tickers": self.new_tickers,
            "message": self.message,
        }


def _connect(database_path: Path) -> sqlite3.Connection:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    return connection


def _initialize(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS scan_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            result_count INTEGER NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS scan_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            ticker TEXT NOT NULL,
            company_name TEXT,
            market_cap INTEGER,
            near_earnings INTEGER NOT NULL,
            near_yearly INTEGER NOT NULL,
            min_distance_earnings REAL,
            min_distance_yearly REAL,
            distance_score REAL,
            last_price REAL,
            payload_json TEXT NOT NULL,
            FOREIGN KEY (run_id) REFERENCES scan_runs (id) ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_scan_results_run_ticker ON scan_results (run_id, ticker)"
    )


def _latest_run_id(connection: sqlite3.Connection) -> int | None:
    row = connection.execute("SELECT MAX(id) AS run_id FROM scan_runs").fetchone()
    run_id = row["run_id"] if row is not None else None
    return int(run_id) if run_id is not None else None


def _tickers_for_run(connection: sqlite3.Connection, run_id: int) -> set[str]:
    rows = connection.execute(
        "SELECT ticker FROM scan_results WHERE run_id = ?",
        (run_id,),
    ).fetchall()
    return {str(row["ticker"]).upper() for row in rows}


def _normalize_ticker(value: object) -> str:
    return str(value or "").strip().upper()


def _insert_result(connection: sqlite3.Connection, run_id: int, row: dict[str, Any]) -> None:
    connection.execute(
        """
        INSERT INTO scan_results (
            run_id,
            ticker,
            company_name,
            market_cap,
            near_earnings,
            near_yearly,
            min_distance_earnings,
            min_distance_yearly,
            distance_score,
            last_price,
            payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            _normalize_ticker(row.get("ticker")),
            row.get("company_name"),
            row.get("market_cap"),
            int(bool(row.get("near_earnings"))),
            int(bool(row.get("near_yearly"))),
            row.get("min_distance_earnings"),
            row.get("min_distance_yearly"),
            row.get("distance_score"),
            row.get("last_price"),
            json.dumps(row, sort_keys=True),
        ),
    )


def persist_scan_results(
    results: Iterable[dict[str, Any]],
    database_path: Path = SCAN_DATABASE,
) -> PersistedScan:
    """Store scan results and identify tickers absent from the previous stored scan."""
    normalized_results = [dict(row, ticker=_normalize_ticker(row.get("ticker"))) for row in results]

    with _connect(database_path) as connection:
        _initialize(connection)
        previous_run_id = _latest_run_id(connection)
        previous_tickers = _tickers_for_run(connection, previous_run_id) if previous_run_id else set()
        current_tickers = list(
            dict.fromkeys(row["ticker"] for row in normalized_results if row["ticker"])
        )
        current_ticker_set = set(current_tickers)
        new_tickers = (
            [ticker for ticker in current_tickers if ticker not in previous_tickers]
            if previous_run_id is not None
            else []
        )

        cursor = connection.execute(
            "INSERT INTO scan_runs (created_at, result_count) VALUES (?, ?)",
            (datetime.now(UTC).isoformat(timespec="seconds"), len(current_ticker_set)),
        )
        run_id = int(cursor.lastrowid)
        for row in normalized_results:
            if row["ticker"]:
                _insert_result(connection, run_id, row)
        connection.commit()

    return PersistedScan(
        database_path=database_path,
        run_id=run_id,
        previous_database_found=previous_run_id is not None,
        new_tickers=new_tickers,
    )
