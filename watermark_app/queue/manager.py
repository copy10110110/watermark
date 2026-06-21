import asyncio
from watermark_app.models.task import Task, TaskStatus, TaskType


class TaskQueueManager:
    def __init__(self):
        self._tasks: dict[str, Task] = {}
        self._queues: dict[TaskType, asyncio.Queue] = {
            TaskType.EMBED: asyncio.Queue(),
            TaskType.EXTRACT: asyncio.Queue(),
            TaskType.DETECT: asyncio.Queue(),
            TaskType.URL_DETECT: asyncio.Queue(),
        }
        self._cancel_events: dict[str, asyncio.Event] = {}
        self._pause_events: dict[str, asyncio.Event] = {}

    async def submit(self, task: Task) -> None:
        self._tasks[task.task_id] = task
        self._cancel_events[task.task_id] = asyncio.Event()
        self._pause_events[task.task_id] = asyncio.Event()
        self._pause_events[task.task_id].set()
        await self._queues[task.type].put(task)

    def get_task(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    def list_tasks(self) -> list[Task]:
        return list(self._tasks.values())

    def get_queue_length(self, task_type: TaskType) -> int:
        return self._queues[task_type].qsize()

    async def cancel(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if task and task.status in (TaskStatus.PENDING, TaskStatus.RUNNING, TaskStatus.PAUSED):
            event = self._cancel_events.get(task_id)
            if event:
                event.set()
            task.cancel()
            return True
        return False

    async def pause(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if task and task.status == TaskStatus.RUNNING:
            event = self._pause_events.get(task_id)
            if event:
                event.clear()
            task.pause()
            return True
        return False

    async def resume(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if task and task.status == TaskStatus.PAUSED:
            event = self._pause_events.get(task_id)
            if event:
                event.set()
            task.resume()
            return True
        return False

    def is_cancelled(self, task_id: str) -> bool:
        event = self._cancel_events.get(task_id)
        return event.is_set() if event else True

    def is_paused(self, task_id: str) -> bool:
        event = self._pause_events.get(task_id)
        return not event.is_set() if event else False

    async def wait_if_paused(self, task_id: str) -> None:
        event = self._pause_events.get(task_id)
        if event:
            await event.wait()
