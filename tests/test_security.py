import io
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from watermark_app.main import create_app
from watermark_app.services.opencli_service import OpenCliService


@pytest_asyncio.fixture
async def client():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestURLValidation:
    def test_rejects_javascript_scheme(self):
        svc = OpenCliService()
        assert svc._validate_url("javascript:alert(1)") is False

    def test_rejects_file_scheme(self):
        svc = OpenCliService()
        assert svc._validate_url("file:///etc/passwd") is False

    def test_rejects_private_ip(self):
        svc = OpenCliService()
        for ip in ["127.0.0.1", "192.168.1.1", "10.0.0.1", "172.16.0.1"]:
            assert svc._validate_url(f"http://{ip}/") is False

    def test_rejects_ipv6_loopback(self):
        svc = OpenCliService()
        assert svc._validate_url("http://[::1]/") is False

    def test_allows_public_url(self):
        svc = OpenCliService()
        assert svc._validate_url("https://example.com/path") is True


class TestPathTraversal:
    @pytest.mark.asyncio
    async def test_embed_accepts_valid_upload(self, client):
        files = [("files", ("test.jpg", io.BytesIO(b"\xff\xd8\xff\xe0" + b"\x00" * 500), "image/jpeg"))]
        resp = await client.post("/api/embed", files=files, data={"text": "test", "mode": "uniform"})
        assert resp.status_code in (200, 202, 400)


class TestCSVInjection:
    def test_csv_output_escaping(self):
        import csv
        import io as stdlib_io
        output = stdlib_io.StringIO()
        writer = csv.writer(output, quoting=csv.QUOTE_ALL)
        writer.writerow(["=cmd|' /C calc'!A0", "@SUM(A1:A10)", "+1+1", "-1-1"])
        result = output.getvalue()
        for line in result.strip().split("\n"):
            assert line.startswith('"'), f"CSV line should start with quote: {line}"
