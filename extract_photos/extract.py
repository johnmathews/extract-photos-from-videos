#!/usr/bin/env python3

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from threading import Thread

import cv2
import numpy as np
from extract_photos.borders import trim_and_add_border
from extract_photos.display_progress import build_progress_bar, format_time, print_scan_progress
from extract_photos.utils import make_safe_folder_name, setup_logger

HASH_SIZE = 8
HASH_DIFF_THRESHOLD = 10  # hamming distance out of 64 bits — for first-detection
HASH_STEP_THRESHOLD = 3  # step-to-step threshold — same photo has distance 0-2

VAAPI_DEVICE = "/dev/dri/renderD128"
_vaapi_available: bool | None = None


def _is_vaapi_available() -> bool:
    """Check if VAAPI hardware acceleration is available.

    Fast path: returns False immediately if the render device doesn't exist.
    Slow path: runs a minimal ffmpeg encode probe to verify the GPU works.
    Result is cached for the lifetime of the process.
    """
    global _vaapi_available
    if _vaapi_available is not None:
        return _vaapi_available

    if not os.path.exists(VAAPI_DEVICE):
        _vaapi_available = False
        return False

    try:
        subprocess.run(
            [
                "ffmpeg", "-vaapi_device", VAAPI_DEVICE,
                "-f", "lavfi", "-i", "nullsrc=s=16x16:d=1",
                "-vf", "format=nv12,hwupload",
                "-c:v", "h264_vaapi", "-frames:v", "1",
                "-f", "null", "-",
            ],
            capture_output=True,
            timeout=10,
        )
        _vaapi_available = True
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        _vaapi_available = False

    return _vaapi_available


def _lowres_encode_args() -> list[str]:
    """Return ffmpeg encode arguments for low-res transcoding."""
    return ["-vf", "scale=320:-2", "-an", "-q:v", "5"]


def _playback_encode_args(input_height: int) -> list[str]:
    """Return ffmpeg encode arguments for playback transcoding."""
    if _is_vaapi_available():
        if input_height > 1080:
            vf = "format=nv12,hwupload,scale_vaapi=w=-2:h=1080"
        else:
            vf = "format=nv12,hwupload"
        return [
            "-vaapi_device", VAAPI_DEVICE,
            "-vf", vf,
            "-c:v", "h264_vaapi", "-qp", "28",
            "-c:a", "aac", "-b:a", "128k",
        ]
    return [
        "-vf", "scale=-2:'min(1080,ih)'",
        "-c:v", "libx264", "-crf", "28", "-preset", "faster",
        "-c:a", "aac", "-b:a", "128k",
    ]


def _ts() -> str:
    """Return current wall-clock time as HH:MM:SS string."""
    return datetime.now().strftime("%H:%M:%S")


