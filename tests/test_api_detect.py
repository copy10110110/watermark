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


class TestDetectAPI:
    @pytest.mark.asyncio
    async def test_detect_single(self, client):
        files = [("files", ("test.jpg", io.BytesIO(b"\xff\xd8\xff\xe0" + b"\x00" * 1000), "image/jpeg"))]
        resp = await client.post("/api/detect", files=files)
        assert resp.status_code in (200, 202)

    @pytest.mark.asyncio
    async def test_url_detect(self, client):
        resp = await client.post("/api/url-detect", json={"urls": ["https://example.com"]})
        assert resp.status_code == 202
