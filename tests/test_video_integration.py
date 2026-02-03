"""Integration tests using the real test video.

These tests are slow (require transcoding + scanning a real video) and are
excluded from default pytest runs.  Run them explicitly with:

    uv run pytest tests/test_video_integration.py -m slow
"""

import os
import re
import tempfile

import pytest

from extract_photos.extract import (
    extract_fullres_frames,
    get_video_metadata,
    scan_for_photos,
    transcode_lowres,
)
from extract_photos.utils import setup_logger

TEST_VIDEO_DIR = os.path.join(os.path.dirname(__file__), "..", "test-video")
TIMESTAMPS_FILE = os.path.join(TEST_VIDEO_DIR, "photo-timestamps.txt")
TOLERANCE_SEC = 3.0  # match tolerance between expected and detected timestamps


def _find_test_video():
    """Return the path to the test video, or None if not present."""
    if not os.path.isdir(TEST_VIDEO_DIR):
        return None
    for f in os.listdir(TEST_VIDEO_DIR):
        if f.endswith(".mp4"):
            return os.path.join(TEST_VIDEO_DIR, f)
    return None


def _parse_expected_timestamps(path):
    """Parse photo-timestamps.txt and return a list of (label, seconds) tuples."""
    timestamps = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            m = re.match(r"^(\d+):(\d+)$", line)
            if m:
                minutes, seconds = int(m.group(1)), int(m.group(2))
                total_sec = minutes * 60 + seconds
                timestamps.append((line, total_sec))
    return timestamps


TEST_VIDEO = _find_test_video()
skip_no_video = pytest.mark.skipif(TEST_VIDEO is None, reason="Test video not present")


@pytest.mark.slow
@skip_no_video
class TestVideoIntegration:
    """End-to-end tests against the real test video."""

    @pytest.fixture(scope="class")
    def video_metadata(self):
        return get_video_metadata(TEST_VIDEO)

    @pytest.fixture(scope="class")
    def scan_results(self, video_metadata):
        """Transcode and scan the test video once for the whole class."""
        fps, duration, _w, _h = video_metadata
        lowres_path = transcode_lowres(TEST_VIDEO, duration)
        try:
            timestamps = scan_for_photos(lowres_path, fps, 0.4, "test.mp4", duration)
        finally:
            os.unlink(lowres_path)
        return timestamps

    @pytest.fixture(scope="class")
    def expected_timestamps(self):
        return _parse_expected_timestamps(TIMESTAMPS_FILE)

    def test_all_expected_timestamps_found(self, scan_results, expected_timestamps):
        """Every expected photo timestamp should have a scan match within tolerance."""
        detected_seconds = [ts for ts, _ in scan_results]

        missing = []
        for label, exp_sec in expected_timestamps:
            matches = [d for d in detected_seconds if abs(d - exp_sec) <= TOLERANCE_SEC]
            if not matches:
                missing.append(label)

        assert missing == [], (
            f"Expected timestamps not found in scan (tolerance {TOLERANCE_SEC}s): {missing}"
        )

    def test_extraction_does_not_reject_expected(self, scan_results, expected_timestamps, video_metadata):
        """Frames at expected timestamps should pass the extraction-phase validation."""
        _fps, _duration, frame_w, frame_h = video_metadata
        min_photo_area = int(frame_w * frame_h * 25 / 100)

        # Filter scan results to only those matching expected timestamps
        matched_candidates = []
        for label, exp_sec in expected_timestamps:
            matches = [(ts, ts_str) for ts, ts_str in scan_results if abs(ts - exp_sec) <= TOLERANCE_SEC]
            if matches:
                closest = min(matches, key=lambda m: abs(m[0] - exp_sec))
                matched_candidates.append(closest)

        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = os.path.join(tmpdir, "test.log")
            logger = setup_logger(log_file)
            saved = extract_fullres_frames(
                TEST_VIDEO, tmpdir, matched_candidates, "test.mp4", logger,
                min_photo_area=min_photo_area,
            )

        assert saved == len(matched_candidates), (
            f"Expected {len(matched_candidates)} photos saved, got {saved}"
        )
