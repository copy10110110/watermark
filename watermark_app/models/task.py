import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class TaskType(StrEnum):
    EMBED = "embed"
    EXTRACT = "extract"
    DETECT = "detect"
    URL_DETECT = "url-detect"


@dataclass
class Task:
    type: TaskType
    total: int
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: TaskStatus = TaskStatus.PENDING
    progress: dict = field(default_factory=lambda: {"current": 0, "total": 0})
    results: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    stats: dict = field(default_factory=lambda: {"success": 0, "skipped": 0, "failed": 0})
    queue_position: int = 0
    download_url: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self):
        self.progress = {"current": 0, "total": self.total}

    def start(self) -> None:
        self.status = TaskStatus.RUNNING

    def pause(self) -> None:
        if self.status == TaskStatus.RUNNING:
            self.status = TaskStatus.PAUSED

    def resume(self) -> None:
        if self.status == TaskStatus.PAUSED:
            self.status = TaskStatus.RUNNING

    def complete(self, download_url: str | None = None) -> None:
        self.status = TaskStatus.COMPLETED
        self.download_url = download_url

    def cancel(self, reason: str = "user_requested") -> None:
        self.status = TaskStatus.CANCELLED

    def fail(self) -> None:
        self.status = TaskStatus.FAILED

    def advance(self, filename: str) -> None:
        self.progress["current"] += 1
        self.progress["filename"] = filename

    def add_result(self, result: dict) -> None:
        self.results.append(result)
        if result.get("status") == "success":
            self.stats["success"] += 1

    def add_error(self, filename: str, error_code: str, error_message: str) -> None:
        self.errors.append({
            "filename": filename,
            "error_code": error_code,
            "error": error_message,
        })
        self.stats["failed"] += 1

    def add_skipped(self, filename: str, reason: str) -> None:
        self.skipped.append({"filename": filename, "reason": reason})
        self.stats["skipped"] += 1

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "type": str(self.type),
            "status": str(self.status),
            "progress": self.progress,
            "results": self.results,
            "errors": self.errors,
            "skipped": self.skipped,
            "stats": self.stats,
            "queue_position": self.queue_position,
            "download_url": self.download_url,
            "created_at": self.created_at,
        }
