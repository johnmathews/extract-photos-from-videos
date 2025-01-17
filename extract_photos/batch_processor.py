import os

from extract import extract_photos_from_video
from utils import make_safe_folder_name


def process_videos_in_directory(input_directory: str, output_directory: str, **kwargs):
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
        file_path = os.path.join(input_directory, filename)

        # Skip if it's not a file or doesn't have a video file extension
        if filename.lower().endswith(video_file_extensions):
            video_files.append(filename)

    # Iterate over all files in the input directory
    for filename in video_files:
        # Create a subdirectory named after the video
        video_name = os.path.splitext(filename)[0]
        subfolder = make_safe_folder_name(video_name)
        video_output_directory = os.path.join(output_directory, subfolder)
        os.makedirs(video_output_directory, exist_ok=True)

        print(f"Processing video: {filename}")

        # Extract photos from the video
        extract_photos_from_video(video_file=input_path, output_folder=video_output_directory, **kwargs)

    print(f"Finished processing videos in directory: {input_directory}")
