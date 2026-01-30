import sys
from pathlib import Path

# extract.py uses bare imports (from borders import ...), so add its directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "extract_photos"))

from extract import detect_almost_uniform_borders

import numpy as np


class TestDetectAlmostUniformBorders:
    def test_uniform_black_border(self):
        # 200x300 image, all black -> borders are perfectly uniform
        frame = np.zeros((200, 300, 3), dtype=np.uint8)
        # Fill center with content
        frame[20:180, 20:280] = 128
        assert detect_almost_uniform_borders(frame)

    def test_uniform_white_border(self):
        frame = np.full((200, 300, 3), 255, dtype=np.uint8)
        frame[20:180, 20:280] = 50
        assert detect_almost_uniform_borders(frame)

    def test_noisy_border_rejected(self):
        rng = np.random.RandomState(42)
        frame = rng.randint(0, 256, (200, 300, 3), dtype=np.uint8)
        assert not detect_almost_uniform_borders(frame)

    def test_one_noisy_border_rejected(self):
        # Uniform on 3 sides, noisy on left
        frame = np.zeros((200, 300, 3), dtype=np.uint8)
        frame[20:180, 20:280] = 128
        rng = np.random.RandomState(42)
        frame[:, :5] = rng.randint(0, 256, (200, 5, 3), dtype=np.uint8)
        assert not detect_almost_uniform_borders(frame)

    def test_custom_border_width(self):
        frame = np.zeros((200, 300, 3), dtype=np.uint8)
        frame[10:190, 10:290] = 128
        assert detect_almost_uniform_borders(frame, border_width=10)

    def test_high_threshold_accepts_noisy_border(self):
        rng = np.random.RandomState(42)
        frame = rng.randint(0, 256, (200, 300, 3), dtype=np.uint8)
        # With a very high threshold, even random borders pass
        assert detect_almost_uniform_borders(frame, threshold=200)

    def test_low_threshold_rejects_slight_variation(self):
        frame = np.zeros((200, 300, 3), dtype=np.uint8)
        frame[20:180, 20:280] = 128
        # Add noticeable variation to left border
        frame[:, :5, 0] = 100
        frame[:, :5, 1] = 0
        frame[:, :5, 2] = 0
        # Default threshold=10 should reject since the grayscale std of the
        # left border alone won't be zero, but the function checks grayscale.
        # Grayscale of (100,0,0) ≈ 30, rest of borders are 0. Left border is all ~30 (uniform).
        # Actually all left border pixels are the same (100,0,0), so std=0. Let's
        # instead mix values within the border:
        frame[::2, :5] = [0, 0, 0]
        frame[1::2, :5] = [200, 200, 200]
        # Now left border alternates 0 and 200 in grayscale -> std >> 10
        assert not detect_almost_uniform_borders(frame, threshold=10)

    def test_grayscale_frame(self):
        frame = np.zeros((200, 300), dtype=np.uint8)
        frame[20:180, 20:280] = 128
        assert detect_almost_uniform_borders(frame)
