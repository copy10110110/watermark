from pathlib import Path
from watermark_app.services.c2pa_service import C2paService


class TestC2paService:
    def test_parse_exif_basic(self, sample_image):
        svc = C2paService()
        result = svc.parse_exif(sample_image)
        assert isinstance(result, dict)
        assert "software" in result

    def test_parse_exif_with_empty(self, tmp_path):
        from PIL import Image
        img = Image.new("RGB", (100, 100))
        path = tmp_path / "ai_img.jpg"
        img.save(path)
        svc = C2paService()
        result = svc.parse_exif(path)
        assert "software" in result
        assert "ai_tags" in result

    def test_parse_c2pa_no_manifest(self, sample_image):
        svc = C2paService()
        result = svc.parse_c2pa(sample_image)
        assert result is None or result.get("has_c2pa") is False

    def test_supported_extensions(self):
        svc = C2paService()
        assert svc.is_supported(Path("test.jpg"))
        assert svc.is_supported(Path("test.png"))
        assert not svc.is_supported(Path("test.svg"))
