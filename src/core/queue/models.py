"""
Queue Models - Definitions for Async Job handling.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class JobStatus(Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass
class Job:
    """Represents a background task."""

    job_id: str
    user_id: str
    task_type: str  # e.g., "crew_execution"
    payload: dict[str, Any]
    status: JobStatus = JobStatus.PENDING
    result: Any = None
    error: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: datetime | None = None
    completed_at: datetime | None = None

    @classmethod
    def create(cls, user_id: str, task_type: str, payload: dict[str, Any]) -> "Job":
        return cls(job_id=str(uuid.uuid4()), user_id=user_id, task_type=task_type, payload=payload)
