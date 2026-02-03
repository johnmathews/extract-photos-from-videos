import os
from datetime import datetime

from extract_photos.extract import extract_photos_from_video
from extract_photos.utils import make_safe_folder_name


def process_videos_in_directory(
    input_directory: str,
    output_directory: str,
    step_time: int,
    border_px: int = 5,
    **kwargs,
):
    """
    Processes all videos in the specified directory. For each video, it creates a subdirectory
    named after the video's filename and extracts photos into that folder.

    Parameters:
    - input_directory: Path to the directory containing videos.
    - output_directory: Path to the directory where extracted photos will be stored.
    - kwargs: Additional arguments for `extract_photos_from_video`.
    """
    # Ensure the output directory exists
    os.makedirs(output_directory, exist_ok=True)

    video_files = []

    video_file_extensions = (".mp4", ".mkv", ".avi", ".mov", ".webm")
    # Iterate over all files in the input directory
    for filename in os.listdir(input_directory):
        # Skip if it's not a file or doesn't have a video file extension
        if filename.lower().endswith(video_file_extensions):
            video_files.append(filename)

    if not video_files:
        print("🛑 Found 0 video files. Stopping.")
        return

    print(f"\033[93mFound {len(video_files)} videos...\033[0m")
    for video in video_files:
        print(f"\033[94m- {video}\033[0m")

    # Iterate over all files in the input directory
    for filename in video_files:
        # Create a subdirectory named after the video
        video_name = os.path.splitext(filename)[0]
        subfolder = make_safe_folder_name(video_name)
        video_output_directory = os.path.join(output_directory, subfolder)
        os.makedirs(video_output_directory, exist_ok=True)

        input_path = os.path.join(input_directory, filename)

        print(
            f"\n\033[93m{datetime.now().strftime('%H:%M:%S')} Processing video: \033[94m{filename}\033[0m"
        )

        # Extract photos from the video
        extract_photos_from_video(
            video_file=input_path,
            output_folder=video_output_directory,
            step_time=step_time,
            filename=filename,
            border_px=border_px,
        )

    print(
        f"{datetime.now().strftime('%H:%M:%S')} ✨ Finished processing {len(video_files)} videos ✨"
    )
