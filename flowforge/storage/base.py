from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from flowforge.models import FlowRecord, NodeRecord


class StorageBackend(ABC):
    """
    Abstract interface for all FlowForge storage backends.

    Implement this to add a new backend (Redis, MongoDB, SQLite, etc.).
    All methods must be synchronous for v0.1.
    """

    # -------------------------------------------------------------------------
    # Flow operations
    # -------------------------------------------------------------------------

    @abstractmethod
    def get_flow(self, tracking_id: str) -> Optional[FlowRecord]:
        """Return the FlowRecord for the given tracking_id, or None if not found."""
        ...

    @abstractmethod
    def create_flow(
        self,
        tracking_id: str,
        name: str,
        input_data: Dict[str, Any],
    ) -> FlowRecord:
        """Insert a new flow record with status=RUNNING and return it."""
        ...

    @abstractmethod
    def complete_flow(self, flow_id: str, output_data: Dict[str, Any]) -> None:
        """Mark a flow as COMPLETED and store its final output."""
        ...

    @abstractmethod
    def fail_flow(self, flow_id: str, error: str) -> None:
        """Mark a flow as FAILED and store the error message."""
        ...

    # -------------------------------------------------------------------------
    # Node operations
    # -------------------------------------------------------------------------

    @abstractmethod
    def get_node(self, flow_id: str, step_name: str) -> Optional[NodeRecord]:
        """Return the NodeRecord for (flow_id, step_name), or None if not found."""
        ...

    @abstractmethod
    def start_node(
        self,
        flow_id: str,
        step_name: str,
        input_data: Dict[str, Any],
    ) -> NodeRecord:
        """
        Insert a new node record with status=RUNNING.
        If a node already exists for (flow_id, step_name), upsert it
        and increment attempt_count.
        """
        ...

    @abstractmethod
    def complete_node(
        self,
        flow_id: str,
        step_name: str,
        output_data: Dict[str, Any],
    ) -> None:
        """Mark a node as COMPLETED and store its output."""
        ...

    @abstractmethod
    def fail_node(
        self,
        flow_id: str,
        step_name: str,
        error: str,
        attempt: int,
    ) -> None:
        """Mark a node as FAILED and store the error + attempt count."""
        ...

    # -------------------------------------------------------------------------
    # Watchdog support
    # -------------------------------------------------------------------------

    @abstractmethod
    def get_stuck_nodes(self, timeout_seconds: int):
        """
        Return all NodeRecords that are:
          - status = RUNNING
          - started_at < now() - timeout_seconds

        Used by the Watchdog to detect crashed processes.
        """
        ...
