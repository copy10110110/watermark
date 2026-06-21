from dataclasses import dataclass
from pathlib import Path


@dataclass
class EmbedResult:
    success: bool
    output_path: Path | None
    elapsed_ms: int
    error_code: str | None = None
    error_message: str | None = None

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "output": str(self.output_path.name) if self.output_path else None,
            "elapsed_ms": self.elapsed_ms,
            "error_code": self.error_code,
            "error": self.error_message,
        }


@dataclass
class ExtractResult:
    success: bool
    text: str | None
    confidence: float
    elapsed_ms: int
    error_code: str | None = None
    error_message: str | None = None

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "text": self.text,
            "confidence": self.confidence,
            "elapsed_ms": self.elapsed_ms,
            "error_code": self.error_code,
            "error": self.error_message,
        }


@dataclass
class DetectResult:
    ai_score: float
    verdict: str
    spectral_mse: float
    ring_anomaly: float
    synthid_flag: bool
    c2pa_data: dict | None
    elapsed_ms: int

    def to_dict(self) -> dict:
        return {
            "ai_score": self.ai_score,
            "verdict": self.verdict,
            "spectral_mse": self.spectral_mse,
            "ring_anomaly": self.ring_anomaly,
            "synthid_flag": self.synthid_flag,
            "c2pa": self.c2pa_data,
            "elapsed_ms": self.elapsed_ms,
        }
