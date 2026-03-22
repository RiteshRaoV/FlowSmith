from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class FlowRecord:
    """
    Represents one execution instance of a workflow.
    Pure data — no DB logic here.
    """
    id: str                              # tracking_id supplied by caller
    name: str                            # workflow name e.g. "process_order"
    status: str                          # PENDING | RUNNING | FAILED | COMPLETED
    input_data: Dict[str, Any]
    output_data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
