"""Integration tests using real test videos.

These tests are slow (require transcoding + scanning real videos) and are
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

TEST_VIDEOS_ROOT = os.path.join(os.path.dirname(__file__), "..", "test-videos")
TOLERANCE_SEC = 3.0  # match tolerance between expected and detected timestamps
VIDEO_EXTENSIONS = (".mp4", ".mkv", ".avi", ".mov", ".webm")


def _find_video_in_dir(video_dir):
    """Return the path to the first video file in a directory, or None."""
    for f in sorted(os.listdir(video_dir)):
        if any(f.endswith(ext) for ext in VIDEO_EXTENSIONS):
            return os.path.join(video_dir, f)
    return None


def _discover_test_video_dirs():
    """Find all test-video-* directories that have both a video and photo-timestamps.txt."""
    dirs = []
    if not os.path.isdir(TEST_VIDEOS_ROOT):
        return dirs
    for name in sorted(os.listdir(TEST_VIDEOS_ROOT)):
        d = os.path.join(TEST_VIDEOS_ROOT, name)
        if not os.path.isdir(d) or not name.startswith("test-video-"):
            continue
        ts_file = os.path.join(d, "photo-timestamps.txt")
        video = _find_video_in_dir(d)
        if os.path.isfile(ts_file) and video:
            dirs.append(d)
    return dirs


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


def _parse_scan_settings(path):
    """Parse 'setting: key=value' directives from photo-timestamps.txt.

    Returns a dict of keyword arguments to pass to scan_for_photos().
    Supported settings: require_borders (bool).
    """
    settings: dict[str, object] = {}
    bool_keys = {"require_borders"}
    with open(path) as f:
        for line in f:
            m = re.match(r"^setting:\s*(\w+)=(\S+)", line.strip())
            if m:
                key, val = m.group(1), m.group(2)
                if key in bool_keys:
                    settings[key] = val.lower() == "true"
    return settings


def _parse_edge_case_timestamps(path):
    """Parse edge-cases.txt and return a list of (label, seconds) tuples.

    Finds all MM:SS timestamps in the file, excluding those in the "should be
    rejected" section.
    """
    timestamps = []
    in_rejection_section = False
    with open(path) as f:
        for line in f:
            if "should be rejected" in line.lower():
                in_rejection_section = True
                continue
            # A new section header (non-blank line without timestamps) ends the rejection section
            if in_rejection_section and line.strip() and not re.search(r"\d+:\d+", line):
                in_rejection_section = False
            if in_rejection_section:
                continue
            for m in re.finditer(r"(\d+):(\d+)", line):
                minutes, seconds = int(m.group(1)), int(m.group(2))
                total_sec = minutes * 60 + seconds
                label = m.group(0)
                timestamps.append((label, total_sec))
    return timestamps


def _parse_rejection_timestamps(path):
    """Parse edge-cases.txt and return timestamps from the 'should be rejected' section."""
    timestamps = []
    in_rejection_section = False
    with open(path) as f:
        for line in f:
            if "should be rejected" in line.lower():
                in_rejection_section = True
                continue
            if in_rejection_section and line.strip() and not re.search(r"\d+:\d+", line):
                in_rejection_section = False
            if in_rejection_section:
                for m in re.finditer(r"(\d+):(\d+)", line):
                    minutes, seconds = int(m.group(1)), int(m.group(2))
                    total_sec = minutes * 60 + seconds
                    label = m.group(0)
                    timestamps.append((label, total_sec))
    return timestamps


_test_video_dirs = _discover_test_video_dirs()
skip_no_videos = pytest.mark.skipif(len(_test_video_dirs) == 0, reason="No test videos present")


# --- Module-level fixtures parametrized over test video directories ---


@pytest.fixture(scope="class", params=_test_video_dirs, ids=lambda d: os.path.basename(d))
def video_dir(request):
    return request.param


@pytest.fixture(scope="class")
def test_video_path(video_dir):
    path = _find_video_in_dir(video_dir)
    assert path is not None, f"No video file found in {video_dir}"
    return path


@pytest.fixture(scope="class")
def video_metadata(test_video_path):
    return get_video_metadata(test_video_path)


@pytest.fixture(scope="class")
def scan_results(test_video_path, video_dir, video_metadata):
    """Transcode and scan the test video once per video directory."""
    _fps, duration, _w, _h = video_metadata
    settings = _parse_scan_settings(os.path.join(video_dir, "photo-timestamps.txt"))
    lowres_path = transcode_lowres(test_video_path, duration)
    try:
        timestamps = scan_for_photos(
            lowres_path, 0.4, os.path.basename(test_video_path), duration,
            min_photo_duration=0.5,
            **settings,
        )
    finally:
        os.unlink(lowres_path)
    return timestamps


@pytest.fixture(scope="class")
def expected_timestamps(video_dir):
    return _parse_expected_timestamps(os.path.join(video_dir, "photo-timestamps.txt"))


@pytest.fixture(scope="class")
def edge_case_timestamps(video_dir):
    path = os.path.join(video_dir, "edge-cases.txt")
    if not os.path.isfile(path):
        pytest.skip("edge-cases.txt not present")
    return _parse_edge_case_timestamps(path)


@pytest.fixture(scope="class")
def rejection_timestamps(video_dir):
    path = os.path.join(video_dir, "edge-cases.txt")
    if not os.path.isfile(path):
        pytest.skip("edge-cases.txt not present")
    timestamps = _parse_rejection_timestamps(path)
    if not timestamps:
        pytest.skip("No rejection timestamps in edge-cases.txt")
    return timestamps


@pytest.mark.slow
@skip_no_videos
class TestVideoIntegration:
    """End-to-end tests against real test videos (parametrized over all test-video-* dirs)."""

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

    def test_extraction_does_not_reject_expected(self, scan_results, expected_timestamps, video_metadata, test_video_path):
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
                test_video_path, tmpdir, matched_candidates, os.path.basename(test_video_path), logger,
                min_photo_area=min_photo_area,
            )

        assert saved == len(matched_candidates), (
            f"Expected {len(matched_candidates)} photos saved, got {saved}"
        )

    def test_edge_cases_found_in_scan(self, scan_results, edge_case_timestamps):
        """Edge-case timestamps (side-by-side, similar sequential) should be detected."""
        detected_seconds = [ts for ts, _ in scan_results]

        missing = []
        for label, exp_sec in edge_case_timestamps:
            matches = [d for d in detected_seconds if abs(d - exp_sec) <= TOLERANCE_SEC]
            if not matches:
                missing.append(label)

        assert missing == [], (
            f"Edge-case timestamps not found in scan (tolerance {TOLERANCE_SEC}s): {missing}"
        )

    def test_edge_cases_not_rejected_at_extraction(self, scan_results, edge_case_timestamps, video_metadata, test_video_path):
        """Edge-case photos should pass the extraction-phase validation."""
        _fps, _duration, frame_w, frame_h = video_metadata
        min_photo_area = int(frame_w * frame_h * 25 / 100)

        matched_candidates = []
        for label, exp_sec in edge_case_timestamps:
            matches = [(ts, ts_str) for ts, ts_str in scan_results if abs(ts - exp_sec) <= TOLERANCE_SEC]
            if matches:
                closest = min(matches, key=lambda m: abs(m[0] - exp_sec))
                matched_candidates.append(closest)

        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = os.path.join(tmpdir, "test.log")
            logger = setup_logger(log_file)
            saved = extract_fullres_frames(
                test_video_path, tmpdir, matched_candidates, os.path.basename(test_video_path), logger,
                min_photo_area=min_photo_area,
            )

        assert saved == len(matched_candidates), (
            f"Expected {len(matched_candidates)} edge-case photos saved, got {saved}"
        )

    def test_ui_screens_rejected_at_extraction(self, scan_results, rejection_timestamps, video_metadata, test_video_path):
        """UI/screenshot frames should be rejected during extraction (saved == 0)."""
        _fps, _duration, frame_w, frame_h = video_metadata
        min_photo_area = int(frame_w * frame_h * 25 / 100)

        # Find scan results near rejection timestamps
        matched_candidates = []
        for label, exp_sec in rejection_timestamps:
            matches = [(ts, ts_str) for ts, ts_str in scan_results if abs(ts - exp_sec) <= TOLERANCE_SEC]
            if matches:
                closest = min(matches, key=lambda m: abs(m[0] - exp_sec))
                matched_candidates.append(closest)

        if not matched_candidates:
            pytest.skip("No rejection timestamps found in scan results")

        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = os.path.join(tmpdir, "test.log")
            logger = setup_logger(log_file)
            saved = extract_fullres_frames(
                test_video_path, tmpdir, matched_candidates, os.path.basename(test_video_path), logger,
                min_photo_area=min_photo_area,
            )

        assert saved == 0, (
            f"Expected 0 photos saved from UI screens, got {saved} "
            f"(timestamps: {[label for label, _ in rejection_timestamps]})"
        )