def compute_frame_hash(frame: np.ndarray) -> np.ndarray:
    """Compute an average perceptual hash of a frame (64-bit boolean array)."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if len(frame.shape) == 3 else frame
    resized = cv2.resize(gray, (HASH_SIZE, HASH_SIZE), interpolation=cv2.INTER_AREA)
    return resized > resized.mean()


def hash_difference(hash1: np.ndarray, hash2: np.ndarray) -> int:
    """Hamming distance between two perceptual hashes."""
    return np.count_nonzero(hash1 != hash2)


def detect_almost_uniform_borders(frame: np.ndarray, border_width: int = 5, threshold: float = 5, pillarbox_threshold: float = 1) -> bool:
    """
    Checks if a frame has almost uniform borders.

    Detects three border patterns:
    1. All four borders uniform (photos with full border, e.g. white borders)
    2. Left + Right borders uniform AND truly black (pillarbox/side borders only)
    3. Top + Bottom borders uniform AND truly black (letterbox/top-bottom borders only)

    The all-4-borders check uses threshold=5 to avoid false positives from dark video
    scenes. Pillarbox/letterbox detection requires both very low std (threshold=1) AND
    truly black pixels (max value < 3) to distinguish real pillarbox bars from dark
    video content that happens to have uniform edges.

    Parameters:
        frame (np.array): The input video frame (grayscale or color).
        border_width (int): The width of the borders to check (default 5).
        threshold (float): Max std deviation for all-4-borders uniformity (default 5).
        pillarbox_threshold (float): Stricter std threshold for pillarbox/letterbox (default 1).

    Returns:
        bool: True if borders match any of the three patterns, False otherwise.
    """
    # Convert frame to grayscale if it is not already
    gray_frame = (
        cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if len(frame.shape) == 3 else frame
    )

    # Extract border regions
    left_border = gray_frame[:, :border_width]
    right_border = gray_frame[:, -border_width:]
    top_border = gray_frame[:border_width, :]
    bottom_border = gray_frame[-border_width:, :]

    # Calculate the standard deviation for each border
    left_std = np.std(left_border)  # type: ignore[reportArgumentType]
    right_std = np.std(right_border)  # type: ignore[reportArgumentType]
    top_std = np.std(top_border)  # type: ignore[reportArgumentType]
    bottom_std = np.std(bottom_border)  # type: ignore[reportArgumentType]

    # Pattern 1: All four borders uniform (threshold 10)
    all_four_uniform = (
        left_std <= threshold and right_std <= threshold and
        top_std <= threshold and bottom_std <= threshold
    )
    if all_four_uniform:
        return True

    # Pattern 2: Pillarbox - left and right borders very uniform (stricter threshold)
    # Also require borders to be truly black (max pixel value < 3) to avoid dark scene false positives
    pillarbox = left_std <= pillarbox_threshold and right_std <= pillarbox_threshold
    if pillarbox:
        left_max = np.max(left_border)
        right_max = np.max(right_border)
        if left_max < 3 and right_max < 3:
            return True

    # Pattern 3: Letterbox - top and bottom borders very uniform (stricter threshold)
    # Also require borders to be truly black (max pixel value < 3) to avoid dark scene false positives
    letterbox = top_std <= pillarbox_threshold and bottom_std <= pillarbox_threshold
    if letterbox:
        top_max = np.max(top_border)
        bottom_max = np.max(bottom_border)
        if top_max < 3 and bottom_max < 3:
            return True

    return False


def _is_near_uniform(image: np.ndarray, std_threshold: float = 5.0) -> str | None:
    """Return a rejection reason if the image is near-uniform (solid color with noise), else None.

    Converts to grayscale and checks overall standard deviation.
    Pure black/white frames have std ~0, codec noise gives std ~1-3,
    while even the darkest real photo has std > 15.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
    if np.std(gray) < std_threshold:  # type: ignore[reportArgumentType]
        return "near-uniform frame"
    return None


