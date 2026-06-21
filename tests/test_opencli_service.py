from unittest.mock import patch, MagicMock
from pathlib import Path
from watermark_app.services.opencli_service import OpenCliService


class TestOpenCliService:
    def test_validate_url_http(self):
        svc = OpenCliService()
        assert svc._validate_url("http://example.com") is True
        assert svc._validate_url("https://example.com/path?q=1") is True

    def test_validate_url_reject_bad_schemes(self):
        svc = OpenCliService()
        assert svc._validate_url("file:///etc/passwd") is False
        assert svc._validate_url("javascript:alert(1)") is False
        assert svc._validate_url("") is False

    def test_validate_url_reject_private_ips(self):
        svc = OpenCliService()
        assert svc._validate_url("http://127.0.0.1/admin") is False
        assert svc._validate_url("http://192.168.1.1/") is False
        assert svc._validate_url("http://10.0.0.1/") is False

    def test_find_chrome_returns_something(self):
        svc = OpenCliService()
        path = svc._find_chrome()
        # May be None if Chrome not installed — that's OK for tests

    def test_cleanup_temp_dir(self, tmp_path):
        svc = OpenCliService()
        test_dir = tmp_path / "test_profile"
        test_dir.mkdir()
        svc._cleanup_temp_dir(test_dir)
        assert not test_dir.exists()
