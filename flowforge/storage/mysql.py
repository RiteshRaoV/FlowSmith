import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from flowforge.models import FlowRecord, NodeRecord
from flowforge.storage.base import StorageBackend


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_json(data: Any) -> Optional[str]:
    return json.dumps(data) if data is not None else None


def _from_json(data: Any) -> Any:
    if data is None:
        return None
    if isinstance(data, (dict, list)):
        return data          # mysql-connector auto-parses JSON columns
    return json.loads(data)


class MySQLStorage(StorageBackend):
    """
    MySQL 8.0+ storage backend.

    Requires: pip install flowforge[mysql]

    Uses a single mysql.connector connection — suitable for single-process
    servers. Connection pooling is a v0.3 concern.
    """

    def __init__(self, url: str):
        self._url = url
        self._conn = self._connect()

    def _connect(self):
        try:
            import mysql.connector
        except ImportError:
            raise ImportError(
                "mysql-connector-python is required for MySQLStorage.\n"
                "Install it with:  pip install flowforge[mysql]"
            )
        parsed = urlparse(self._url)
        conn = mysql.connector.connect(
            host=parsed.hostname,
            port=parsed.port or 3306,
            user=parsed.username,
            password=parsed.password,
            database=parsed.path.lstrip("/"),
            autocommit=False,
        )
        return conn

    def _cur(self):
        """Return a dictionary cursor so rows come back as dicts."""
        return self._conn.cursor(dictionary=True)

    # -------------------------------------------------------------------------
    # Flow operations
    # -------------------------------------------------------------------------

    def get_flow(self, tracking_id: str) -> Optional[FlowRecord]:
        cur = self._cur()
        cur.execute("SELECT * FROM ff_flows WHERE id = %s", (tracking_id,))
        row = cur.fetchone()
        cur.close()
        if row is None:
            return None
        return self._row_to_flow(row)

    def create_flow(
        self,
        tracking_id: str,
        name: str,
        input_data: Dict[str, Any],
    ) -> FlowRecord:
        now = _now()
        cur = self._cur()
        cur.execute(
            """
            INSERT INTO ff_flows (id, name, status, input_data, created_at, updated_at)
            VALUES (%s, %s, 'RUNNING', %s, %s, %s)
            """,
            (tracking_id, name, _to_json(input_data), now, now)
        )
        self._conn.commit()
        cur.close()
        return FlowRecord(
            id=tracking_id,
            name=name,
            status="RUNNING",
            input_data=input_data,
            created_at=now,
            updated_at=now,
        )

    def complete_flow(self, flow_id: str, output_data: Dict[str, Any]) -> None:
        cur = self._cur()
        cur.execute(
            """
            UPDATE ff_flows
            SET status = 'COMPLETED', output_data = %s, updated_at = %s
            WHERE id = %s
            """,
            (_to_json(output_data), _now(), flow_id)
        )
        self._conn.commit()
        cur.close()

    def fail_flow(self, flow_id: str, error: str) -> None:
        cur = self._cur()
        cur.execute(
            """
            UPDATE ff_flows
            SET status = 'FAILED', error = %s, updated_at = %s
            WHERE id = %s
            """,
            (error, _now(), flow_id)
        )
        self._conn.commit()
        cur.close()

    # -------------------------------------------------------------------------
    # Node operations
    # -------------------------------------------------------------------------

    def get_node(self, flow_id: str, step_name: str) -> Optional[NodeRecord]:
        cur = self._cur()
        cur.execute(
            "SELECT * FROM ff_nodes WHERE flow_id = %s AND step_name = %s",
            (flow_id, step_name)
        )
        row = cur.fetchone()
        cur.close()
        if row is None:
            return None
        return self._row_to_node(row)

    def start_node(
        self,
        flow_id: str,
        step_name: str,
        input_data: Dict[str, Any],
    ) -> NodeRecord:
        now = _now()
        node_id = str(uuid.uuid4())
        cur = self._cur()

        # MySQL upsert — ON DUPLICATE KEY UPDATE
        cur.execute(
            """
            INSERT INTO ff_nodes (id, flow_id, step_name, status, input_data, attempt_count, started_at)
            VALUES (%s, %s, %s, 'RUNNING', %s, 1, %s)
            ON DUPLICATE KEY UPDATE
                status        = 'RUNNING',
                input_data    = VALUES(input_data),
                attempt_count = attempt_count + 1,
                started_at    = VALUES(started_at),
                output_data   = NULL,
                error         = NULL,
                ended_at      = NULL
            """,
            (node_id, flow_id, step_name, _to_json(input_data), now)
        )
        self._conn.commit()

        # Fetch the upserted row
        cur.execute(
            "SELECT * FROM ff_nodes WHERE flow_id = %s AND step_name = %s",
            (flow_id, step_name)
        )
        row = cur.fetchone()
        cur.close()
        return self._row_to_node(row)

    def complete_node(
        self,
        flow_id: str,
        step_name: str,
        output_data: Dict[str, Any],
    ) -> None:
        cur = self._cur()
        cur.execute(
            """
            UPDATE ff_nodes
            SET status = 'COMPLETED', output_data = %s, ended_at = %s
            WHERE flow_id = %s AND step_name = %s
            """,
            (_to_json(output_data), _now(), flow_id, step_name)
        )
        self._conn.commit()
        cur.close()

    def fail_node(
        self,
        flow_id: str,
        step_name: str,
        error: str,
        attempt: int,
    ) -> None:
        cur = self._cur()
        cur.execute(
            """
            UPDATE ff_nodes
            SET status = 'FAILED', error = %s, attempt_count = %s, ended_at = %s
            WHERE flow_id = %s AND step_name = %s
            """,
            (error, attempt, _now(), flow_id, step_name)
        )
        self._conn.commit()
        cur.close()

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _row_to_flow(self, row: dict) -> FlowRecord:
        return FlowRecord(
            id=row["id"],
            name=row["name"],
            status=row["status"],
            input_data=_from_json(row["input_data"]),
            output_data=_from_json(row["output_data"]),
            error=row["error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _row_to_node(self, row: dict) -> NodeRecord:
        return NodeRecord(
            id=row["id"],
            flow_id=row["flow_id"],
            step_name=row["step_name"],
            status=row["status"],
            input_data=_from_json(row["input_data"]),
            output_data=_from_json(row["output_data"]),
            error=row["error"],
            attempt_count=row["attempt_count"],
            started_at=row["started_at"],
            ended_at=row["ended_at"],
        )

    def get_stuck_nodes(self, timeout_seconds: int):
        cur = self._cur()
        cur.execute(
            """
            SELECT * FROM ff_nodes
            WHERE status = 'RUNNING'
              AND started_at < NOW() - INTERVAL %s SECOND
            """,
            (timeout_seconds,)
        )
        rows = cur.fetchall()
        cur.close()
        return [self._row_to_node(row) for row in rows]
