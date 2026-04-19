from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class NodeRecord:
    """
    Represents the execution record for a single step within a flow.
    Pure data — no DB logic here.
    """
    id: str
    flow_id: str
    step_name: str
    status: str
    input_data: dict[str, Any] | None = None
    output_data: dict[str, Any] | None = None
    error: str | None = None
    attempt_count: int = 0
    started_at: datetime | None = None
    ended_at: datetime | None = None
