#!/usr/bin/env python3

import os
from datetime import timedelta
from multiprocessing import Manager, Pool

import cv2
import numpy as np
from borders import trim_and_add_border
from display_progress import display_progress
from utils import calculate_ssim, is_valid_photo, make_safe_folder_name, setup_logger


def is_frame_static(video_capture, current_frame, frame_offset, ssim_threshold):
    """
    Determines if the current frame is part of a still photo or a video segment.

    Parameters:
        video_capture (cv2.VideoCapture): The video capture object.
        current_frame (np.array): The current frame to test.
        frame_offset (int): Number of frames to skip forward for comparison.
        ssim_threshold (float): SSIM similarity threshold. Frames with SSIM above this are considered identical.

    Returns:
        bool: True if the frame is part of a photo, False if part of a video.
    """
    # Get the current position in the video
    current_pos = int(video_capture.get(cv2.CAP_PROP_POS_FRAMES))

    # Move forward by the frame offset
    target_frame_pos = current_pos + frame_offset
    video_capture.set(cv2.CAP_PROP_POS_FRAMES, target_frame_pos)

    # Read the target frame
    ret, target_frame = video_capture.read()

    # Restore the position to the current frame
    video_capture.set(cv2.CAP_PROP_POS_FRAMES, current_pos)

    # If unable to read the target frame, return False (likely end of video)
    if not ret:
        return False

    # Calculate SSIM between the current frame and the target frame
    current_gray = cv2.cvtColor(current_frame, cv2.COLOR_BGR2GRAY)
    target_gray = cv2.cvtColor(target_frame, cv2.COLOR_BGR2GRAY)
    from skimage.metrics import structural_similarity as ssim

    similarity, _ = ssim(current_gray, target_gray, full=True)

    # Determine if the frames are identical
    return similarity >= ssim_threshold


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


def process_chunk(
    video_file,
    output_folder: str,
    start_frame: int,
    end_frame: int,
    frame_step: float,
    fps: int,
    ssim_threshold: float,
    chunk_id: int,
    progress_dict: dict,
    filename: str,
):

    filename_safe = make_safe_folder_name(os.path.splitext(filename)[0])
    log_dir = os.path.join(output_folder, "logs")
    os.makedirs(log_dir, exist_ok=True)

    start_minutes, start_seconds = divmod(start_frame / fps, 60)
    start_time = f"{int(start_minutes)}:{int(start_seconds):02d}"
    end_minutes, end_seconds = divmod(end_frame / fps, 60)
    end_time = f"{int(end_minutes)}:{int(end_seconds):02d}"

    log_file = os.path.join(
        log_dir, f"{filename_safe}__chunk_{chunk_id}__{start_time.replace(':','m')}s_to_{end_time.replace(':','m')}s.log"
    )
    logger = setup_logger(log_file)

    logger.info(f"File: {filename_safe}")
    logger.info(f"Starting chunk {chunk_id}")
    logger.info(f"Chunk time: {start_time} - {end_time}")
    logger.info(f"fps: {fps}, frame_step: {frame_step}, step_time: {frame_step / fps}s")
    logger.info(f"ssim_threshold: {ssim_threshold}")

    cap = cv2.VideoCapture(video_file)
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

    prev_frame = None
    photo_index = 0
    total_frames = end_frame - start_frame
    total_time = timedelta(seconds=int(total_frames / fps))

    start_frame = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
    # start_time_minutes, start_time_seconds = divmod(start_frame / fps, 60)
    # start_time = f"{int(start_time_minutes)}-{int(start_time_seconds):02d}"
    logger.info(f"Analysing from {start_time}")

    while True:
        current_frame = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
        current_time_minutes, current_time_seconds = divmod(current_frame / fps, 60)
        current_time = f"{int(current_time_minutes)}m{int(current_time_seconds):02d}s"

        if current_frame >= end_frame:
            break

        ret, frame = cap.read()
        if not ret:  # End of video
            break

        # Check for white borders
        border_test = detect_almost_uniform_borders(frame)

        # to avoid extracting the same photograph more than once,
        # check that this frame is not the same as the previous frame
        if border_test:
            if prev_frame is not None:
                similarity = calculate_ssim(frame, prev_frame)
                if similarity < ssim_threshold:
                    trimmed_frame = trim_and_add_border(frame)
                    if is_valid_photo(trimmed_frame):
                        is_photo = is_frame_static(cap, frame, frame_offset=5, ssim_threshold=ssim_threshold)
                        if is_photo:
                            file_name = f"{filename_safe}_{current_time}.jpg"
                            photo_path = os.path.join(output_folder, file_name)
                            cv2.imwrite(photo_path, trimmed_frame)
                            photo_index += 1
                            logger.info(f"{current_time}: saved file {file_name}")

        prev_frame = frame
        cap.set(cv2.CAP_PROP_POS_FRAMES, current_frame + frame_step)

        # Update progress
        elapsed_time = timedelta(seconds=int((current_frame - start_frame) / fps))
        progress = (current_frame - start_frame) / total_frames * 100
        progress_dict[chunk_id] = {
            "progress": f"{progress:.2f}%",
            "time": f"{elapsed_time}/{total_time}",
            "frames": f"{current_frame}/{total_frames}",
            "photos": photo_index,
            "current_time": current_time,
        }

    logger.info(f"Progress: {progress:.2f}% | Photos: {photo_index}")

    # Mark chunk as complete
    progress_dict[chunk_id] = {
        "progress": "100.00%",
        "time": f"{total_time}/{total_time}",
        "frames": f"{total_frames}/{total_frames}",
        "photos": photo_index,
        "current_time": current_time,
    }

    # Log completion
    logger.info(f"Analysed until {current_time}")
    logger.info(f"Chunk {chunk_id} completed: {photo_index} photos extracted.")
    cap.release()
    return photo_index


