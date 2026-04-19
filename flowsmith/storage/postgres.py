import json
import uuid
from datetime import UTC, datetime
from typing import Any

from flowsmith.models import FlowRecord, NodeRecord
from flowsmith.storage.base import StorageBackend


def _now() -> datetime:
    """Always return timezone-aware UTC datetime."""
    return datetime.now(UTC)


def _to_json(data: Any) -> str | None:
    return json.dumps(data) if data is not None else None


def _from_json(data: Any) -> Any:
    if data is None:
        return None
    if isinstance(data, (dict, list)):
        return data
    return json.loads(data)


class PostgresStorage(StorageBackend):
    """
    PostgreSQL storage backend using SQLAlchemy connection pooling.

    Requires: pip install flowsmith[postgres]

    Uses SQLAlchemy's QueuePool — a thread-safe pool that maintains
    min connections alive and scales up to max under load.
    pool_pre_ping=True verifies connections before use, automatically
    handling connections dropped by the server after idle timeout.
    """

    def __init__(
        self,
        url: str,
        pool_min: int = 2,
        pool_max: int = 10,
        pool_timeout: int = 30,
    ):
        self._url = url
        self._engine = self._create_engine(url, pool_min, pool_max, pool_timeout)

    def _create_engine(self, url: str, pool_min: int, pool_max: int, pool_timeout: int) -> Any:
        try:
            from sqlalchemy import create_engine
        except ImportError as err:
            raise ImportError(
                "sqlalchemy and psycopg2 are required for PostgresStorage.\n"
                "Install with:  pip install flowsmith[postgres]"
            ) from err

        return create_engine(
            url,
            pool_size=pool_min,
            max_overflow=pool_max - pool_min,
            pool_timeout=pool_timeout,
            pool_pre_ping=True,   # validate connection before use
        )

    def _conn(self) -> Any:
        """Return a context manager yielding a SQLAlchemy connection."""
        return self._engine.connect()

    # -------------------------------------------------------------------------
    # Flow operations
    # -------------------------------------------------------------------------

    def get_flow(self, tracking_id: str) -> FlowRecord | None:
        from sqlalchemy import text
        with self._conn() as conn:
            row = conn.execute(
                text("SELECT * FROM fs_flows WHERE id = :id"),
                {"id": tracking_id}
            ).mappings().fetchone()
        return None if row is None else self._row_to_flow(row)

    def create_flow(self, tracking_id: str, name: str, input_data: dict[str, Any]) -> FlowRecord:
        from sqlalchemy import text
        now = _now()
        with self._conn() as conn:
            conn.execute(text(
                "INSERT INTO fs_flows (id, name, status, input_data, created_at, updated_at) "
                "VALUES (:id, :name, 'RUNNING', :input_data, :created_at, :updated_at)"
            ), {"id": tracking_id, "name": name, "input_data": _to_json(input_data),
                "created_at": now, "updated_at": now})
            conn.commit()
        return FlowRecord(id=tracking_id, name=name, status="RUNNING",
                          input_data=input_data, created_at=now, updated_at=now)

    def complete_flow(self, flow_id: str, output_data: dict[str, Any]) -> None:
        from sqlalchemy import text
        with self._conn() as conn:
            conn.execute(text(
                "UPDATE fs_flows SET status='COMPLETED', output_data=:output_data, "
                "updated_at=:updated_at WHERE id=:id"
            ), {"output_data": _to_json(output_data), "updated_at": _now(), "id": flow_id})
            conn.commit()

    def fail_flow(self, flow_id: str, error: str) -> None:
        from sqlalchemy import text
        with self._conn() as conn:
            conn.execute(text(
                "UPDATE fs_flows SET status='FAILED', error=:error, "
                "updated_at=:updated_at WHERE id=:id"
            ), {"error": error, "updated_at": _now(), "id": flow_id})
            conn.commit()

    # -------------------------------------------------------------------------
    # Node operations
    # -------------------------------------------------------------------------

    def get_node(self, flow_id: str, step_name: str) -> NodeRecord | None:
        from sqlalchemy import text
        with self._conn() as conn:
            row = conn.execute(text(
                "SELECT * FROM fs_nodes WHERE flow_id=:flow_id AND step_name=:step_name"
            ), {"flow_id": flow_id, "step_name": step_name}).mappings().fetchone()
        return None if row is None else self._row_to_node(row)

    def start_node(self, flow_id: str, step_name: str, input_data: dict[str, Any]) -> NodeRecord:
        from sqlalchemy import text
        now = _now()
        node_id = str(uuid.uuid4())
        with self._conn() as conn:
            row = conn.execute(text("""
                INSERT INTO fs_nodes (id, flow_id, step_name, status, input_data, attempt_count, started_at)
                VALUES (:id, :flow_id, :step_name, 'RUNNING', :input_data, 1, :started_at)
                ON CONFLICT (flow_id, step_name) DO UPDATE
                    SET status='RUNNING', input_data=EXCLUDED.input_data,
                        attempt_count=fs_nodes.attempt_count+1,
                        started_at=EXCLUDED.started_at,
                        output_data=NULL, error=NULL, ended_at=NULL
                RETURNING *
            """), {"id": node_id, "flow_id": flow_id, "step_name": step_name,
                   "input_data": _to_json(input_data), "started_at": now}).mappings().fetchone()
            conn.commit()
        return self._row_to_node(row)

    def complete_node(self, flow_id: str, step_name: str, output_data: dict[str, Any]) -> None:
        from sqlalchemy import text
        with self._conn() as conn:
            conn.execute(text(
                "UPDATE fs_nodes SET status='COMPLETED', output_data=:output_data, ended_at=:ended_at "
                "WHERE flow_id=:flow_id AND step_name=:step_name"
            ), {"output_data": _to_json(output_data), "ended_at": _now(),
                "flow_id": flow_id, "step_name": step_name})
            conn.commit()

    def fail_node(self, flow_id: str, step_name: str, error: str, attempt: int) -> None:
        from sqlalchemy import text
        with self._conn() as conn:
            conn.execute(text(
                "UPDATE fs_nodes SET status='FAILED', error=:error, "
                "attempt_count=:attempt, ended_at=:ended_at "
                "WHERE flow_id=:flow_id AND step_name=:step_name"
            ), {"error": error, "attempt": attempt, "ended_at": _now(),
                "flow_id": flow_id, "step_name": step_name})
            conn.commit()

    def get_stuck_nodes(self, timeout_seconds: int) -> list[NodeRecord]:
        from sqlalchemy import text
        with self._conn() as conn:
            rows = conn.execute(text(
                "SELECT * FROM fs_nodes WHERE status='RUNNING' "
                "AND started_at < now() - INTERVAL '1 second' * :timeout"
            ), {"timeout": timeout_seconds}).mappings().fetchall()
        return [self._row_to_node(row) for row in rows]

    # -------------------------------------------------------------------------
    # Row mappers
    # -------------------------------------------------------------------------

    def _row_to_flow(self, row: Any) -> FlowRecord:
        return FlowRecord(
            id=row["id"], name=row["name"], status=row["status"],
            input_data=_from_json(row["input_data"]),
            output_data=_from_json(row["output_data"]),
            error=row["error"], created_at=row["created_at"], updated_at=row["updated_at"],
        )

    def _row_to_node(self, row: Any) -> NodeRecord:
        return NodeRecord(
            id=row["id"], flow_id=row["flow_id"], step_name=row["step_name"],
            status=row["status"], input_data=_from_json(row["input_data"]),
            output_data=_from_json(row["output_data"]), error=row["error"],
            attempt_count=row["attempt_count"], started_at=row["started_at"],
            ended_at=row["ended_at"],
        )
