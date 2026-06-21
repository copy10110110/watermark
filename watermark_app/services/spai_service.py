import time
import sys
from pathlib import Path
from watermark_app.models.results import DetectResult

SPAI_PATH = Path(__file__).parent.parent.parent / "watermark_tools" / "spai-main"
if str(SPAI_PATH) not in sys.path:
    sys.path.insert(0, str(SPAI_PATH))


class SpaiService:
    def __init__(self):
        self._model = None

    def detect(self, image_path: Path) -> DetectResult:
        start = time.monotonic()
        if not image_path.exists():
            elapsed = int((time.monotonic() - start) * 1000)
            return DetectResult(ai_score=0.0, verdict="likely_real",
                spectral_mse=0.0, ring_anomaly=0.0,
                synthid_flag=False, c2pa_data=None, elapsed_ms=elapsed)
        try:
            ai_score = self._run_inference(image_path)
            verdict = self._classify(ai_score)
            elapsed = int((time.monotonic() - start) * 1000)
            return DetectResult(ai_score=ai_score, verdict=verdict,
                spectral_mse=0.0, ring_anomaly=0.0,
                synthid_flag=False, c2pa_data=None, elapsed_ms=elapsed)
        except Exception:
            elapsed = int((time.monotonic() - start) * 1000)
            return DetectResult(ai_score=0.0, verdict="likely_real",
                spectral_mse=0.0, ring_anomaly=0.0,
                synthid_flag=False, c2pa_data=None, elapsed_ms=elapsed)

    def _run_inference(self, image_path: Path) -> float:
        return 0.5

    def _classify(self, score: float) -> str:
        if score >= 0.7:
            return "likely_ai"
        elif score <= 0.3:
            return "likely_real"
        else:
            return "uncertain"
