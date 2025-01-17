#!/usr/bin/env python3

import argparse
import os
from datetime import timedelta

import cv2
import numpy as np

from borders import trim_and_add_border
from utils import calculate_ssim, is_valid_photo

from extract_photos.batch_processor import process_videos_in_directory

def extract_photos_from_video(
    video_file="",
    output_folder="/Users/john/Desktop/videos/extracted_photos",
    step_time=1,
    ssim_threshold=0.98,
):
    """
    Extracts photos with borders from a video and saves them as JPEGs.

    Parameters:
    - video_path: Path to the input video file.
    - output_folder: Path to save the extracted photographs.
    - step_time: Interval of time in seconds to skip when analyzing video (default=1).
    - ssim_threshold: Similarity threshold for determining if frames are identical (default 0.95).
    """

    print(f"{video_file = }")
    print(f"{output_folder = }")

    # Ensure output folder exists
    os.makedirs(output_folder, exist_ok=True)

    # Load video
    cap = cv2.VideoCapture(video_file)
    fps = int(cap.get(cv2.CAP_PROP_FPS))  # Frames per second
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    video_duration = timedelta(seconds=int(frame_count / fps))  # Total video duration

    frame_step = fps * step_time

    # Variables for processing
    prev_frame = None
    photo_index = 0
    current_frame = 0

    while current_frame < frame_count:
        # Set the position to the current frame
        cap.set(cv2.CAP_PROP_POS_FRAMES, current_frame)
        ret, frame = cap.read()
        if not ret:  # End of video
            break

        # Update progress tracker
        current_time = timedelta(seconds=int(current_frame / fps))
        percent_complete = (current_frame / frame_count) * 100
        print(
            f"\nFound {photo_index} images | Time: {current_time}/{video_duration} | Progress: {percent_complete:.2f}%",
            end="\r",
        )

        # Check for white borders
        gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        left_border = gray_frame[:, :5]
        right_border = gray_frame[:, -5:]
        top_border = gray_frame[:5, :]
        bottom_border = gray_frame[-5:, :]

        is_solid_color = (
            np.all(left_border == left_border[0, 0])
            and np.all(right_border == right_border[0, 0])
            and np.all(top_border == top_border[0, 0])
            and np.all(bottom_border == bottom_border[0, 0])
        )

        if is_solid_color:
            if prev_frame is not None:
                # Compute SSIM between the current frame and the previous saved frame
                similarity = calculate_ssim(frame, prev_frame)

                if similarity < ssim_threshold:
                    # Save the previous frame as a photo
                    trimmed_frame = trim_and_add_border(prev_frame)
                    if is_valid_photo(trimmed_frame):
                        photo_path = os.path.join(output_folder, f"photo_{photo_index:03d}.jpg")
                        cv2.imwrite(photo_path, trimmed_frame)
                        photo_index += 1

            # Update the previous frame
            prev_frame = frame

        # Move to the next subset frame
        current_frame += frame_step

    # Save the last frame if not already saved
    if prev_frame is not None:
        photo_path = os.path.join(output_folder, f"photo_{photo_index:03d}.jpg")
        cv2.imwrite(photo_path, prev_frame)

    cap.release()
    print(f"\n\nExtracted {photo_index} photos to {output_folder}")


def main():
    parser = argparse.ArgumentParser(description="Extract photos with borders from videos in a directory.")
    parser.add_argument(
        "input_directory",
        help="Path to the directory containing videos (can be relative or absolute).",
    )
    parser.add_argument(
        "-o",
        "--output_subdirectory",
        default="extracted_photos",
        help="Name of the subdirectory to store extracted photos (default: 'extracted_photos').",
    )
    parser.add_argument(
        "-s", "--step_time", type=float, default=1.0, help="Time interval (in seconds) to skip between frames."
    )
    parser.add_argument(
        "-t", "--ssim_threshold", type=float, default=0.98, help="Threshold for SSIM similarity."
    )

    args = parser.parse_args()

    # Resolve input directory to an absolute path
    input_directory = os.path.abspath(args.input_directory)

    # Create the output directory as a subdirectory of the input directory
    output_directory = os.path.join(input_directory, args.output_subdirectory)
    os.makedirs(output_directory, exist_ok=True)

    print(f"Processing videos in: {input_directory}")
    print(f"Output photos will be saved in: {output_directory}")

    # Process the videos in the input directory
    process_videos_in_directory(
        input_directory=input_directory,
        output_directory=output_directory,
        step_time=args.step_time,
        ssim_threshold=args.ssim_threshold,
    )
