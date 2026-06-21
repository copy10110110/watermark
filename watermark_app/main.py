import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader

from watermark_app.config import load_config
from watermark_app.queue.manager import TaskQueueManager

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"

# Use a plain dict-based cache to avoid Jinja2 LRUCache weakref issues on Python 3.14
_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    auto_reload=False,
    cache_size=0,
)
templates = Jinja2Templates(env=_env)


def create_app() -> FastAPI:
    app = FastAPI(title="Watermark Tool")
    config = load_config()
    app.state.config = config
    app.state.queue_manager = TaskQueueManager()

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        return templates.TemplateResponse(request, "index.html")

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    @app.get("/api/task/{task_id}/status")
    async def task_status(task_id: str):
        task = app.state.queue_manager.get_task(task_id)
        if task is None:
            return JSONResponse({"error": "task not found"}, status_code=404)
        return task.to_dict()

    @app.post("/api/task/{task_id}/cancel")
    async def cancel_task(task_id: str):
        success = await app.state.queue_manager.cancel(task_id)
        return {"success": success}

    @app.post("/api/task/{task_id}/pause")
    async def pause_task(task_id: str, action: str = "pause"):
        mgr = app.state.queue_manager
        if action == "pause":
            success = await mgr.pause(task_id)
        else:
            success = await mgr.resume(task_id)
        return {"success": success}

    return app
