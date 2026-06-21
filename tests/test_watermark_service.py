import pytest
from pathlib import Path
from watermark_app.services.watermark_service import (
    WatermarkService, SUPPORTED_EMBED_FORMATS, SUPPORTED_EXTRACT_FORMATS,
)
from watermark_app.models.errors import ErrorCode


class TestWatermarkService:
    def test_embed_single_image(self, sample_image, tmp_path):
        svc = WatermarkService()
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        result = svc.embed(sample_image, "测试水印", output_dir)
        assert result.success is True
        assert result.output_path.exists()
        assert "_wm" in result.output_path.name

    def test_extract_embedded_watermark(self, sample_image, tmp_path):
        svc = WatermarkService()
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        embed_result = svc.embed(sample_image, "Hello123", output_dir)
        assert embed_result.success
        # Use the same service instance so it has the stored wm_bit_len
        extract_result = svc.extract(embed_result.output_path)
        assert extract_result.success, f"extract failed: {extract_result.error_code} {extract_result.error_message}"
        assert extract_result.text == "Hello123", f"expected 'Hello123', got {extract_result.text!r}"
        assert extract_result.confidence > 0.5

    def test_extract_no_watermark(self, sample_image):
        svc = WatermarkService()
        result = svc.extract(sample_image)
        assert result.success is False
        # blind-watermark on clean images either raises ValueError (during hex
        # decode of all-zero bits) or produces garbled text -> WATERMARK_NOT_FOUND
        assert result.error_code == "WATERMARK_NOT_FOUND"

    def test_unsupported_format(self, tmp_path):
        svc = WatermarkService()
        svg_path = tmp_path / "test.svg"
        svg_path.write_text("<svg></svg>")
        result = svc.embed(svg_path, "test", tmp_path)
        assert result.success is False
        assert result.error_code == "FORMAT_UNSUPPORTED"

    def test_file_not_found(self, tmp_path):
        svc = WatermarkService()
        result = svc.embed(tmp_path / "nonexistent.jpg", "test", tmp_path)
        assert result.success is False
        assert result.error_code == "FILE_NOT_FOUND"

    def test_watermark_text_too_long(self, sample_image, tmp_path):
        svc = WatermarkService()
        long_text = "A" * 2000
        result = svc.embed(sample_image, long_text, tmp_path)
        assert result.success is False
        assert result.error_code == "WATERMARK_TEXT_TOO_LONG"

    def test_watermark_text_empty(self, sample_image, tmp_path):
        svc = WatermarkService()
        result = svc.embed(sample_image, "", tmp_path)
        assert result.success is False
        assert result.error_code == "WATERMARK_TEXT_EMPTY"

    def test_output_naming_collision(self, sample_image, tmp_path):
        svc = WatermarkService()
        # embed now outputs .png by default; create a collision with that name
        collision = tmp_path / "test_img_wm.png"
        collision.write_bytes(b"fake")
        result = svc.embed(sample_image, "test", tmp_path)
        assert result.success
        assert result.output_path.name == "test_img_wm_1.png"
        assert collision.read_bytes() == b"fake"

    def test_batch_embed_uniform(self, sample_images, tmp_path):
        svc = WatermarkService()
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        mapping = {p.name: "统一水印" for p in sample_images}
        results = svc.embed_batch(sample_images, mapping, output_dir)
        assert len(results) == 3
        assert all(r.success for r in results)

    def test_supported_formats(self):
        assert ".jpg" in SUPPORTED_EMBED_FORMATS
        assert ".png" in SUPPORTED_EMBED_FORMATS
        assert ".svg" not in SUPPORTED_EMBED_FORMATS
