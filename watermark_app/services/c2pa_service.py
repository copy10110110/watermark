from pathlib import Path
from PIL import Image, ExifTags


class C2paService:
    SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".tiff", ".tif"}
    _AI_SOFTWARE_KEYWORDS = [
        "dall-e", "midjourney", "stable diffusion", "novelai",
        "adobe firefly", "bing image creator", "gemini",
    ]

    def parse_exif(self, image_path: Path) -> dict:
        result = {"software": None, "artist": None, "make": None, "model": None,
            "datetime": None, "gps_lat": None, "gps_lon": None, "ai_tags": []}
        try:
            img = Image.open(image_path)
            exif_data = img._getexif()
            if exif_data:
                for tag_id, value in exif_data.items():
                    tag_name = ExifTags.TAGS.get(tag_id, str(tag_id))
                    if tag_name == "Software":
                        result["software"] = str(value)
                        for kw in self._AI_SOFTWARE_KEYWORDS:
                            if kw in str(value).lower():
                                result["ai_tags"].append(f"EXIF Software: {value}")
                    elif tag_name == "Artist":
                        result["artist"] = str(value)
                    elif tag_name == "Make":
                        result["make"] = str(value)
                    elif tag_name == "Model":
                        result["model"] = str(value)
                    elif tag_name == "DateTimeOriginal":
                        result["datetime"] = str(value)
        except Exception:
            pass
        return result

    def parse_c2pa(self, image_path: Path) -> dict | None:
        try:
            from c2pa import Reader
            reader = Reader(str(image_path))
            manifest = reader.get_manifest()
            if manifest:
                return {"has_c2pa": True, "issuer": manifest.get("issuer"),
                    "timestamp": manifest.get("timestamp"), "claims": manifest.get("claims", {})}
        except ImportError:
            pass
        except Exception:
            pass
        return None

    def is_supported(self, image_path: Path) -> bool:
        return image_path.suffix.lower() in self.SUPPORTED_EXTS
