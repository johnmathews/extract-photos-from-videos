import sys
from pathlib import Path

# extract.py uses bare imports (from borders import ...), so add its directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "extract_photos"))

from extract import detect_almost_uniform_borders, _is_near_uniform, _is_screenshot, _rejection_reason

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


class TestIsNearUniform:
    def test_all_black_rejected(self):
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        assert _is_near_uniform(img) is not None

    def test_all_white_rejected(self):
        img = np.full((100, 100, 3), 255, dtype=np.uint8)
        assert _is_near_uniform(img) is not None

    def test_near_black_with_noise_rejected(self):
        rng = np.random.RandomState(42)
        img = rng.randint(0, 4, (100, 100, 3), dtype=np.uint8)  # std ~1
        assert _is_near_uniform(img) is not None

    def test_photo_like_content_accepted(self):
        rng = np.random.RandomState(42)
        img = rng.randint(0, 256, (100, 100, 3), dtype=np.uint8)  # std ~74
        assert _is_near_uniform(img) is None

    def test_dark_photo_accepted(self):
        """A dark but textured photo should pass (std well above 5)."""
        rng = np.random.RandomState(42)
        img = rng.randint(10, 80, (100, 100, 3), dtype=np.uint8)  # std ~20
        assert _is_near_uniform(img) is None

    def test_grayscale_solid_rejected(self):
        img = np.full((100, 100), 128, dtype=np.uint8)
        assert _is_near_uniform(img) is not None

    def test_custom_threshold(self):
        rng = np.random.RandomState(42)
        img = rng.randint(0, 10, (100, 100, 3), dtype=np.uint8)  # grayscale std ~1.9
        # Default threshold=5.0 rejects it (std ~1.9 < 5)
        assert _is_near_uniform(img) is not None
        # With threshold below the actual std, it passes
        assert _is_near_uniform(img, std_threshold=1.5) is None


class TestIsScreenshot:
    def test_flat_ui_blocks_rejected(self):
        """A screenshot-like image with large flat color blocks has few unique colors."""
        img = np.zeros((200, 200, 3), dtype=np.uint8)
        # A few flat-colored rectangles (typical UI)
        img[0:100, 0:100] = [255, 255, 255]
        img[0:100, 100:200] = [50, 50, 200]
        img[100:200, 0:100] = [200, 200, 200]
        img[100:200, 100:200] = [30, 30, 30]
        assert _is_screenshot(img) is not None
        assert "screenshot" in _is_screenshot(img)

    def test_random_photo_accepted(self):
        """A photo-like image with diverse colors should pass."""
        rng = np.random.RandomState(42)
        img = rng.randint(0, 256, (200, 200, 3), dtype=np.uint8)
        assert _is_screenshot(img) is None

    def test_grayscale_skipped(self):
        """Grayscale images skip the screenshot check entirely."""
        img = np.full((200, 200), 128, dtype=np.uint8)
        assert _is_screenshot(img) is None

    def test_custom_threshold(self):
        """With a very high threshold, even a photo gets rejected."""
        rng = np.random.RandomState(42)
        img = rng.randint(0, 256, (200, 200, 3), dtype=np.uint8)
        assert _is_screenshot(img, color_count_threshold=100000) is not None

    def test_natural_photo_with_moderate_range_accepted(self):
        """A photo-like image with moderate color range should pass."""
        rng = np.random.RandomState(42)
        img = rng.randint(20, 200, (200, 200, 3), dtype=np.uint8)
        assert _is_screenshot(img) is None


class TestRejectionReason:
    def test_too_small(self):
        rng = np.random.RandomState(42)
        img = rng.randint(0, 256, (500, 500, 3), dtype=np.uint8)
        reason = _rejection_reason(img)
        assert reason is not None
        assert "too small" in reason

    def test_near_uniform_rejected(self):
        img = np.zeros((1200, 1200, 3), dtype=np.uint8)
        reason = _rejection_reason(img)
        assert reason is not None
        assert "near-uniform" in reason

    def test_screenshot_rejected(self):
        """A large image with flat color blocks should be rejected as screenshot."""
        img = np.zeros((1200, 1200, 3), dtype=np.uint8)
        img[0:600, 0:600] = [255, 255, 255]
        img[0:600, 600:1200] = [50, 50, 200]
        img[600:1200, 0:600] = [200, 200, 200]
        img[600:1200, 600:1200] = [30, 30, 30]
        reason = _rejection_reason(img)
        assert reason is not None
        assert "screenshot" in reason

    def test_valid_photo(self):
        rng = np.random.RandomState(42)
        img = rng.randint(0, 256, (1200, 1200, 3), dtype=np.uint8)
        assert _rejection_reason(img) is None
