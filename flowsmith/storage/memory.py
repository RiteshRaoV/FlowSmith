import uuid
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from flowsmith.models import FlowRecord, NodeRecord
from flowsmith.storage.base import StorageBackend


def _now() -> datetime:
    return datetime.now(UTC)


class InMemoryStorage(StorageBackend):
    """
    In-memory storage backend for unit tests.

    Zero infrastructure required. Behaves identically to PostgresStorage
    from the executor's perspective — same interface, same return types.

    Not thread-safe. Use one instance per test.
    """

    def __init__(self) -> None:
        self._flows: dict[str, FlowRecord] = {}
        self._nodes: dict[str, NodeRecord] = {}

    def _node_key(self, flow_id: str, step_name: str) -> str:
        return f"{flow_id}:{step_name}"

    def get_flow(self, tracking_id: str) -> FlowRecord | None:
        return deepcopy(self._flows.get(tracking_id))

    def create_flow(
        self,
        tracking_id: str,
        name: str,
        input_data: dict[str, Any],
    ) -> FlowRecord:
        now = _now()
        record = FlowRecord(
            id=tracking_id,
            name=name,
            status="RUNNING",
            input_data=deepcopy(input_data),
            created_at=now,
            updated_at=now,
        )
        self._flows[tracking_id] = record
        return deepcopy(record)

    def complete_flow(self, flow_id: str, output_data: dict[str, Any]) -> None:
        record = self._flows[flow_id]
        record.status = "COMPLETED"
        record.output_data = deepcopy(output_data)
        record.updated_at = _now()

    def fail_flow(self, flow_id: str, error: str) -> None:
        record = self._flows[flow_id]
        record.status = "FAILED"
        record.error = error
        record.updated_at = _now()

    def get_node(self, flow_id: str, step_name: str) -> NodeRecord | None:
        return deepcopy(self._nodes.get(self._node_key(flow_id, step_name)))

    def start_node(
        self,
        flow_id: str,
        step_name: str,
        input_data: dict[str, Any],
    ) -> NodeRecord:
        key = self._node_key(flow_id, step_name)
        now = _now()
        existing = self._nodes.get(key)
        attempt = (existing.attempt_count + 1) if existing else 1

        record = NodeRecord(
            id=str(uuid.uuid4()),
            flow_id=flow_id,
            step_name=step_name,
            status="RUNNING",
            input_data=deepcopy(input_data),
            attempt_count=attempt,
            started_at=now,
        )
        self._nodes[key] = record
        return deepcopy(record)

    def complete_node(
        self,
        flow_id: str,
        step_name: str,
        output_data: dict[str, Any],
    ) -> None:
        record = self._nodes[self._node_key(flow_id, step_name)]
        record.status = "COMPLETED"
        record.output_data = deepcopy(output_data)
        record.ended_at = _now()

    def fail_node(
        self,
        flow_id: str,
        step_name: str,
        error: str,
        attempt: int,
    ) -> None:
        record = self._nodes[self._node_key(flow_id, step_name)]
        record.status = "FAILED"
        record.error = error
        record.attempt_count = attempt
        record.ended_at = _now()

    def get_stuck_nodes(self, timeout_seconds: int) -> list[NodeRecord]:
        cutoff = datetime.now(UTC).timestamp() - timeout_seconds
        stuck = []
        for node in self._nodes.values():
            if node.status == "RUNNING" and node.started_at:
                started = node.started_at
                started_ts = (
                    started.timestamp()
                    if started.tzinfo is None
                    else started.astimezone(UTC).timestamp()
                )
                if started_ts < cutoff:
                    stuck.append(node)
        return stuck
