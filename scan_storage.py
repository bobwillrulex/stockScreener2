"""SQLite persistence for stock screener scan results."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
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
    created_at: str
    result_count: int
    previous_database_found: bool
    new_tickers: list[str]
    new_results: list[dict[str, Any]]

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
            "created_at": self.created_at,
            "result_count": self.result_count,
            "previous_database_found": self.previous_database_found,
            "new_tickers": self.new_tickers,
            "new_results": self.new_results,
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
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS scan_new_tickers (
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
        "CREATE INDEX IF NOT EXISTS idx_scan_new_tickers_run_ticker ON scan_new_tickers (run_id, ticker)"
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


def _insert_result(
    connection: sqlite3.Connection,
    run_id: int,
    row: dict[str, Any],
    table_name: str = "scan_results",
) -> None:
    if table_name not in {"scan_results", "scan_new_tickers"}:
        raise ValueError(f"Unsupported scan storage table: {table_name}")

    connection.execute(
        f"""
        INSERT INTO {table_name} (
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

    with closing(_connect(database_path)) as connection:
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
        new_ticker_set = set(new_tickers)
        new_results: list[dict[str, Any]] = []
        seen_new_tickers: set[str] = set()
        for row in normalized_results:
            ticker = row["ticker"]
            if ticker in new_ticker_set and ticker not in seen_new_tickers:
                new_results.append(row)
                seen_new_tickers.add(ticker)

        created_at = datetime.now(UTC).isoformat(timespec="seconds")
        cursor = connection.execute(
            "INSERT INTO scan_runs (created_at, result_count) VALUES (?, ?)",
            (created_at, len(current_ticker_set)),
        )
        run_id = int(cursor.lastrowid)
        stored_new_tickers: set[str] = set()
        for row in normalized_results:
            ticker = row["ticker"]
            if ticker:
                _insert_result(connection, run_id, row)
                if ticker in new_ticker_set and ticker not in stored_new_tickers:
                    _insert_result(connection, run_id, row, "scan_new_tickers")
                    stored_new_tickers.add(ticker)
        connection.commit()

    return PersistedScan(
        database_path=database_path,
        run_id=run_id,
        created_at=created_at,
        result_count=len(current_ticker_set),
        previous_database_found=previous_run_id is not None,
        new_tickers=new_tickers,
        new_results=new_results,
    )


def latest_scan_summary(database_path: Path = SCAN_DATABASE) -> dict[str, object] | None:
    """Return a JSON-serializable summary of the most recent stored scan."""
    if not database_path.exists():
        return None

    with closing(_connect(database_path)) as connection:
        _initialize(connection)
        run = connection.execute(
            "SELECT id, created_at, result_count FROM scan_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if run is None:
            return None

        new_tickers = [
            str(row["ticker"])
            for row in connection.execute(
                "SELECT ticker FROM scan_new_tickers WHERE run_id = ? ORDER BY id",
                (run["id"],),
            ).fetchall()
        ]

    message = (
        f"Found {len(new_tickers)} new ticker(s) compared with the previous scan."
        if new_tickers
        else "No new tickers found compared with the previous scan."
    )
    return {
        "database_path": str(database_path),
        "run_id": int(run["id"]),
        "created_at": str(run["created_at"]),
        "result_count": int(run["result_count"]),
        "new_tickers": new_tickers,
        "new_results": [],
        "message": message,
    }
