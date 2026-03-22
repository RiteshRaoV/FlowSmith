from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class NodeRecord:
    """
    Represents the execution record for a single step within a flow.
    Pure data — no DB logic here.
    """
    id: str                              # auto-generated UUID
    flow_id: str                         # FK → FlowRecord.id
    step_name: str                       # matches the name passed to flow.step()
    status: str                          # PENDING | RUNNING | FAILED | COMPLETED
    input_data: Optional[Dict[str, Any]] = None
    output_data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    attempt_count: int = 0
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
