import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from watermark_app.models.results import EmbedResult, ExtractResult
from watermark_app.models.errors import ErrorCode

SUPPORTED_EMBED_FORMATS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"}
SUPPORTED_EXTRACT_FORMATS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"}
MAX_WATERMARK_TEXT_LEN = 1024
# Default wm_shape when actual bit length is unknown (used as fallback for
# images embedded outside this service)
DEFAULT_WM_SHAPE = 512


class WatermarkService:
    def __init__(self, strength: float = 0.8, domain: str = "dwt"):
        self.strength = strength
        self.domain = domain
        # Track wm_bit length for images embedded by this service instance
        self._wm_bit_lens: dict[str, int] = {}

    def embed(self, image_path: Path, text: str, output_dir: Path) -> EmbedResult:
        start = time.monotonic()
        if not image_path.exists():
            return EmbedResult(success=False, output_path=None, elapsed_ms=0,
                error_code=ErrorCode.FILE_NOT_FOUND, error_message="文件不存在或无法读取")
        suffix = image_path.suffix.lower()
        if suffix not in SUPPORTED_EMBED_FORMATS:
            return EmbedResult(success=False, output_path=None, elapsed_ms=0,
                error_code=ErrorCode.FORMAT_UNSUPPORTED, error_message=f"不支持的图片格式: {suffix}")
        if not text:
            return EmbedResult(success=False, output_path=None, elapsed_ms=0,
                error_code=ErrorCode.WATERMARK_TEXT_EMPTY, error_message="水印文本为空")
        if len(text) > MAX_WATERMARK_TEXT_LEN:
            return EmbedResult(success=False, output_path=None, elapsed_ms=0,
                error_code=ErrorCode.WATERMARK_TEXT_TOO_LONG, error_message="水印文本过长")
        try:
            from blind_watermark import WaterMark
            wm = WaterMark(password_img=1, password_wm=1)
            wm.read_img(str(image_path))
            wm.read_wm(text, mode="str")
            # Always output as PNG (lossless) so extraction works reliably
            output_path = self._resolve_output_path(image_path, output_dir, force_png=True)
            wm.embed(str(output_path))
            elapsed = int((time.monotonic() - start) * 1000)
            # Record wm_bit length so extract() can use the correct wm_shape
            self._wm_bit_lens[output_path.name] = len(wm.wm_bit)
            return EmbedResult(success=True, output_path=output_path, elapsed_ms=elapsed)
        except Exception as e:
            elapsed = int((time.monotonic() - start) * 1000)
            return EmbedResult(success=False, output_path=None, elapsed_ms=elapsed,
                error_code=ErrorCode.INTERNAL_ERROR, error_message=str(e))

    def extract(self, image_path: Path, wm_shape: int | None = None) -> ExtractResult:
        start = time.monotonic()
        if not image_path.exists():
            return ExtractResult(success=False, text=None, confidence=0.0, elapsed_ms=0,
                error_code=ErrorCode.FILE_NOT_FOUND, error_message="文件不存在或无法读取")
        try:
            from blind_watermark import WaterMark
            wm = WaterMark(password_img=1, password_wm=1)
            # Use stored wm_bit_len if available, else fallback to provided/default
            shape = wm_shape or self._wm_bit_lens.get(image_path.name, DEFAULT_WM_SHAPE)
            text = wm.extract(str(image_path), wm_shape=shape, mode="str")
            elapsed = int((time.monotonic() - start) * 1000)
            if text and not self._is_garbled_text(text):
                return ExtractResult(success=True, text=text, confidence=0.8, elapsed_ms=elapsed)
            else:
                return ExtractResult(success=False, text=None, confidence=0.0, elapsed_ms=elapsed,
                    error_code=ErrorCode.WATERMARK_NOT_FOUND, error_message="图片中未检测到水印")
        except ValueError:
            elapsed = int((time.monotonic() - start) * 1000)
            return ExtractResult(success=False, text=None, confidence=0.0, elapsed_ms=elapsed,
                error_code=ErrorCode.WATERMARK_NOT_FOUND, error_message="图片中未检测到水印")
        except Exception as e:
            elapsed = int((time.monotonic() - start) * 1000)
            return ExtractResult(success=False, text=None, confidence=0.0, elapsed_ms=elapsed,
                error_code=ErrorCode.INTERNAL_ERROR, error_message=str(e))

    @staticmethod
    def _is_garbled_text(text: str) -> bool:
        """Check if extracted text is garbled (all replacement chars or non-printable)."""
        if not text:
            return True
        replacement_count = text.count("�")
        if replacement_count >= len(text) * 0.3:
            return True
        printable = sum(1 for c in text if c.isprintable())
        if printable < len(text) * 0.5:
            return True
        return False

    def embed_batch(self, images: list[Path], mapping: dict[str, str], output_dir: Path, concurrency: int = 4) -> list[EmbedResult]:
        results = []
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = {}
            for img in images:
                text = mapping.get(img.name, "")
                if not text:
                    results.append(EmbedResult(success=False, output_path=None, elapsed_ms=0,
                        error_code="NO_MAPPING", error_message="无对应水印文本映射"))
                    continue
                futures[pool.submit(self.embed, img, text, output_dir)] = img
            for f in as_completed(futures):
                results.append(f.result())
        return results

    def extract_batch(self, images: list[Path], concurrency: int = 4) -> list[ExtractResult]:
        results = []
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = {pool.submit(self.extract, img): img for img in images}
            for f in as_completed(futures):
                results.append(f.result())
        return results

    def _resolve_output_path(self, image_path: Path, output_dir: Path, force_png: bool = False) -> Path:
        stem = image_path.stem
        suffix = ".png" if force_png else image_path.suffix.lower()
        if suffix in (".tiff", ".tif"):
            suffix = ".png"
        base_name = f"{stem}_wm{suffix}"
        output_path = output_dir / base_name
        counter = 1
        while output_path.exists():
            output_path = output_dir / f"{stem}_wm_{counter}{suffix}"
            counter += 1
        return output_path
