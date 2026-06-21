import io
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from watermark_app.main import create_app


@pytest_asyncio.fixture
async def client():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestEmbedAPI:
    @pytest.mark.asyncio
    async def test_embed_single(self, client):
        files = [("files", ("test.jpg", io.BytesIO(b"\xff\xd8\xff\xe0" + b"\x00" * 1000), "image/jpeg"))]
        data = {"text": "测试水印", "mode": "uniform"}
        resp = await client.post("/api/embed", files=files, data=data)
        assert resp.status_code in (200, 202)
        result = resp.json()
        assert "task_id" in result

    @pytest.mark.asyncio
    async def test_embed_no_files(self, client):
        resp = await client.post("/api/embed", data={"text": "test", "mode": "uniform"})
        # FastAPI validation returns 422 when required File param is missing
        assert resp.status_code in (400, 422)
