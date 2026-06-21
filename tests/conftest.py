import pytest
from pathlib import Path
from PIL import Image


@pytest.fixture
def sample_image(tmp_path) -> Path:
    img = Image.new("RGB", (256, 256), color=(128, 128, 128))
    path = tmp_path / "test_img.jpg"
    img.save(path, "JPEG")
    return path


@pytest.fixture
def sample_images(tmp_path) -> list[Path]:
    paths = []
    for i in range(3):
        img = Image.new("RGB", (256, 256), color=(i * 80, 100, 150))
        path = tmp_path / f"img{i:03d}.jpg"
        img.save(path, "JPEG")
        paths.append(path)
    return paths


@pytest.fixture
def sample_texts() -> list[str]:
    return ["水印-A", "水印-B", "水印-C"]
