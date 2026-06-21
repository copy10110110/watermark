# tests/test_config.py
import pytest
from watermark_app.config import Config, load_config


def test_load_default_config():
    """默认配置加载：所有字段有默认值"""
    config = Config()
    assert config.chrome_path is None
    assert config.upload_max_size_mb == 500
    assert config.max_files_per_batch == 1000
    assert config.log_level == "INFO"
    assert config.log_retention_days == 7
    assert config.embed_strength == 0.8
    assert config.embed_domain == "dwt"
    assert config.watermark_timeout_embed_sec == 60
    assert config.watermark_timeout_extract_sec == 30
    assert config.opencli_timeout_nav_sec == 30
    assert config.opencli_timeout_download_sec == 10
    assert config.opencli_timeout_total_min == 5
    assert config.embed_concurrency > 0
    assert config.extract_concurrency > 0
    assert config.detect_concurrency == 1
    assert config.url_detect_concurrency == 1


def test_config_from_yaml(tmp_path):
    """从 YAML 文件加载配置，覆盖默认值"""
    yaml_content = """
chrome_path: "E:\\\\custom_chrome"
upload_max_size_mb: 200
log_level: "DEBUG"
"""
    yaml_file = tmp_path / "config.yaml"
    yaml_file.write_text(yaml_content)
    config = Config.from_yaml(yaml_file)
    assert config.chrome_path == "E:\\custom_chrome"
    assert config.upload_max_size_mb == 200
    assert config.log_level == "DEBUG"
    assert config.max_files_per_batch == 1000


def test_config_env_override(monkeypatch):
    """环境变量覆盖 YAML 配置"""
    monkeypatch.setenv("WATERMARK_LOG_LEVEL", "WARNING")
    monkeypatch.setenv("WATERMARK_CHROME_PATH", "E:\\env_chrome")
    config = Config()
    config.apply_env_overrides()
    assert config.log_level == "WARNING"
    assert config.chrome_path == "E:\\env_chrome"
