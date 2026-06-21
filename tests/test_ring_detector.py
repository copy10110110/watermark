import numpy as np
from watermark_app.services.ring_detector import RingDetector


class TestRingDetector:
    def test_initial_state(self):
        rd = RingDetector()
        assert rd.baseline_loaded is False

    def test_compute_ring_energy(self):
        rd = RingDetector()
        fake_spectrum = np.ones((256, 256), dtype=np.float32)
        energy = rd._compute_ring_energy(fake_spectrum, radius=50, width=10)
        assert energy > 0

    def test_anomaly_score_range(self):
        rd = RingDetector()
        rd._baseline_energies = [0.5, 0.3, 0.2]
        rd._baseline_stds = [0.1, 0.05, 0.05]
        rd.baseline_loaded = True
        score = rd._calc_anomaly([0.5, 0.3, 0.2])
        assert 0.0 <= score <= 1.0

    def test_obvious_anomaly(self):
        rd = RingDetector()
        rd._baseline_energies = [0.5, 0.3, 0.2]
        rd._baseline_stds = [0.05, 0.03, 0.02]
        rd.baseline_loaded = True
        score = rd._calc_anomaly([5.0, 3.0, 2.0])
        assert score > 0.6

    def test_no_baseline_loaded(self):
        rd = RingDetector()
        assert rd.detect(np.ones((256, 256))) == 0.0
