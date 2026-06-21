from unittest.mock import patch
from pathlib import Path
from watermark_app.services.spai_service import SpaiService


class TestSpaiService:
    def test_detect_ai_likely_real(self, sample_image):
        svc = SpaiService()
        with patch.object(svc, "_run_inference", return_value=0.08):
            result = svc.detect(sample_image)
        assert result.ai_score == 0.08
        assert result.verdict == "likely_real"
        assert isinstance(result.synthid_flag, bool)
        assert result.elapsed_ms >= 0

    def test_detect_ai_likely_ai(self, sample_image):
        svc = SpaiService()
        with patch.object(svc, "_run_inference", return_value=0.92):
            result = svc.detect(sample_image)
        assert result.verdict == "likely_ai"

    def test_detect_ai_uncertain(self, sample_image):
        svc = SpaiService()
        with patch.object(svc, "_run_inference", return_value=0.55):
            result = svc.detect(sample_image)
        assert result.verdict == "uncertain"

    def test_file_not_found(self, tmp_path):
        svc = SpaiService()
        result = svc.detect(tmp_path / "nope.jpg")
        assert result.verdict == "likely_real"
        assert result.ai_score == 0.0

    def test_threshold_boundaries(self):
        svc = SpaiService()
        assert svc._classify(0.30) == "likely_real"
        assert svc._classify(0.31) == "uncertain"
        assert svc._classify(0.69) == "uncertain"
        assert svc._classify(0.70) == "likely_ai"
