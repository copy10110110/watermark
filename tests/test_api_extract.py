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


class TestExtractAPI:
    @pytest.mark.asyncio
    async def test_extract_single(self, client):
        files = [("files", ("test.jpg", io.BytesIO(b"\xff\xd8\xff\xe0" + b"\x00" * 1000), "image/jpeg"))]
        resp = await client.post("/api/extract", files=files)
        assert resp.status_code in (200, 202)

    @pytest.mark.asyncio
    async def test_extract_no_files(self, client):
        resp = await client.post("/api/extract")
        # FastAPI validation returns 422 when required File param is missing
        assert resp.status_code in (400, 422)
