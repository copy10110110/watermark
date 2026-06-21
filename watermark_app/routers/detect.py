import tempfile
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from watermark_app.models.task import Task, TaskType
from watermark_app.services.spai_service import SpaiService
from watermark_app.services.c2pa_service import C2paService


class UrlDetectRequest(BaseModel):
    urls: list[str]

router = APIRouter(prefix="/api", tags=["detect"])


@router.post("/detect")
async def detect_ai(
    request: Request,
    files: list[UploadFile] = File(...),
):
    if not files:
        return JSONResponse({"error": "请至少选择一张图片"}, status_code=400)

    task = Task(type=TaskType.DETECT, total=len(files))
    tmp_dir = Path(tempfile.mkdtemp(prefix="wm_detect_"))
    saved_paths = []
    for f in files:
        content = await f.read()
        path = tmp_dir / (f.filename or "unknown.jpg")
        path.write_bytes(content)
        saved_paths.append(path)

    await request.app.state.queue_manager.submit(task)
    spai = SpaiService()
    c2pa = C2paService()
    task.start()

    mgr = request.app.state.queue_manager
    for img_path in saved_paths:
        if mgr.is_cancelled(task.task_id):
            break
        await mgr.wait_if_paused(task.task_id)
        detect_result = spai.detect(img_path)
        c2pa_data = c2pa.parse_c2pa(img_path) or c2pa.parse_exif(img_path)
        detect_result.c2pa_data = c2pa_data
        task.add_result(detect_result.to_dict())
        task.advance(img_path.name)

    task.complete()
    return JSONResponse(task.to_dict(), status_code=200)


@router.post("/url-detect")
async def url_detect(request: Request, body: UrlDetectRequest):
    if not body.urls:
        return JSONResponse({"error": "请至少提供一个 URL"}, status_code=400)
    task = Task(type=TaskType.URL_DETECT, total=len(body.urls))
    await request.app.state.queue_manager.submit(task)
    task.start()
    task.complete()
    return JSONResponse(task.to_dict(), status_code=202)
