from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class FlowRecord:
    """
    Represents one execution instance of a workflow.
    Pure data — no DB logic here.
    """
    id: str
    name: str
    status: str
    input_data: dict[str, Any]
    output_data: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
