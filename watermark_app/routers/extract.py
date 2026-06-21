import tempfile
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, Request
from fastapi.responses import JSONResponse

from watermark_app.models.task import Task, TaskType
from watermark_app.services.watermark_service import WatermarkService

router = APIRouter(prefix="/api", tags=["extract"])


@router.post("/extract")
async def extract_watermark(
    request: Request,
    files: list[UploadFile] = File(...),
):
    if not files:
        return JSONResponse({"error": "请至少选择一张图片"}, status_code=400)

    task = Task(type=TaskType.EXTRACT, total=len(files))
    tmp_dir = Path(tempfile.mkdtemp(prefix="wm_extract_"))
    saved_paths = []
    for f in files:
        content = await f.read()
        path = tmp_dir / (f.filename or "unknown.jpg")
        path.write_bytes(content)
        saved_paths.append(path)

    await request.app.state.queue_manager.submit(task)
    svc = WatermarkService()
    task.start()

    mgr = request.app.state.queue_manager
    for img_path in saved_paths:
        if mgr.is_cancelled(task.task_id):
            break
        await mgr.wait_if_paused(task.task_id)
        result = svc.extract(img_path)
        task.add_result(result.to_dict())
        task.advance(img_path.name)

    task.complete()
    return JSONResponse(task.to_dict(), status_code=200)
