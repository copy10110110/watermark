"""Watermark Tool 应用入口"""
import uvicorn
from watermark_app.main import create_app

app = create_app()

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        log_level="info",
    )