def extract_photos_from_video_parallel(
    video_file,
    output_folder: str,
    step_time: float,
    ssim_threshold: float,
    filename: int,
):
    """
    checks frames of a video to see if the frame contains a photograph.
    a photograph is identified by having a solid color border around it.
    the photo must be larger than a minimum size.

    extracted_photos: will contain a subdirectory for each video. each subdirectory contains the photographs extracted from
        the video.
    step_time: amount of time in seconds between each step.
    ssim_threshold: if a frame has a similarity higher than ssim_threshold it will be considered the same as the previous
        frame and will not be extracted again.
    """
    os.makedirs(output_folder, exist_ok=True)

    # Load video
    cap = cv2.VideoCapture(video_file)
    fps = int(cap.get(cv2.CAP_PROP_FPS))
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_step = fps * step_time  # number of frames to jump each time
    cap.release()

    # Determine the number of chunks
    num_cores = os.cpu_count() or 1
    num_chunks = max(1, num_cores // 4)  # div by more than 4 makes laptop unusably slow. 4 seems a good balance.
    chunk_size = frame_count // num_chunks
    chunks = [(i * chunk_size, (i + 1) * chunk_size) for i in range(num_chunks)]
    chunks[-1] = (chunks[-1][0], frame_count)  # Ensure the last chunk includes all remaining frames

    # Shared progress dictionary
    with Manager() as manager:

        # this is the first version of progress_dict that you see, and can leave artifiacts on the console.
        progress_dict = manager.dict(
            {
                i: {
                    "progress": "0.00%",
                    "time": "0:00:00/0:00:00",
                    "frames": "0/0",
                    "photos": 0,
                    "current_time": "00:00",
                }
                for i in range(num_chunks)
            }
        )

        # Prepare arguments for multiprocessing
        args = [
            (video_file, output_folder, start, end, frame_step, fps, ssim_threshold, i, progress_dict, filename)
            for i, (start, end) in enumerate(chunks)
        ]

        # Start multiprocessing
        with Pool(num_chunks) as pool:
            # Launch a background thread to display progress
            from threading import Thread

            progress_thread = Thread(target=display_progress, args=(progress_dict, num_chunks))
            progress_thread.start()

            # Run the chunk processing
            results = pool.starmap(process_chunk, args)

            # Wait for progress display to finish
            progress_thread.join()

    total_photos = sum(results)
    print(f"\n✅ Extracted {total_photos} photos to {output_folder}")
