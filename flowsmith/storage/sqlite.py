import json
import sqlite3
import threading
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from flowsmith.models import FlowRecord, NodeRecord
from flowsmith.storage.base import StorageBackend


def _now() -> datetime:
    """Always return timezone-aware UTC datetime."""
    return datetime.now(UTC)


def _ts(dt: datetime) -> str:
    return dt.isoformat()


def _parse_ts(value: str | None) -> datetime | None:
    return None if value is None else datetime.fromisoformat(value)


def _to_json(data: Any) -> str | None:
    return json.dumps(data) if data is not None else None


def _from_json(data: str | None) -> Any:
    return None if data is None else json.loads(data)


def sqlite_path(url: str) -> str:
    """
    Extract the database path from a sqlite:// URL.

        sqlite:///relative/path.db   -> relative/path.db
        sqlite:////absolute/path.db  -> /absolute/path.db
        sqlite:///:memory:           -> :memory:
    """
    for prefix in ("sqlite:///", "sqlite://"):
        if url.startswith(prefix):
            return url[len(prefix):] or ":memory:"
    return url


class SQLiteStorage(StorageBackend):
    """
    SQLite storage backend using the standard library sqlite3 module.

    No extra dependencies. Intended for local development, tests and
    single-process deployments. A single connection is shared and guarded
    by a lock, so it is safe to use from multiple threads (including the
    watchdog). pool_* arguments are accepted for interface parity with the
    other backends and ignored.
    """

    def __init__(
        self,
        url: str,
        pool_min: int = 2,
        pool_max: int = 10,
        pool_timeout: int = 30,
    ):
        self._url = url
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(
            sqlite_path(url),
            timeout=pool_timeout,
            check_same_thread=False,
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _execute(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        with self._lock:
            try:
                rows = self._conn.execute(sql, params).fetchall()
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
            return rows

    # -------------------------------------------------------------------------
    # Flow operations
    # -------------------------------------------------------------------------

    def get_flow(self, tracking_id: str) -> FlowRecord | None:
        rows = self._execute("SELECT * FROM fs_flows WHERE id = ?", (tracking_id,))
        return self._row_to_flow(rows[0]) if rows else None

    def create_flow(self, tracking_id: str, name: str, input_data: dict[str, Any]) -> FlowRecord:
        now = _now()
        self._execute(
            "INSERT INTO fs_flows (id, name, status, input_data, created_at, updated_at) "
            "VALUES (?, ?, 'RUNNING', ?, ?, ?)",
            (tracking_id, name, _to_json(input_data), _ts(now), _ts(now)),
        )
        return FlowRecord(id=tracking_id, name=name, status="RUNNING",
                          input_data=input_data, created_at=now, updated_at=now)

    def complete_flow(self, flow_id: str, output_data: dict[str, Any]) -> None:
        self._execute(
            "UPDATE fs_flows SET status='COMPLETED', output_data=?, updated_at=? WHERE id=?",
            (_to_json(output_data), _ts(_now()), flow_id),
        )

    def fail_flow(self, flow_id: str, error: str) -> None:
        self._execute(
            "UPDATE fs_flows SET status='FAILED', error=?, updated_at=? WHERE id=?",
            (error, _ts(_now()), flow_id),
        )

    # -------------------------------------------------------------------------
    # Node operations
    # -------------------------------------------------------------------------

    def get_node(self, flow_id: str, step_name: str) -> NodeRecord | None:
        rows = self._execute(
            "SELECT * FROM fs_nodes WHERE flow_id=? AND step_name=?",
            (flow_id, step_name),
        )
        return self._row_to_node(rows[0]) if rows else None

    def start_node(self, flow_id: str, step_name: str, input_data: dict[str, Any]) -> NodeRecord:
        with self._lock:
            self._execute(
                """
                INSERT INTO fs_nodes (id, flow_id, step_name, status, input_data, attempt_count, started_at)
                VALUES (?, ?, ?, 'RUNNING', ?, 1, ?)
                ON CONFLICT (flow_id, step_name) DO UPDATE SET
                    status='RUNNING', input_data=excluded.input_data,
                    attempt_count=attempt_count+1, started_at=excluded.started_at,
                    output_data=NULL, error=NULL, ended_at=NULL
                """,
                (str(uuid.uuid4()), flow_id, step_name, _to_json(input_data), _ts(_now())),
            )
            node = self.get_node(flow_id, step_name)
        assert node is not None
        return node

    def complete_node(self, flow_id: str, step_name: str, output_data: dict[str, Any]) -> None:
        self._execute(
            "UPDATE fs_nodes SET status='COMPLETED', output_data=?, ended_at=? "
            "WHERE flow_id=? AND step_name=?",
            (_to_json(output_data), _ts(_now()), flow_id, step_name),
        )

    def fail_node(self, flow_id: str, step_name: str, error: str, attempt: int) -> None:
        self._execute(
            "UPDATE fs_nodes SET status='FAILED', error=?, attempt_count=?, ended_at=? "
            "WHERE flow_id=? AND step_name=?",
            (error, attempt, _ts(_now()), flow_id, step_name),
        )

    def get_stuck_nodes(self, timeout_seconds: int) -> list[NodeRecord]:
        # Timestamps are stored as UTC ISO-8601 strings, which sort lexicographically.
        cutoff = _ts(_now() - timedelta(seconds=timeout_seconds))
        rows = self._execute(
            "SELECT * FROM fs_nodes WHERE status='RUNNING' AND started_at < ?",
            (cutoff,),
        )
        return [self._row_to_node(row) for row in rows]

    # -------------------------------------------------------------------------
    # Row mappers
    # -------------------------------------------------------------------------

    def _row_to_flow(self, row: sqlite3.Row) -> FlowRecord:
        return FlowRecord(
            id=row["id"], name=row["name"], status=row["status"],
            input_data=_from_json(row["input_data"]),
            output_data=_from_json(row["output_data"]),
            error=row["error"],
            created_at=_parse_ts(row["created_at"]),
            updated_at=_parse_ts(row["updated_at"]),
        )

    def _row_to_node(self, row: sqlite3.Row) -> NodeRecord:
        return NodeRecord(
            id=row["id"], flow_id=row["flow_id"], step_name=row["step_name"],
            status=row["status"], input_data=_from_json(row["input_data"]),
            output_data=_from_json(row["output_data"]), error=row["error"],
            attempt_count=row["attempt_count"],
            started_at=_parse_ts(row["started_at"]),
            ended_at=_parse_ts(row["ended_at"]),
        )
