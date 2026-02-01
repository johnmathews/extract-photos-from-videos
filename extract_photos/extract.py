#!/usr/bin/env python3

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from threading import Thread

import cv2
import numpy as np
from borders import trim_and_add_border
from display_progress import build_progress_bar, format_time, print_scan_progress
from utils import is_valid_photo, make_safe_folder_name, setup_logger

HASH_SIZE = 8
HASH_DIFF_THRESHOLD = 10  # hamming distance out of 64 bits


def _ts():
    """Return current wall-clock time as HH:MM:SS string."""
    return datetime.now().strftime("%H:%M:%S")


def compute_frame_hash(frame):
    """Compute an average perceptual hash of a frame (64-bit boolean array)."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if len(frame.shape) == 3 else frame
    resized = cv2.resize(gray, (HASH_SIZE, HASH_SIZE), interpolation=cv2.INTER_AREA)
    return resized > resized.mean()


def hash_difference(hash1, hash2):
    """Hamming distance between two perceptual hashes."""
    return np.count_nonzero(hash1 != hash2)


def detect_almost_uniform_borders(frame, border_width=5, threshold=10):
    """
    Checks if a frame has almost uniform borders.

    Parameters:
        frame (np.array): The input video frame (grayscale or color).
        border_width (int): The width of the borders to check.
        threshold (float): Maximum allowed standard deviation for uniformity.

    Returns:
        bool: True if all borders are almost uniform, False otherwise.
    """
    # Convert frame to grayscale if it is not already
    gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if len(frame.shape) == 3 else frame

    # Extract border regions
    left_border = gray_frame[:, :border_width]
    right_border = gray_frame[:, -border_width:]
    top_border = gray_frame[:border_width, :]
    bottom_border = gray_frame[-border_width:, :]

    # Calculate the standard deviation for each border
    left_std = np.std(left_border)
    right_std = np.std(right_border)
    top_std = np.std(top_border)
    bottom_std = np.std(bottom_border)

    # Check if the standard deviation for all borders is below the threshold
    is_left_uniform = left_std <= threshold
    is_right_uniform = right_std <= threshold
    is_top_uniform = top_std <= threshold
    is_bottom_uniform = bottom_std <= threshold

    # A valid frame must have all borders almost uniform
    return is_left_uniform and is_right_uniform and is_top_uniform and is_bottom_uniform


def _read_ffmpeg_progress(process, duration_us, progress_list, index):
    """Read ffmpeg -progress output and update progress_list[index] with percentage."""
    for raw_line in process.stdout:
        line = raw_line.decode("utf-8", errors="replace").strip()
        if line.startswith("out_time_us="):
            try:
                current_us = int(line.split("=", 1)[1])
            except ValueError:
                continue
            if duration_us > 0:
                progress_list[index] = min(current_us / duration_us * 100, 100)


def transcode_lowres(video_file, video_duration_sec):
    """Transcode a video to 320px wide low-res copy for fast scanning.

    Splits the video in half and transcodes both halves in parallel,
    then concatenates the results. Shows a combined progress bar.
    Returns path to the temporary low-res file.
    Raises RuntimeError if ffmpeg is not found or fails.
    """
    midpoint = video_duration_sec / 2

    progress_args = ["-progress", "pipe:1", "-nostats"]
    scale_args = ["-vf", "scale=320:-2", "-an", "-q:v", "5"]

    tmp1 = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    tmp1.close()
    tmp2 = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    tmp2.close()

    cmd1 = ["ffmpeg", "-i", video_file, "-t", str(midpoint)] + scale_args + progress_args + [tmp1.name, "-y"]
    cmd2 = ["ffmpeg", "-ss", str(midpoint), "-i", video_file] + scale_args + progress_args + [tmp2.name, "-y"]

    try:
        proc1 = subprocess.Popen(cmd1, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        proc2 = subprocess.Popen(cmd2, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
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
        raise RuntimeError(f"ffmpeg failed (exit codes: {proc1.returncode}, {proc2.returncode})")

    # Concatenate the two halves (stream copy, very fast)
    concat_out = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    concat_out.close()
    filelist = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
    filelist.write(f"file '{tmp1.name}'\n")
    filelist.write(f"file '{tmp2.name}'\n")
    filelist.close()

    try:
        subprocess.run(
            ["ffmpeg", "-f", "concat", "-safe", "0", "-i", filelist.name, "-c", "copy", concat_out.name, "-y"],
            check=True, capture_output=True,
        )
    except subprocess.CalledProcessError as e:
        os.unlink(concat_out.name)
        raise RuntimeError(f"ffmpeg concat failed: {e.stderr.decode()}")
    finally:
        os.unlink(tmp1.name)
        os.unlink(tmp2.name)
        os.unlink(filelist.name)

    return concat_out.name


def scan_for_photos(lowres_path, fps, step_time, filename, video_duration_sec):
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
        minutes, seconds = divmod(int(timestamp_sec), 60)
        time_str = f"{minutes}m{seconds:02d}s"

        if detect_almost_uniform_borders(frame):
            frame_hash = compute_frame_hash(frame)
            is_new = prev_photo_hash is None or hash_difference(frame_hash, prev_photo_hash) > HASH_DIFF_THRESHOLD
            if is_new:
                photo_timestamps.append((timestamp_sec, time_str))
                prev_photo_hash = frame_hash

        cap.set(cv2.CAP_PROP_POS_FRAMES, current_frame + frame_step)

        # Update progress display every 5 seconds
        now = time.monotonic()
        if now - last_progress_time >= 5.0:
            last_progress_time = now
            pct = current_frame / total_frames * 100 if total_frames > 0 else 0
            wall_elapsed = now - wall_start
            if pct > 2.0:
                eta_sec = wall_elapsed / (pct / 100) - wall_elapsed
                eta_str = f"ETA {format_time(eta_sec)}"
            else:
                eta_str = "ETA --:--"
            print_scan_progress(filename, pct, timestamp_sec, video_duration_sec, len(photo_timestamps), eta_str)

    cap.release()

    # Final progress update with elapsed time
    elapsed = format_time(time.monotonic() - wall_start)
    print_scan_progress(filename, 100.0, video_duration_sec, video_duration_sec, len(photo_timestamps), f"took {elapsed}")
    print()

    return photo_timestamps


def _rejection_reason(image):
    """Return a rejection reason string, or None if the image is valid."""
    h, w = image.shape[:2]
    if h < 1000 or w < 1000:
        return f"too small ({w}x{h})"
    if len(image.shape) == 2:
        if np.all(image == image[0, 0]):
            return "single color"
    else:
        if (
            np.all(image[:, :, 0] == image[0, 0, 0])
            and np.all(image[:, :, 1] == image[0, 0, 1])
            and np.all(image[:, :, 2] == image[0, 0, 2])
        ):
            return "single color"
    return None


def get_video_metadata(video_file):
    """Get video fps and duration using ffprobe.

    Returns (fps, duration_sec) tuple. Raises RuntimeError if ffprobe fails.
    """
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", "-select_streams", "v:0", video_file,
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

    return fps, duration_sec


def extract_fullres_frames(video_file, output_folder, photo_timestamps, filename, logger, border_px=5):
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
                "ffmpeg", "-ss", str(timestamp_sec), "-i", video_file,
                "-frames:v", "1", "-q:v", "2", tmp_frame.name, "-y",
            ]
            result = subprocess.run(cmd, capture_output=True)
            if result.returncode != 0:
                print(f"  {time_str}  -- skipped: ffmpeg failed to extract frame", flush=True)
                logger.warning(f"{time_str}: ffmpeg failed at {timestamp_sec:.1f}s")
                continue

            frame = cv2.imread(tmp_frame.name)
            if frame is None:
                print(f"  {time_str}  -- skipped: could not read extracted frame", flush=True)
                logger.warning(f"{time_str}: could not read frame at {timestamp_sec:.1f}s")
                continue

            trimmed_frame = trim_and_add_border(frame, border_px=border_px)
            reason = _rejection_reason(trimmed_frame)
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


def extract_photos_from_video(video_file, output_folder, step_time, ssim_threshold, filename, border_px=5):
    """Extract photos from a video using a three-phase pipeline:
    1. Transcode to low-res temp file
    2. Scan low-res for photo timestamps
    3. Extract full-res frames at those timestamps
    """
    os.makedirs(output_folder, exist_ok=True)

    # Set up logging
    filename_safe = make_safe_folder_name(os.path.splitext(filename)[0])
    log_dir = os.path.join(output_folder, "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"{filename_safe}.log")
    logger = setup_logger(log_file)

    # Get video metadata via ffprobe (works with any codec including AV1)
    fps, video_duration_sec = get_video_metadata(video_file)

    logger.info(f"File: {filename}")
    logger.info(f"fps: {fps}, duration: {format_time(video_duration_sec)}, step_time: {step_time}s")

    # Phase 1: Transcode to low-res
    print(f"{_ts()} [1/3] Transcoding to low resolution...", flush=True)
    lowres_path = transcode_lowres(video_file, video_duration_sec)
    logger.info(f"Transcoded to low-res: {lowres_path}")

    try:
        # Phase 2: Scan low-res for photo timestamps
        print(f"{_ts()} [2/3] Scanning for photos...", flush=True)
        photo_timestamps = scan_for_photos(lowres_path, fps, step_time, filename, video_duration_sec)
        logger.info(f"Scan complete: found {len(photo_timestamps)} candidate photos")

        # Phase 3: Extract full-res frames
        candidates = len(photo_timestamps)
        if candidates:
            print(f"{_ts()} [3/3] Extracting {candidates} candidates at full resolution...", flush=True)
            extract_start = time.monotonic()
            saved = extract_fullres_frames(video_file, output_folder, photo_timestamps, filename, logger, border_px=border_px)
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
    print(f"{_ts()} Extracted {saved} photos to {output_folder}/{skipped_msg}  took {extract_elapsed}", flush=True)
