#!/usr/bin/env python3

import argparse
import os

from extract_photos.batch_processor import process_videos_in_directory


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
    parser.add_argument("-t", "--ssim_threshold", type=float, default=0.98, help="Threshold for SSIM similarity.")

    args = parser.parse_args()

    # Resolve input directory to an absolute path
    input_directory = args.input_directory

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

if __name__=="__main__":
    main()
