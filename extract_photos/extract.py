#!/usr/bin/env python3

import os
import re
import subprocess
import sys
import tempfile
import time

import cv2
import numpy as np
from borders import trim_and_add_border
from display_progress import build_progress_bar, format_time, print_scan_progress
from utils import is_valid_photo, make_safe_folder_name, setup_logger

HASH_SIZE = 8
HASH_DIFF_THRESHOLD = 10  # hamming distance out of 64 bits


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


def transcode_lowres(video_file, video_duration_sec):
    """Transcode a video to 320px wide low-res copy for fast scanning.

    Shows a single-line progress bar during transcoding.
    Returns path to the temporary low-res file.
    Raises RuntimeError if ffmpeg is not found or fails.
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    tmp.close()
    # -progress pipe:1 outputs line-buffered key=value progress to stdout,
    # which avoids the pipe-buffering issues of ffmpeg's \r-delimited stderr.
    cmd = [
        "ffmpeg", "-i", video_file, "-vf", "scale=320:-2", "-an", "-q:v", "5",
        "-progress", "pipe:1", "-nostats",
        tmp.name, "-y",
    ]

    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        os.unlink(tmp.name)
        raise RuntimeError("ffmpeg not found. Install ffmpeg to use this tool.")

    wall_start = time.monotonic()
    last_update = 0.0
    duration_us = video_duration_sec * 1_000_000

    for raw_line in process.stdout:
        line = raw_line.decode("utf-8", errors="replace").strip()
        if line.startswith("out_time_us="):
            try:
                current_us = int(line.split("=", 1)[1])
            except ValueError:
                continue
            if duration_us > 0:
                pct = min(current_us / duration_us * 100, 100)
                now = time.monotonic()
                if now - last_update >= 1.0:
                    wall_elapsed = now - wall_start
                    if pct > 2.0:
                        eta_sec = wall_elapsed / (pct / 100) - wall_elapsed
                        eta_str = f"ETA {format_time(eta_sec)}"
                    else:
                        eta_str = "ETA --:--"
                    bar = build_progress_bar(pct)
                    sys.stdout.write(f"\r {bar}  {pct:5.1f}%   {eta_str}\033[K")
                    sys.stdout.flush()
                    last_update = now

    process.wait()

    # Show completed bar, then move to next line
    sys.stdout.write(f"\r {build_progress_bar(100)}  100.0%\033[K\n")
    sys.stdout.flush()

    if process.returncode != 0:
        os.unlink(tmp.name)
        raise RuntimeError(f"ffmpeg failed with exit code {process.returncode}")

    return tmp.name


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

    # Final progress update
    print_scan_progress(filename, 100.0, video_duration_sec, video_duration_sec, len(photo_timestamps), "")
    print()

    return photo_timestamps


def extract_fullres_frames(video_file, output_folder, photo_timestamps, fps, filename, logger):
    """Extract full-resolution frames at the given timestamps from the original video.

    Opens the original video, seeks to each timestamp, decodes the frame,
    runs trim_and_add_border + is_valid_photo, and saves as JPEG.
    """
    cap = cv2.VideoCapture(video_file)
    filename_safe = make_safe_folder_name(os.path.splitext(filename)[0])
    saved_count = 0

    for timestamp_sec, time_str in photo_timestamps:
        target_frame = int(timestamp_sec * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
        ret, frame = cap.read()
        if not ret:
            logger.warning(f"{time_str}: could not read frame at {timestamp_sec:.1f}s")
            continue

        trimmed_frame = trim_and_add_border(frame)
        if is_valid_photo(trimmed_frame):
            file_name = f"{filename_safe}_{time_str}.jpg"
            photo_path = os.path.join(output_folder, file_name)
            cv2.imwrite(photo_path, trimmed_frame)
            saved_count += 1
            logger.info(f"{time_str}: saved {file_name}")
        else:
            logger.info(f"{time_str}: frame failed validation, skipped")

    cap.release()
    return saved_count


def extract_photos_from_video(video_file, output_folder, step_time, ssim_threshold, filename):
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

    # Get video metadata
    cap = cv2.VideoCapture(video_file)
    fps = int(cap.get(cv2.CAP_PROP_FPS))
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    video_duration_sec = frame_count / fps if fps > 0 else 0
    cap.release()

    logger.info(f"File: {filename}")
    logger.info(f"fps: {fps}, duration: {format_time(video_duration_sec)}, step_time: {step_time}s")

    # Phase 1: Transcode to low-res
    print("[1/3] Transcoding to low resolution...", flush=True)
    lowres_path = transcode_lowres(video_file, video_duration_sec)
    logger.info(f"Transcoded to low-res: {lowres_path}")

    try:
        # Phase 2: Scan low-res for photo timestamps
        print("[2/3] Scanning for photos...", flush=True)
        photo_timestamps = scan_for_photos(lowres_path, fps, step_time, filename, video_duration_sec)
        logger.info(f"Scan complete: found {len(photo_timestamps)} candidate photos")

        # Phase 3: Extract full-res frames
        if photo_timestamps:
            print(f"[3/3] Extracting {len(photo_timestamps)} photos at full resolution...", flush=True)
            saved = extract_fullres_frames(video_file, output_folder, photo_timestamps, fps, filename, logger)
        else:
            print("[3/3] No photos found.", flush=True)
            saved = 0
    finally:
        # Clean up temp file
        os.unlink(lowres_path)

    logger.info(f"Done: {saved} photos saved to {output_folder}")
    print(f"Extracted {saved} photos to {output_folder}/", flush=True)
