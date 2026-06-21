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


class TestBaseAPI:
    @pytest.mark.asyncio
    async def test_root_returns_html(self, client):
        resp = await client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    @pytest.mark.asyncio
    async def test_task_status_not_found(self, client):
        resp = await client.get("/api/task/nonexistent/status")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_health_check(self, client):
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
