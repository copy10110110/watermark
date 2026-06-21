from pathlib import Path
from watermark_app.models.results import EmbedResult, ExtractResult, DetectResult


def test_embed_result_success():
    r = EmbedResult(
        success=True,
        output_path=Path("img_wm.jpg"),
        elapsed_ms=1500,
    )
    assert r.to_dict()["success"] is True
    assert r.to_dict()["output"] == "img_wm.jpg"
    assert r.to_dict()["error_code"] is None


def test_embed_result_failure():
    r = EmbedResult(
        success=False, output_path=None, elapsed_ms=100,
        error_code="FORMAT_UNSUPPORTED", error_message="不支持的图片格式",
    )
    d = r.to_dict()
    assert d["success"] is False
    assert d["error_code"] == "FORMAT_UNSUPPORTED"


def test_extract_result_with_text():
    r = ExtractResult(success=True, text="机密文档-2024", confidence=0.95, elapsed_ms=800)
    d = r.to_dict()
    assert d["text"] == "机密文档-2024"
    assert d["confidence"] == 0.95


def test_extract_result_no_watermark():
    r = ExtractResult(success=False, text=None, confidence=0.0, elapsed_ms=500,
        error_code="WATERMARK_NOT_FOUND", error_message="图片中未检测到水印")
    assert r.text is None
    assert r.to_dict()["text"] is None


def test_detect_result_ai_generated():
    r = DetectResult(ai_score=0.92, verdict="likely_ai", spectral_mse=0.15,
        ring_anomaly=0.72, synthid_flag=True, c2pa_data=None, elapsed_ms=3200)
    d = r.to_dict()
    assert d["verdict"] == "likely_ai"
    assert d["ring_anomaly"] > 0.6
    assert d["synthid_flag"] is True


def test_detect_result_real():
    r = DetectResult(ai_score=0.08, verdict="likely_real", spectral_mse=0.02,
        ring_anomaly=0.1, synthid_flag=False,
        c2pa_data={"has_c2pa": True, "issuer": "Adobe"}, elapsed_ms=2800)
    d = r.to_dict()
    assert d["verdict"] == "likely_real"
    assert d["c2pa"]["has_c2pa"] is True


import uuid
from watermark_app.models.task import Task, TaskStatus, TaskType


def test_task_initial_state():
    task = Task(type=TaskType.EMBED, total=10)
    assert task.status == TaskStatus.PENDING
    assert task.progress["current"] == 0
    assert task.progress["total"] == 10
    assert isinstance(task.task_id, str)
    uuid.UUID(task.task_id)  # must not raise


def test_task_lifecycle():
    task = Task(type=TaskType.EXTRACT, total=5)
    task.start()
    assert task.status == TaskStatus.RUNNING
    task.add_result({"filename": "a.jpg", "status": "success", "output": "a_wm.jpg"})
    task.advance("a.jpg")
    assert task.progress["current"] == 1
    task.pause()
    assert task.status == TaskStatus.PAUSED
    task.resume()
    assert task.status == TaskStatus.RUNNING
    task.complete()
    assert task.status == TaskStatus.COMPLETED
    assert task.stats["success"] == 1


def test_task_cancel():
    task = Task(type=TaskType.DETECT, total=3)
    task.start()
    task.add_error("b.jpg", "FORMAT_UNSUPPORTED", "不支持的格式")
    task.cancel("user_requested")
    assert task.status == TaskStatus.CANCELLED
    assert task.stats["failed"] == 1


def test_task_add_skipped():
    task = Task(type=TaskType.EMBED, total=5)
    task.start()
    task.add_skipped("c.bmp", "unsupported_format")
    assert task.stats["skipped"] == 1


def test_task_queue_position():
    task = Task(type=TaskType.URL_DETECT, total=2)
    assert task.queue_position == 0
    task.queue_position = 3
    assert task.queue_position == 3


def test_task_to_dict():
    task = Task(type=TaskType.EMBED, total=2)
    task.start()
    d = task.to_dict()
    assert d["type"] == "embed"
    assert d["status"] == "running"
    assert "created_at" in d
