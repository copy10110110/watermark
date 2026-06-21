import tempfile
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, Form, Request
from fastapi.responses import JSONResponse, FileResponse
import shutil

from watermark_app.models.task import Task, TaskType
from watermark_app.services.watermark_service import WatermarkService

router = APIRouter(prefix="/api", tags=["embed"])

OUTPUT_BASE = Path("outputs")  # 项目根目录下的 outputs/


@router.post("/embed")
async def embed_watermark(
    request: Request,
    files: list[UploadFile] = File(...),
    text: str = Form(""),
    mode: str = Form("uniform"),
):
    if not files:
        return JSONResponse({"error": "请至少选择一张图片"}, status_code=400)

    config = request.app.state.config
    task = Task(type=TaskType.EMBED, total=len(files))

    tmp_dir = Path(tempfile.mkdtemp(prefix="wm_upload_"))
    saved_paths = []
    for f in files:
        content = await f.read()
        if len(content) > config.upload_max_size_mb * 1024 * 1024:
            task.add_skipped(f.filename or "unknown", "file_too_large")
            continue
        path = tmp_dir / (f.filename or "unknown.jpg")
        path.write_bytes(content)
        saved_paths.append(path)

    task.progress["total"] = len(saved_paths)
    await request.app.state.queue_manager.submit(task)

    output_dir = OUTPUT_BASE / task.task_id
    output_dir.mkdir(parents=True, exist_ok=True)
    svc = WatermarkService(strength=config.embed_strength, domain=config.embed_domain)
    task.start()

    for img_path in saved_paths:
        mgr = request.app.state.queue_manager
        if mgr.is_cancelled(task.task_id):
            break
        await mgr.wait_if_paused(task.task_id)
        result = svc.embed(img_path, text, output_dir)
        if result.success:
            task.add_result(result.to_dict())
        else:
            task.add_error(img_path.name, result.error_code or "UNKNOWN", result.error_message or "")
        task.advance(img_path.name)

    task.complete(download_url=f"/api/download/{task.task_id}")
    return JSONResponse(task.to_dict(), status_code=200)
