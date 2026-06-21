import numpy as np
from pathlib import Path

BASELINE_PATH = Path(__file__).parent.parent.parent / "watermark_tools" / "spai-main" / "data" / "baseline_features.npz"


class RingDetector:
    def __init__(self, baseline_path: Path | None = None):
        self._baseline_energies: list[float] = []
        self._baseline_stds: list[float] = []
        self.baseline_loaded = False
        if baseline_path is None:
            baseline_path = BASELINE_PATH
        if baseline_path.exists():
            self._load_baseline(baseline_path)

    def detect(self, frequency_spectrum: np.ndarray) -> float:
        if not self.baseline_loaded:
            return 0.0
        rings = [
            self._compute_ring_energy(frequency_spectrum, radius=20, width=8),
            self._compute_ring_energy(frequency_spectrum, radius=64, width=16),
            self._compute_ring_energy(frequency_spectrum, radius=108, width=20),
        ]
        return self._calc_anomaly(rings)

    def _compute_ring_energy(self, spectrum: np.ndarray, radius: int, width: int) -> float:
        h, w = spectrum.shape
        cy, cx = h // 2, w // 2
        y, x = np.ogrid[:h, :w]
        dist = np.sqrt((y - cy) ** 2 + (x - cx) ** 2)
        inner = radius - width // 2
        outer = radius + width // 2
        mask = (dist >= inner) & (dist < outer)
        ring_values = spectrum[mask]
        if len(ring_values) == 0:
            return 0.0
        return float(np.mean(np.abs(ring_values)))

    def _calc_anomaly(self, energies: list[float]) -> float:
        z_scores = []
        for e, baseline, std in zip(energies, self._baseline_energies, self._baseline_stds):
            z = abs(e - baseline) / std if std > 0 else 0.0
            z_scores.append(z)
        mean_z = float(np.mean(z_scores))
        return float(1.0 / (1.0 + np.exp(-(mean_z - 1.96))))

    def _load_baseline(self, path: Path) -> None:
        data = np.load(path)
        self._baseline_energies = data["energies"].tolist()
        self._baseline_stds = data["stds"].tolist()
        self.baseline_loaded = True
