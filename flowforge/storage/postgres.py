import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from flowforge.models import FlowRecord, NodeRecord
from flowforge.storage.base import StorageBackend


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_json(data: Any) -> str:
    return json.dumps(data) if data is not None else None


def _from_json(data: Any) -> Any:
    if data is None:
        return None
    if isinstance(data, (dict, list)):
        return data
    return json.loads(data)


class PostgresStorage(StorageBackend):
    """
    PostgreSQL storage backend.
    Requires: pip install flowforge[postgres]
    """

    def __init__(self, url: str):
        self._url = url
        self._conn = None   # lazy — connect on first use

    def _get_conn(self):
        """Return connection, creating it on first call."""
        if self._conn is None:
            self._conn = self._connect()
        return self._conn

    def _connect(self):
        try:
            import psycopg2
        except ImportError:
            raise ImportError(
                "psycopg2 is required for PostgresStorage.\n"
                "Install it with:  pip install flowforge[postgres]"
            )
        conn = psycopg2.connect(self._url)
        conn.autocommit = False
        return conn

    def _cur(self):
        import psycopg2.extras
        return self._get_conn().cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    def get_flow(self, tracking_id: str) -> Optional[FlowRecord]:
        with self._cur() as cur:
            cur.execute("SELECT * FROM ff_flows WHERE id = %s", (tracking_id,))
            row = cur.fetchone()
        if row is None:
            return None
        return self._row_to_flow(row)

    def create_flow(self, tracking_id, name, input_data) -> FlowRecord:
        now = _now()
        with self._cur() as cur:
            cur.execute(
                "INSERT INTO ff_flows (id, name, status, input_data, created_at, updated_at) "
                "VALUES (%s, %s, 'RUNNING', %s, %s, %s)",
                (tracking_id, name, json.dumps(input_data), now, now)
            )
        self._get_conn().commit()
        return FlowRecord(id=tracking_id, name=name, status="RUNNING",
                          input_data=input_data, created_at=now, updated_at=now)

    def complete_flow(self, flow_id, output_data) -> None:
        with self._cur() as cur:
            cur.execute(
                "UPDATE ff_flows SET status='COMPLETED', output_data=%s, updated_at=%s WHERE id=%s",
                (json.dumps(output_data), _now(), flow_id)
            )
        self._get_conn().commit()

    def fail_flow(self, flow_id, error) -> None:
        with self._cur() as cur:
            cur.execute(
                "UPDATE ff_flows SET status='FAILED', error=%s, updated_at=%s WHERE id=%s",
                (error, _now(), flow_id)
            )
        self._get_conn().commit()

    def get_node(self, flow_id, step_name) -> Optional[NodeRecord]:
        with self._cur() as cur:
            cur.execute(
                "SELECT * FROM ff_nodes WHERE flow_id=%s AND step_name=%s",
                (flow_id, step_name)
            )
            row = cur.fetchone()
        if row is None:
            return None
        return self._row_to_node(row)

    def start_node(self, flow_id, step_name, input_data) -> NodeRecord:
        now = _now()
        node_id = str(uuid.uuid4())
        with self._cur() as cur:
            cur.execute(
                """
                INSERT INTO ff_nodes (id, flow_id, step_name, status, input_data, attempt_count, started_at)
                VALUES (%s, %s, %s, 'RUNNING', %s, 1, %s)
                ON CONFLICT (flow_id, step_name) DO UPDATE
                    SET status='RUNNING', input_data=EXCLUDED.input_data,
                        attempt_count=ff_nodes.attempt_count+1,
                        started_at=EXCLUDED.started_at,
                        output_data=NULL, error=NULL, ended_at=NULL
                RETURNING *
                """,
                (node_id, flow_id, step_name, json.dumps(input_data), now)
            )
            row = cur.fetchone()
        self._get_conn().commit()
        return self._row_to_node(row)

    def complete_node(self, flow_id, step_name, output_data) -> None:
        with self._cur() as cur:
            cur.execute(
                "UPDATE ff_nodes SET status='COMPLETED', output_data=%s, ended_at=%s "
                "WHERE flow_id=%s AND step_name=%s",
                (json.dumps(output_data), _now(), flow_id, step_name)
            )
        self._get_conn().commit()

    def fail_node(self, flow_id, step_name, error, attempt) -> None:
        with self._cur() as cur:
            cur.execute(
                "UPDATE ff_nodes SET status='FAILED', error=%s, attempt_count=%s, ended_at=%s "
                "WHERE flow_id=%s AND step_name=%s",
                (error, attempt, _now(), flow_id, step_name)
            )
        self._get_conn().commit()

    def get_stuck_nodes(self, timeout_seconds: int):
        with self._cur() as cur:
            cur.execute(
                "SELECT * FROM ff_nodes WHERE status='RUNNING' "
                "AND started_at < now() - INTERVAL '%s seconds'",
                (timeout_seconds,)
            )
            rows = cur.fetchall()
        return [self._row_to_node(row) for row in rows]

    def _row_to_flow(self, row) -> FlowRecord:
        return FlowRecord(id=row["id"], name=row["name"], status=row["status"],
                          input_data=_from_json(row["input_data"]),
                          output_data=_from_json(row["output_data"]),
                          error=row["error"], created_at=row["created_at"],
                          updated_at=row["updated_at"])

    def _row_to_node(self, row) -> NodeRecord:
        return NodeRecord(id=row["id"], flow_id=row["flow_id"], step_name=row["step_name"],
                          status=row["status"], input_data=_from_json(row["input_data"]),
                          output_data=_from_json(row["output_data"]), error=row["error"],
                          attempt_count=row["attempt_count"], started_at=row["started_at"],
                          ended_at=row["ended_at"])
