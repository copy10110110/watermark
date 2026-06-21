import os
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class Config:
    chrome_path: str | None = None
    upload_max_size_mb: int = 500
    max_files_per_batch: int = 1000
    log_level: str = "INFO"
    log_retention_days: int = 7
    embed_strength: float = 0.8
    embed_domain: str = "dwt"
    watermark_timeout_embed_sec: int = 60
    watermark_timeout_extract_sec: int = 30
    opencli_timeout_nav_sec: int = 30
    opencli_timeout_download_sec: int = 10
    opencli_timeout_total_min: int = 5
    embed_concurrency: int = 4
    extract_concurrency: int = 4
    detect_concurrency: int = 1
    url_detect_concurrency: int = 1

    @classmethod
    def from_yaml(cls, path: Path) -> "Config":
        if not path.exists():
            return cls()
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        valid_keys = cls.__dataclass_fields__.keys()
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)

    def apply_env_overrides(self) -> None:
        env_map = {
            "WATERMARK_CHROME_PATH": "chrome_path",
            "WATERMARK_LOG_LEVEL": "log_level",
            "WATERMARK_UPLOAD_MAX_SIZE_MB": "upload_max_size_mb",
        }
        for env_var, attr in env_map.items():
            val = os.getenv(env_var)
            if val is not None:
                if isinstance(getattr(self, attr), int):
                    setattr(self, attr, int(val))
                else:
                    setattr(self, attr, val)


def load_config(config_path: Path | None = None) -> Config:
    if config_path is None:
        config_path = Path("config.yaml")
    config = Config.from_yaml(config_path)
    config.apply_env_overrides()
    if config.embed_concurrency < 1:
        config.embed_concurrency = min(4, os.cpu_count() or 4)
    if config.extract_concurrency < 1:
        config.extract_concurrency = min(4, os.cpu_count() or 4)
    return config
