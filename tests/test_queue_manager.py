import asyncio
import pytest
from watermark_app.queue.manager import TaskQueueManager
from watermark_app.models.task import Task, TaskType, TaskStatus


class TestTaskQueueManager:
    @pytest.mark.asyncio
    async def test_submit_task(self):
        mgr = TaskQueueManager()
        task = Task(type=TaskType.EMBED, total=5)
        await mgr.submit(task)
        stored = mgr.get_task(task.task_id)
        assert stored is not None
        assert stored.status == TaskStatus.PENDING

    @pytest.mark.asyncio
    async def test_independent_queues(self):
        mgr = TaskQueueManager()
        embed_task = Task(type=TaskType.EMBED, total=10)
        extract_task = Task(type=TaskType.EXTRACT, total=3)
        await mgr.submit(embed_task)
        await mgr.submit(extract_task)
        assert mgr.get_queue_length(TaskType.EMBED) >= 0
        assert mgr.get_queue_length(TaskType.EXTRACT) >= 0

    @pytest.mark.asyncio
    async def test_get_queue_length(self):
        mgr = TaskQueueManager()
        for _ in range(3):
            await mgr.submit(Task(type=TaskType.EMBED, total=1))
        assert mgr.get_queue_length(TaskType.EMBED) == 3

    @pytest.mark.asyncio
    async def test_cancel_task(self):
        mgr = TaskQueueManager()
        task = Task(type=TaskType.DETECT, total=5)
        await mgr.submit(task)
        success = await mgr.cancel(task.task_id)
        assert success is True
        updated = mgr.get_task(task.task_id)
        assert updated.status == TaskStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_pause_resume_task(self):
        mgr = TaskQueueManager()
        task = Task(type=TaskType.EMBED, total=5)
        await mgr.submit(task)
        task.start()
        await mgr.pause(task.task_id)
        assert mgr.get_task(task.task_id).status == TaskStatus.PAUSED
        await mgr.resume(task.task_id)
        assert mgr.get_task(task.task_id).status == TaskStatus.RUNNING

    @pytest.mark.asyncio
    async def test_list_tasks(self):
        mgr = TaskQueueManager()
        await mgr.submit(Task(type=TaskType.EMBED, total=1))
        await mgr.submit(Task(type=TaskType.EXTRACT, total=1))
        tasks = mgr.list_tasks()
        assert len(tasks) == 2