def _white_background_percentage(image: np.ndarray, sample_size: int = 128, brightness_threshold: int = 240) -> float:
    """Return percentage of near-white pixels in the image.

    Downscales to sample_size x sample_size grayscale and counts pixels above
    brightness_threshold. UI/screenshot frames typically have large white
    backgrounds (40-70%+), while photos rarely exceed 10%.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
    small = cv2.resize(gray, (sample_size, sample_size), interpolation=cv2.INTER_AREA)
    white_pixels = np.count_nonzero(small > brightness_threshold)
    return white_pixels / (sample_size * sample_size) * 100


def _is_screenshot(image: np.ndarray, color_count_threshold: int = 100, sample_size: int = 128) -> str | None:
    """Return a rejection reason if the image looks like a screenshot/UI, else None.

    Two-stage detection:
    1. White-background check: rejects images with >30% near-white pixels (>240
       brightness at 128x128). UI screens have large white backgrounds (40-70%);
       photos rarely exceed 10%. Runs before the grayscale skip to catch both
       color and near-grayscale UI screens.
    2. Color-count check: downscales to sample_size x sample_size, quantizes colors
       to 32 levels per channel, and counts unique combinations. Simple screenshots
       with flat UI regions have 4-30 unique colors; photos have 100+.
       Skips grayscale images (can't reliably classify without color info).
    """
    if len(image.shape) < 3 or image.shape[2] < 3:
        return None
    small = cv2.resize(image, (sample_size, sample_size), interpolation=cv2.INTER_AREA)
    # Stage 1: White-background detection. Runs before the grayscale skip because
    # some UI screens (e.g. template galleries) appear nearly grayscale but have
    # distinctive white backgrounds that photos don't.
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    white_pct = np.count_nonzero(gray > 240) / (sample_size * sample_size) * 100
    if white_pct > 30.0:
        return f"screenshot ({white_pct:.0f}% white background)"
    # Skip effectively-grayscale 3-channel images (e.g. B&W photos from video).
    # Same rationale as the single-channel skip above: can't reliably distinguish
    # a B&W photo from a B&W screenshot using color diversity alone.
    channels = small.astype(np.int16)
    mean_channel_diff = (
        np.abs(channels[:, :, 0] - channels[:, :, 1]).mean()
        + np.abs(channels[:, :, 0] - channels[:, :, 2]).mean()
        + np.abs(channels[:, :, 1] - channels[:, :, 2]).mean()
    ) / 3
    if mean_channel_diff < 10.0:
        return None
    # Stage 2: Color-count detection for simple flat-color screenshots.
    quantized = small // 8  # 256 / 8 = 32 levels per channel
    # Pack RGB into a single int per pixel for fast unique counting
    r = quantized[:, :, 0].astype(np.uint32)
    g = quantized[:, :, 1].astype(np.uint32)
    b = quantized[:, :, 2].astype(np.uint32)
    packed = r * 1024 + g * 32 + b
    unique_colors = len(np.unique(packed))
    if unique_colors < color_count_threshold:
        return f"screenshot ({unique_colors} unique colors)"
    return None


def _read_ffmpeg_progress(process: subprocess.Popen[bytes], duration_us: float, progress_list: list[float], index: int) -> None:
    """Read ffmpeg -progress output and update progress_list[index] with percentage."""
    assert process.stdout is not None
    for raw_line in process.stdout:
        line = raw_line.decode("utf-8", errors="replace").strip()
        if line.startswith("out_time_us="):
            try:
                current_us = int(line.split("=", 1)[1])
            except ValueError:
                continue
            if duration_us > 0:
                progress_list[index] = min(current_us / duration_us * 100, 100)


def transcode_lowres(video_file: str, video_duration_sec: float) -> str:
    """Transcode a video to 320px wide low-res copy for fast scanning.

    Splits the video in half and transcodes both halves in parallel,
    then concatenates the results. Shows a combined progress bar.
    Returns path to the temporary low-res file.
    Raises RuntimeError if ffmpeg is not found or fails.
    """
    midpoint = video_duration_sec / 2

    progress_args = ["-progress", "pipe:1", "-nostats"]
    scale_args = _lowres_encode_args()

    tmp1 = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    tmp1.close()
    tmp2 = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    tmp2.close()

    cmd1 = (
        ["ffmpeg", "-i", video_file, "-t", str(midpoint)]
        + scale_args
        + progress_args
        + [tmp1.name, "-y"]
    )
    cmd2 = (
        ["ffmpeg", "-ss", str(midpoint), "-i", video_file]
        + scale_args
        + progress_args
        + [tmp2.name, "-y"]
    )

    try:
        proc1 = subprocess.Popen(
            cmd1, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
        )
        proc2 = subprocess.Popen(
            cmd2, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
        )
    except FileNotFoundError:
        os.unlink(tmp1.name)
        os.unlink(tmp2.name)
        raise RuntimeError("ffmpeg not found. Install ffmpeg to use this tool.")

    # Track progress from both processes using threads
    progress = [0.0, 0.0]
    duration1_us = midpoint * 1_000_000
    duration2_us = (video_duration_sec - midpoint) * 1_000_000

    t1 = Thread(target=_read_ffmpeg_progress, args=(proc1, duration1_us, progress, 0))
    t2 = Thread(target=_read_ffmpeg_progress, args=(proc2, duration2_us, progress, 1))
    t1.start()
    t2.start()

    # Display combined progress
    wall_start = time.monotonic()
    while t1.is_alive() or t2.is_alive():
        overall_pct = (progress[0] + progress[1]) / 2
        now = time.monotonic()
        wall_elapsed = now - wall_start
        if overall_pct > 2.0:
            eta_sec = wall_elapsed / (overall_pct / 100) - wall_elapsed
            eta_str = f"ETA {format_time(eta_sec)}"
        else:
            eta_str = "ETA --:--"
        bar = build_progress_bar(overall_pct)
        sys.stdout.write(f"\r {bar}  {overall_pct:5.1f}%   {eta_str}\033[K")
        sys.stdout.flush()
        time.sleep(1)

    t1.join()
    t2.join()
    proc1.wait()
    proc2.wait()

    elapsed = format_time(time.monotonic() - wall_start)
    sys.stdout.write(f"\r {build_progress_bar(100)}  100.0%   took {elapsed}\033[K\n")
    sys.stdout.flush()

    if proc1.returncode != 0 or proc2.returncode != 0:
        os.unlink(tmp1.name)
        os.unlink(tmp2.name)
        raise RuntimeError(
            f"ffmpeg failed (exit codes: {proc1.returncode}, {proc2.returncode})"
        )

    # Concatenate the two halves (stream copy, very fast)
    concat_out = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    concat_out.close()
    filelist = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
    filelist.write(f"file '{tmp1.name}'\n")
    filelist.write(f"file '{tmp2.name}'\n")
    filelist.close()

    try:
        subprocess.run(
            [
                "ffmpeg",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                filelist.name,
                "-c",
                "copy",
                concat_out.name,
                "-y",
            ],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as e:
        os.unlink(concat_out.name)
        raise RuntimeError(f"ffmpeg concat failed: {e.stderr.decode()}")
    finally:
        os.unlink(tmp1.name)
        os.unlink(tmp2.name)
        os.unlink(filelist.name)

    return concat_out.name


def scan_for_photos(lowres_path: str, step_time: float, filename: str, video_duration_sec: float) -> list[tuple[float, str]]:
    """Scan the low-res video for frames containing photos.

    Steps through frames at step_time intervals, detects uniform borders,
    and deduplicates using perceptual hashing.

    Returns a list of (timestamp_sec, time_str) tuples for each unique photo found.
    """
    cap = cv2.VideoCapture(lowres_path)
    lowres_fps = cap.get(cv2.CAP_PROP_FPS)
    frame_step = int(lowres_fps * step_time)
    if frame_step < 1:
        frame_step = 1
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    prev_photo_hash = None
    prev_step_hash = None
    photo_timestamps = []
    last_progress_time = 0.0
    wall_start = time.monotonic()

    # Print initial 3 blank lines for the progress display
    print()
    print()
    print()

    while True:
        current_frame = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
        if current_frame >= total_frames:
            break

        ret, frame = cap.read()
        if not ret:
            break

        # Map low-res frame position back to original video timestamp
        timestamp_sec = current_frame / lowres_fps if lowres_fps > 0 else 0
        # Use truncation (not rounding) so tenths stays 0-9
        total_seconds = int(timestamp_sec)
        tenths = int((timestamp_sec - total_seconds) * 10)
        minutes, seconds = divmod(total_seconds, 60)
        if tenths > 0:
            time_str = f"{minutes}m{seconds:02d}.{tenths}s"
        else:
            time_str = f"{minutes}m{seconds:02d}s"

        if detect_almost_uniform_borders(frame) and _is_near_uniform(frame) is None:
            frame_hash = compute_frame_hash(frame)
            # Detect new photo by comparing against the previous step's hash.
            # Consecutive frames of the same photo have distance 0-2; any
            # larger change means the video transitioned to a different photo.
            # Also compare against the last *recorded* photo hash for the
            # initial detection (prev_step_hash is None on first photo frame).
            step_changed = (
                prev_step_hash is not None
                and hash_difference(frame_hash, prev_step_hash) > HASH_STEP_THRESHOLD
            )
            is_new_photo = (
                prev_photo_hash is None
                or step_changed
                or hash_difference(frame_hash, prev_photo_hash) > HASH_DIFF_THRESHOLD
            )
            if is_new_photo:
                photo_timestamps.append((timestamp_sec, time_str))
                prev_photo_hash = frame_hash
            prev_step_hash = frame_hash
        else:
            # Not a photo frame — reset both hashes so the next photo
            # is always detected as new.
            prev_photo_hash = None
            prev_step_hash = None

        cap.set(cv2.CAP_PROP_POS_FRAMES, current_frame + frame_step)

        # Update progress display every second
        now = time.monotonic()
        if now - last_progress_time >= 1.0:
            last_progress_time = now
            pct = current_frame / total_frames * 100 if total_frames > 0 else 0
            wall_elapsed = now - wall_start
            if pct > 2.0:
                eta_sec = wall_elapsed / (pct / 100) - wall_elapsed
                eta_str = f"ETA {format_time(eta_sec)}"
            else:
                eta_str = "ETA --:--"
            print_scan_progress(
                filename,
                pct,
                timestamp_sec,
                video_duration_sec,
                len(photo_timestamps),
                eta_str,
            )

    cap.release()

    # Final progress update with elapsed time
    elapsed = format_time(time.monotonic() - wall_start)
    print_scan_progress(
        filename,
        100.0,
        video_duration_sec,
        video_duration_sec,
        len(photo_timestamps),
        f"took {elapsed}",
    )
    print()

    return photo_timestamps


def _rejection_reason(image: np.ndarray, min_photo_area: int = 0) -> str | None:
    """Return a rejection reason string, or None if the image is valid."""
    h, w = image.shape[:2]
    if min_photo_area > 0 and w * h < min_photo_area:
        return f"too small ({w}x{h})"
    reason = _is_near_uniform(image)
    if reason:
        return reason
    reason = _is_screenshot(image)
    if reason:
        return reason
    return None


def get_video_metadata(video_file: str) -> tuple[int, float, int, int]:
    """Get video fps, duration, and frame dimensions using ffprobe.

    Returns (fps, duration_sec, width, height) tuple.
    Raises RuntimeError if ffprobe fails.
    """
    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        "-select_streams",
        "v:0",
        video_file,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, check=True, text=True)
    except FileNotFoundError:
        raise RuntimeError("ffprobe not found. Install ffmpeg to use this tool.")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffprobe failed: {e.stderr}")

    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    if not streams:
        raise RuntimeError(f"ffprobe found no video stream in {video_file}")
    stream = streams[0]
    fmt = data.get("format", {})

    # Parse fps from r_frame_rate (e.g. "30000/1001") or avg_frame_rate
    fps = 0
    for key in ("r_frame_rate", "avg_frame_rate"):
        rate_str = stream.get(key, "0/0")
        if "/" in rate_str:
            num, den = rate_str.split("/", 1)
            if int(den) > 0:
                fps = int(round(int(num) / int(den)))
                if fps > 0:
                    break
        elif rate_str:
            fps = int(round(float(rate_str)))
            if fps > 0:
                break

    # Parse duration — try stream first, then container format (MKV stores it there)
    duration_sec = 0.0
    if "duration" in stream:
        duration_sec = float(stream["duration"])
    elif "duration" in fmt:
        duration_sec = float(fmt["duration"])
    elif "nb_frames" in stream and fps > 0:
        duration_sec = int(stream["nb_frames"]) / fps

    width = int(stream.get("width", 0))
    height = int(stream.get("height", 0))

    return fps, duration_sec, width, height


def extract_fullres_frames(
    video_file: str, output_folder: str, photo_timestamps: list[tuple[float, str]], filename: str, logger: logging.Logger, border_px: int = 5, min_photo_area: int = 0, include_text: bool = False
) -> int:
    """Extract full-resolution frames at the given timestamps from the original video.

    Uses ffmpeg to seek and decode each frame (works with any codec including AV1),
    runs trim_and_add_border + validation, and saves as JPEG. Prints a line
    per candidate showing the result.
    """
    filename_safe = make_safe_folder_name(os.path.splitext(filename)[0])
    saved_count = 0
    tmp_frame = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    tmp_frame.close()

    try:
        for timestamp_sec, time_str in photo_timestamps:
            cmd = [
                "ffmpeg",
                "-ss",
                str(timestamp_sec),
                "-i",
                video_file,
                "-frames:v",
                "1",
                "-q:v",
                "2",
                tmp_frame.name,
                "-y",
            ]
            result = subprocess.run(cmd, capture_output=True)
            if result.returncode != 0:
                print(
                    f"  {time_str}  -- skipped: ffmpeg failed to extract frame",
                    flush=True,
                )
                logger.warning(f"{time_str}: ffmpeg failed at {timestamp_sec:.1f}s")
                continue

            frame = cv2.imread(tmp_frame.name)
            if frame is None:
                print(
                    f"  {time_str}  -- skipped: could not read extracted frame",
                    flush=True,
                )
                logger.warning(
                    f"{time_str}: could not read frame at {timestamp_sec:.1f}s"
                )
                continue

            trimmed_frame = trim_and_add_border(frame, border_px=border_px, include_text=include_text)
            reason = _rejection_reason(trimmed_frame, min_photo_area=min_photo_area)
            if reason is None:
                file_name = f"{filename_safe}_{time_str}.jpg"
                photo_path = os.path.join(output_folder, file_name)
                cv2.imwrite(photo_path, trimmed_frame)
                saved_count += 1
                print(f"  {time_str}  -- saved", flush=True)
                logger.info(f"{time_str}: saved {file_name}")
            else:
                print(f"  {time_str}  -- skipped: {reason}", flush=True)
                logger.info(f"{time_str}: skipped ({reason})")
    finally:
        if os.path.exists(tmp_frame.name):
            os.unlink(tmp_frame.name)

    return saved_count


def transcode_for_playback(video_file: str, output_dir: str) -> str:
    """Transcode video to H.264/MP4 if needed for Immich playback compatibility.

    Checks the video codec via ffprobe. If already H.264 or HEVC, copies the
    file directly. Otherwise, transcodes to H.264/AAC in MP4 with a progress
    bar. The transcode is optimized for fast encoding over quality — capped at
    1080p, CRF 28, preset faster — since the original file is preserved
    elsewhere and this copy is just for browsing in Immich.

    All progress output goes to stderr so callers can capture the return value
    on stdout.

    Returns the basename of the output file.
    """
    basename = os.path.basename(video_file)

    # Get codec name and height via ffprobe
    codec_cmd = [
        "ffprobe", "-v", "quiet", "-select_streams", "v:0",
        "-show_entries", "stream=codec_name,height", "-of", "csv=p=0", video_file,
    ]
    try:
        codec_result = subprocess.run(codec_cmd, capture_output=True, check=True, text=True)
    except FileNotFoundError:
        raise RuntimeError("ffprobe not found. Install ffmpeg to use this tool.")
    probe_fields = codec_result.stdout.strip().split(",")
    codec = probe_fields[0] if probe_fields else ""
    input_height = int(probe_fields[1]) if len(probe_fields) > 1 and probe_fields[1].strip().isdigit() else 0

    if re.match(r"^(h264|hevc)$", codec, re.IGNORECASE):
        dest = os.path.join(output_dir, basename)
        shutil.copy2(video_file, dest)
        # Explicit fsync to ensure NFS persistence
        with open(dest, "rb") as f:
            os.fsync(f.fileno())
        # Verify the output file exists and has non-zero size (important for NFS)
        if not os.path.exists(dest):
            raise RuntimeError(f"Copy succeeded but file does not exist: {dest}")
        file_size = os.path.getsize(dest)
        if file_size == 0:
            os.unlink(dest)
            raise RuntimeError(f"Copy created empty file: {dest}")
        print(f"Copied video to {dest} ({file_size / 1024 / 1024:.1f} MB)", file=sys.stderr, flush=True)
        return basename

    # Need to transcode — get duration for progress tracking
    dur_cmd = [
        "ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", video_file,
    ]
    dur_result = subprocess.run(dur_cmd, capture_output=True, check=True, text=True)
    duration_sec = float(dur_result.stdout.strip())
    duration_us = duration_sec * 1_000_000

    out_name = os.path.splitext(basename)[0] + ".mp4"
    out_path = os.path.join(output_dir, out_name)

    accel = "VAAPI" if _is_vaapi_available() else "software"
    print(f"Transcoding video ({codec} -> H.264/MP4, {accel}) for Immich compatibility...", file=sys.stderr, flush=True)

    encode_args = _playback_encode_args(input_height)
    cmd = (
        ["ffmpeg", "-i", video_file]
        + encode_args
        + ["-map_metadata", "0", "-progress", "pipe:1", "-nostats", out_path, "-y"]
    )

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    progress = [0.0]
    t = Thread(target=_read_ffmpeg_progress, args=(proc, duration_us, progress, 0))
    t.start()

    wall_start = time.monotonic()
    while t.is_alive():
        pct = progress[0]
        wall_elapsed = time.monotonic() - wall_start
        if pct > 2.0:
            eta_sec = wall_elapsed / (pct / 100) - wall_elapsed
            eta_str = f"ETA {format_time(eta_sec)}"
        else:
            eta_str = "ETA --:--"
        bar = build_progress_bar(pct)
        sys.stderr.write(f"\r {bar}  {pct:5.1f}%   {eta_str}\033[K")
        sys.stderr.flush()
        time.sleep(1)

    t.join()
    proc.wait()

    elapsed = format_time(time.monotonic() - wall_start)
    sys.stderr.write(f"\r {build_progress_bar(100)}  100.0%   took {elapsed}\033[K\n")
    sys.stderr.flush()

    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg transcode failed (exit code: {proc.returncode})")

    # Explicit fsync to ensure NFS persistence before verification
    with open(out_path, "rb") as f:
        os.fsync(f.fileno())

    # Verify the output file exists and has non-zero size (important for NFS)
    if not os.path.exists(out_path):
        raise RuntimeError(f"ffmpeg reported success but output file does not exist: {out_path}")
    file_size = os.path.getsize(out_path)
    if file_size == 0:
        os.unlink(out_path)
        raise RuntimeError(f"ffmpeg created empty output file: {out_path}")

    print(f"Saved transcoded video to {out_path} ({file_size / 1024 / 1024:.1f} MB)", file=sys.stderr, flush=True)
    return out_name


def extract_photos_from_video(
    video_file: str, output_folder: str, step_time: float, filename: str, border_px: int = 5, min_photo_pct: int = 25, include_text: bool = False
) -> None:
    """Extract photos from a video using a three-phase pipeline:
    1. Transcode to low-res temp file
    2. Scan low-res for photo timestamps
    3. Extract full-res frames at those timestamps

    min_photo_pct: minimum photo area as a percentage of total frame area.
        Photos smaller than this fraction of the video frame are rejected.
        Default 25 (i.e. 25%).
    """
    os.makedirs(output_folder, exist_ok=True)

    # Set up logging (timestamped to preserve multiple runs)
    from datetime import datetime

    filename_safe = make_safe_folder_name(os.path.splitext(filename)[0])
    log_dir = os.path.join(output_folder, "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    log_file = os.path.join(log_dir, f"{log_timestamp}_{filename_safe}_extraction.log")
    logger = setup_logger(log_file)

    # Get video metadata via ffprobe (works with any codec including AV1)
    fps, video_duration_sec, frame_w, frame_h = get_video_metadata(video_file)
    frame_area = frame_w * frame_h
    min_photo_area = int(frame_area * min_photo_pct / 100) if frame_area > 0 else 0

    logger.info(f"File: {filename}")
    logger.info(
        f"fps: {fps}, duration: {format_time(video_duration_sec)}, step_time: {step_time}s"
    )
    logger.info(f"Acceleration: {'VAAPI' if _is_vaapi_available() else 'software'}")

    # Phase 1: Transcode to low-res
    print(f"{_ts()} [1/3] Transcoding to low resolution...", flush=True)
    lowres_path = transcode_lowres(video_file, video_duration_sec)
    logger.info(f"Transcoded to low-res: {lowres_path}")

    try:
        # Phase 2: Scan low-res for photo timestamps
        print(f"{_ts()} [2/3] Scanning for photos...", flush=True)
        photo_timestamps = scan_for_photos(
            lowres_path, step_time, filename, video_duration_sec
        )
        logger.info(f"Scan complete: found {len(photo_timestamps)} candidate photos")

        # Phase 3: Extract full-res frames
        candidates = len(photo_timestamps)
        if candidates:
            print(
                f"{_ts()} [3/3] Extracting {candidates} candidates at full resolution...",
                flush=True,
            )
            extract_start = time.monotonic()
            saved = extract_fullres_frames(
                video_file,
                output_folder,
                photo_timestamps,
                filename,
                logger,
                border_px=border_px,
                min_photo_area=min_photo_area,
                include_text=include_text,
            )
            extract_elapsed = format_time(time.monotonic() - extract_start)
        else:
            print(f"{_ts()} [3/3] No photos found.", flush=True)
            saved = 0
            extract_elapsed = "0:00"
    finally:
        # Clean up temp file
        os.unlink(lowres_path)

    logger.info(f"Done: {saved} photos saved to {output_folder}")
    skipped = candidates - saved if candidates else 0
    skipped_msg = f" ({skipped} failed validation)" if skipped else ""
    print(
        f"{_ts()} Extracted {saved} photos to {output_folder}/{skipped_msg}  took {extract_elapsed}",
        flush=True,
    )
