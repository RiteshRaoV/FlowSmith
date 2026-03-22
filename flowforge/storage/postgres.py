from typing import Any, Dict, Optional

from flowforge.models import FlowRecord, NodeRecord
from flowforge.storage.base import StorageBackend


class PostgresStorage(StorageBackend):
    """
    PostgreSQL storage backend for production use.

    Requires psycopg2:
        pip install psycopg2-binary

    Usage (via global config — preferred):
        import flowforge
        flowforge.configure(database_url="postgresql://user:pass@host/db")

    Usage (direct — for testing or override):
        from flowforge.storage import PostgresStorage
        storage = PostgresStorage(url="postgresql://user:pass@host/db")
    """

    def __init__(self, url: str):
        self._url = url
        self._conn = None  # TODO: initialise psycopg2 connection pool

    def _get_conn(self):
        # TODO: return connection from pool
        raise NotImplementedError("PostgresStorage._get_conn() not yet implemented")

    # -------------------------------------------------------------------------
    # Flow operations
    # -------------------------------------------------------------------------

    def get_flow(self, tracking_id: str) -> Optional[FlowRecord]:
        # TODO: SELECT * FROM ff_flows WHERE id = %s
        raise NotImplementedError

    def create_flow(
        self,
        tracking_id: str,
        name: str,
        input_data: Dict[str, Any],
    ) -> FlowRecord:
        # TODO: INSERT INTO ff_flows (id, name, status, input_data, created_at, updated_at)
        #       VALUES (%s, %s, 'RUNNING', %s, now(), now())
        raise NotImplementedError

    def complete_flow(self, flow_id: str, output_data: Dict[str, Any]) -> None:
        # TODO: UPDATE ff_flows SET status='COMPLETED', output_data=%s, updated_at=now()
        #       WHERE id = %s
        raise NotImplementedError

    def fail_flow(self, flow_id: str, error: str) -> None:
        # TODO: UPDATE ff_flows SET status='FAILED', error=%s, updated_at=now()
        #       WHERE id = %s
        raise NotImplementedError

    # -------------------------------------------------------------------------
    # Node operations
    # -------------------------------------------------------------------------

    def get_node(self, flow_id: str, step_name: str) -> Optional[NodeRecord]:
        # TODO: SELECT * FROM ff_nodes WHERE flow_id = %s AND step_name = %s
        raise NotImplementedError

    def start_node(
        self,
        flow_id: str,
        step_name: str,
        input_data: Dict[str, Any],
    ) -> NodeRecord:
        # TODO: INSERT INTO ff_nodes ... ON CONFLICT (flow_id, step_name)
        #       DO UPDATE SET status='RUNNING', attempt_count = ff_nodes.attempt_count + 1,
        #       started_at=now(), input_data=%s
        raise NotImplementedError

    def complete_node(
        self,
        flow_id: str,
        step_name: str,
        output_data: Dict[str, Any],
    ) -> None:
        # TODO: UPDATE ff_nodes SET status='COMPLETED', output_data=%s, ended_at=now()
        #       WHERE flow_id=%s AND step_name=%s
        raise NotImplementedError

    def fail_node(
        self,
        flow_id: str,
        step_name: str,
        error: str,
        attempt: int,
    ) -> None:
        # TODO: UPDATE ff_nodes SET status='FAILED', error=%s, attempt_count=%s, ended_at=now()
        #       WHERE flow_id=%s AND step_name=%s
        raise NotImplementedError
