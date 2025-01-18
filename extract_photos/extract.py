#!/usr/bin/env python3

import os
from datetime import timedelta
from multiprocessing import Manager, Pool

import cv2
import numpy as np
from borders import trim_and_add_border
from utils import calculate_ssim, display_progress, is_valid_photo


def detect_uniform_borders(frame, border_width=10):
    """
    Checks if a frame has exact uniform borders.

    Parameters:
        frame (np.array): The input video frame.
        border_width (int): The width of the borders to check.

    Returns:
        bool: True if all borders are exactly uniform, False otherwise.
    """
    # Convert frame to grayscale for easier processing
    # gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray_frame = frame

    # Extract border regions
    left_border = gray_frame[:, :border_width]
    right_border = gray_frame[:, -border_width:]
    top_border = gray_frame[:border_width, :]
    bottom_border = gray_frame[-border_width:, :]

    # Check uniformity for each border
    is_left_uniform = np.all(left_border == left_border[0, 0])
    is_right_uniform = np.all(right_border == right_border[0, 0])
    is_top_uniform = np.all(top_border == top_border[0, 0])
    is_bottom_uniform = np.all(bottom_border == bottom_border[0, 0])

    # A valid frame must have all borders uniform
    return is_left_uniform and is_right_uniform and is_top_uniform and is_bottom_uniform


def process_chunk(
    video_file, output_folder, start_frame, end_frame, frame_step, fps, ssim_threshold, chunk_id, progress_dict
):
    cap = cv2.VideoCapture(video_file)
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    prev_frame = None
    photo_index = 0
    total_frames = end_frame - start_frame
    total_time = timedelta(seconds=int(total_frames / fps))

    while True:
        current_frame = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
        if current_frame >= end_frame:
            break

        ret, frame = cap.read()
        if not ret:  # End of video
            break

        # Check for white borders
        is_solid_color = detect_uniform_borders(frame, border_width=10)

        # to avoid extracting the same photograph more than once,
        # check that this frame is not the same as the previous frame
        if is_solid_color:
            if prev_frame is not None:
                similarity = calculate_ssim(frame, prev_frame)
                if similarity < ssim_threshold:
                    trimmed_frame = trim_and_add_border(frame)
                    if is_valid_photo(trimmed_frame):
                        photo_path = os.path.join(output_folder, f"photo_chunk{chunk_id}_{photo_index:03d}.jpg")
                        cv2.imwrite(photo_path, trimmed_frame)
                        photo_index += 1

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
        }

    # Mark chunk as complete
    progress_dict[chunk_id] = {
        "progress": "100.00%",
        "time": f"{total_time}/{total_time}",
        "frames": f"{total_frames}/{total_frames}",
        "photos": photo_index,
    }

    cap.release()
    return photo_index


def extract_photos_from_video_parallel(
    video_file,
    output_folder="/Users/john/Desktop/videos/extracted_photos",
    step_time=1,
    ssim_threshold=0.98,
):
    """
    checks frames of a video to see if the frame contains a photograph.
    a photograph is identified by having a solid color border around it.
    the photo must be larger than a minimum size.

    extracted_photos: will contain a subdirectory for each video. each subdirectory contains the photographs extracted from
        the video.
    step_time: amount of time in seconds between each step.
    ssim_threshold: if a frame has a similarity highter than ssim_threshold it will be considered the same as the previous
        frame and will not be extracted again.
    """
    os.makedirs(output_folder, exist_ok=True)

    # Load video
    cap = cv2.VideoCapture(video_file)
    fps = int(cap.get(cv2.CAP_PROP_FPS))
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_step = fps * step_time
    cap.release()

    # Determine the number of chunks
    num_cores = os.cpu_count() or 1
    num_chunks = max(1, num_cores // 4) # div by more than 4 makes laptop unusably slow. 4 seems a good balance.
    chunk_size = frame_count // num_chunks
    chunks = [(i * chunk_size, (i + 1) * chunk_size) for i in range(num_chunks)]
    chunks[-1] = (chunks[-1][0], frame_count)  # Ensure the last chunk includes all remaining frames

    # Shared progress dictionary
    with Manager() as manager:
        progress_dict = manager.dict(
            {
                i: {"progress": "0.00%", "time": "0:00:00/0:00:00", "frames": "0/0", "photos": 0}
                for i in range(num_chunks)
            }
        )

        # Prepare arguments for multiprocessing
        args = [
            (video_file, output_folder, start, end, frame_step, fps, ssim_threshold, i, progress_dict)
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
