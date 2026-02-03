import logging
import os
import tempfile

import cv2
import numpy as np

from extract_photos.utils import calculate_ssim, is_valid_photo, make_safe_folder_name, setup_logger


class TestMakeSafeFolderName:
    def test_basic(self):
        assert make_safe_folder_name("Hello World") == "hello-world"

    def test_special_characters(self):
        assert make_safe_folder_name("Video (2024) - Final!") == "video-2024---final"

    def test_multiple_spaces(self):
        assert make_safe_folder_name("lots   of   spaces") == "lots-of-spaces"

    def test_leading_trailing_whitespace(self):
        assert make_safe_folder_name("  padded  ") == "padded"

    def test_already_safe(self):
        assert make_safe_folder_name("already-safe") == "already-safe"

    def test_empty_string(self):
        assert make_safe_folder_name("") == ""

    def test_unicode_accents_preserved(self):
        # \w matches unicode word chars, so accented letters survive
        result = make_safe_folder_name("café résumé")
        assert result == "café-résumé"

    def test_dots_and_underscores(self):
        # underscores match \w so they survive; dots don't
        result = make_safe_folder_name("file_name.ext")
        assert "_" in result
        assert "." not in result


class TestIsValidPhoto:
    def _solid_color(self, h, w, color=(128, 128, 128)):
        img = np.zeros((h, w, 3), dtype=np.uint8)
        img[:] = color
        return img

    def _gradient(self, h, w):
        """Create an image with varying pixel values (not single color)."""
        img = np.zeros((h, w, 3), dtype=np.uint8)
        for c in range(3):
            img[:, :, c] = np.tile((np.arange(w) % 256).astype(np.uint8), (h, 1))
        return img

    def test_valid_large_gradient(self):
        img = self._gradient(1200, 1200)
        assert is_valid_photo(img) is True

    def test_too_small_width(self):
        img = self._gradient(1200, 800)
        assert is_valid_photo(img) is False

    def test_too_small_height(self):
        img = self._gradient(800, 1200)
        assert is_valid_photo(img) is False

    def test_too_small_both(self):
        img = self._gradient(500, 500)
        assert is_valid_photo(img) is False

    def test_exact_minimum(self):
        img = self._gradient(1000, 1000)
        assert is_valid_photo(img) is True

    def test_single_color_rejected(self):
        img = self._solid_color(1200, 1200)
        assert is_valid_photo(img) is False

    def test_single_color_grayscale_rejected(self):
        img = np.full((1200, 1200), 100, dtype=np.uint8)
        assert is_valid_photo(img) is False

    def test_grayscale_gradient_accepted(self):
        img = np.tile((np.arange(1200) % 256).astype(np.uint8), (1200, 1))
        assert is_valid_photo(img) is True

    def test_near_black_rejected(self):
        """Near-black image with slight noise (std < 5) should be rejected."""
        rng = np.random.RandomState(42)
        img = rng.randint(0, 4, (1200, 1200, 3), dtype=np.uint8)
        assert is_valid_photo(img) is False

    def test_near_white_rejected(self):
        """Near-white image with slight noise (std < 5) should be rejected."""
        rng = np.random.RandomState(42)
        img = 252 + rng.randint(0, 4, (1200, 1200, 3), dtype=np.uint8)
        assert is_valid_photo(img) is False

    def test_dark_but_textured_accepted(self):
        """A dark image with real texture (std > 5) should be accepted."""
        rng = np.random.RandomState(42)
        img = rng.randint(10, 80, (1200, 1200, 3), dtype=np.uint8)
        assert is_valid_photo(img) is True


class TestCalculateSSIM:
    def test_identical_frames(self):
        frame = np.random.randint(0, 256, (200, 200, 3), dtype=np.uint8)
        score = calculate_ssim(frame, frame.copy())
        assert score > 0.99

    def test_different_frames(self):
        frame1 = np.zeros((200, 200, 3), dtype=np.uint8)
        frame2 = np.full((200, 200, 3), 255, dtype=np.uint8)
        score = calculate_ssim(frame1, frame2)
        assert score < 0.1

    def test_similar_frames(self):
        rng = np.random.RandomState(42)
        frame1 = rng.randint(0, 256, (200, 200, 3), dtype=np.uint8)
        frame2 = frame1.copy()
        # Add small noise
        noise = rng.randint(-5, 6, frame2.shape, dtype=np.int16)
        frame2 = np.clip(frame2.astype(np.int16) + noise, 0, 255).astype(np.uint8)
        score = calculate_ssim(frame1, frame2)
        assert 0.3 < score < 1.0


class TestSetupLogger:
    def test_creates_logger_with_file_handler(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = os.path.join(tmpdir, "test.log")
            logger = setup_logger(log_file)

            assert isinstance(logger, logging.Logger)
            logger.info("test message")

            # Flush handlers
            for handler in logger.handlers:
                handler.flush()

            with open(log_file) as f:
                content = f.read()
            assert "test message" in content
