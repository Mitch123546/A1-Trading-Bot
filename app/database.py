import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.models import TradingSettings


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._lock, self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS app_settings (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS bot_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    paused INTEGER NOT NULL DEFAULT 1,
                    emergency_stop INTEGER NOT NULL DEFAULT 0,
                    last_cycle_at TEXT,
                    last_error TEXT,
                    halt_reason TEXT,
                    baseline_account_equity REAL,
                    day_start_account_equity REAL,
                    day_key TEXT,
                    peak_virtual_equity REAL
                );
                CREATE TABLE IF NOT EXISTS equity_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    equity REAL NOT NULL,
                    virtual_equity REAL NOT NULL,
                    cash REAL NOT NULL,
                    buying_power REAL NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    action TEXT NOT NULL,
                    score REAL NOT NULL,
                    price REAL NOT NULL,
                    stop_price REAL,
                    target_price REAL,
                    explanation TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS trade_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT,
                    event_type TEXT NOT NULL,
                    side TEXT,
                    quantity REAL,
                    notional REAL,
                    price REAL,
                    message TEXT NOT NULL,
                    broker_order_id TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS managed_positions (
                    symbol TEXT PRIMARY KEY,
                    entry_price REAL NOT NULL,
                    stop_price REAL NOT NULL,
                    target_price REAL NOT NULL,
                    opened_at TEXT NOT NULL
                );
                """
            )
            db.execute(
                "INSERT OR IGNORE INTO app_settings(id, value, updated_at) VALUES(1, ?, ?)",
                (TradingSettings().model_dump_json(), utc_now()),
            )
            db.execute("INSERT OR IGNORE INTO bot_state(id, paused) VALUES(1, 1)")

    def get_settings(self) -> TradingSettings:
        with self.connect() as db:
            row = db.execute("SELECT value FROM app_settings WHERE id=1").fetchone()
        return TradingSettings.model_validate_json(row["value"])

    def save_settings(self, settings: TradingSettings) -> None:
        with self._lock, self.connect() as db:
            db.execute(
                "UPDATE app_settings SET value=?, updated_at=? WHERE id=1",
                (settings.model_dump_json(), utc_now()),
            )

    def get_state(self) -> dict[str, Any]:
        with self.connect() as db:
            row = db.execute("SELECT * FROM bot_state WHERE id=1").fetchone()
        result = dict(row)
        result["paused"] = bool(result["paused"])
        result["emergency_stop"] = bool(result["emergency_stop"])
        return result

    def update_state(self, **values: Any) -> None:
        allowed = {
            "paused",
            "emergency_stop",
            "last_cycle_at",
            "last_error",
            "halt_reason",
            "baseline_account_equity",
            "day_start_account_equity",
            "day_key",
            "peak_virtual_equity",
        }
        unknown = set(values) - allowed
        if unknown:
            raise ValueError(f"Unknown state fields: {unknown}")
        assignments = ", ".join(f"{key}=?" for key in values)
        data = [int(value) if isinstance(value, bool) else value for value in values.values()]
        with self._lock, self.connect() as db:
            db.execute(f"UPDATE bot_state SET {assignments} WHERE id=1", data)

    def add_equity_snapshot(
        self, equity: float, virtual_equity: float, cash: float, buying_power: float
    ) -> None:
        with self._lock, self.connect() as db:
            db.execute(
                """INSERT INTO equity_snapshots
                   (equity, virtual_equity, cash, buying_power, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (equity, virtual_equity, cash, buying_power, utc_now()),
            )

    def add_signal(self, signal: Any) -> None:
        with self._lock, self.connect() as db:
            db.execute(
                """INSERT INTO signals
                   (symbol, action, score, price, stop_price, target_price, explanation, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    signal.symbol,
                    signal.action,
                    signal.score,
                    signal.price,
                    signal.stop_price,
                    signal.target_price,
                    signal.explanation,
                    utc_now(),
                ),
            )

    def add_event(
        self,
        event_type: str,
        message: str,
        symbol: str | None = None,
        side: str | None = None,
        quantity: float | None = None,
        notional: float | None = None,
        price: float | None = None,
        broker_order_id: str | None = None,
    ) -> None:
        with self._lock, self.connect() as db:
            db.execute(
                """INSERT INTO trade_events
                   (symbol, event_type, side, quantity, notional, price, message,
                    broker_order_id, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    symbol,
                    event_type,
                    side,
                    quantity,
                    notional,
                    price,
                    message,
                    broker_order_id,
                    utc_now(),
                ),
            )

    def manage_position(self, symbol: str, entry: float, stop: float, target: float) -> None:
        with self._lock, self.connect() as db:
            db.execute(
                """INSERT INTO managed_positions(
                       symbol, entry_price, stop_price, target_price, opened_at
                   )
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(symbol) DO UPDATE SET entry_price=excluded.entry_price,
                     stop_price=excluded.stop_price, target_price=excluded.target_price,
                     opened_at=excluded.opened_at""",
                (symbol, entry, stop, target, utc_now()),
            )

    def remove_managed_position(self, symbol: str) -> None:
        with self._lock, self.connect() as db:
            db.execute("DELETE FROM managed_positions WHERE symbol=?", (symbol,))

    def managed_positions(self) -> dict[str, dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM managed_positions").fetchall()
        return {row["symbol"]: dict(row) for row in rows}

    def recent_rows(self, table: str, limit: int = 100) -> list[dict[str, Any]]:
        allowed = {"equity_snapshots", "signals", "trade_events"}
        if table not in allowed:
            raise ValueError("Table is not available")
        with self.connect() as db:
            rows = db.execute(
                f"SELECT * FROM {table} ORDER BY id DESC LIMIT ?", (min(limit, 500),)
            ).fetchall()
        return [dict(row) for row in rows]

    def rows_between(self, table: str, start: str, end: str) -> list[dict[str, Any]]:
        allowed = {"equity_snapshots", "trade_events"}
        if table not in allowed:
            raise ValueError("Table is not available")
        with self.connect() as db:
            rows = db.execute(
                f"""SELECT * FROM {table}
                    WHERE created_at >= ? AND created_at < ? ORDER BY created_at""",
                (start, end),
            ).fetchall()
        return [dict(row) for row in rows]


def dump_public_settings(settings: TradingSettings) -> dict[str, Any]:
    return json.loads(settings.model_dump_json())
