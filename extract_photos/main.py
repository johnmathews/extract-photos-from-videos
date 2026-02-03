#!/usr/bin/env python3

import argparse
import os

from extract_photos.batch_processor import process_videos_in_directory


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract photos with borders from videos in a directory."
    )
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
        "-s",
        "--step_time",
        type=float,
        default=0.4,
        help="Time interval (in seconds) to skip between frames.",
    )
    parser.add_argument(
        "-b",
        "--border_px",
        type=int,
        default=5,
        help="Border size in pixels to add around extracted photos (default: 5).",
    )
    parser.add_argument(
        "--min-photo-pct",
        type=int,
        default=25,
        help="Minimum photo area as %% of video frame area (default: 25). Photos smaller than this are rejected.",
    )

    args = parser.parse_args()

    # Resolve input directory to an absolute path
    input_directory = args.input_directory

    # Create the output directory as a subdirectory of the input directory
    output_directory = os.path.join(input_directory, args.output_subdirectory)
    os.makedirs(output_directory, exist_ok=True)

    print(f"\nProcessing videos in: {input_directory}")
    print(f"Output photos will be saved in: {output_directory}")

    print(f"step_time: {args.step_time}s")
    print(f"border_px: {args.border_px}")

    print()

    # Process the videos in the input directory
    process_videos_in_directory(
        input_directory=input_directory,
        output_directory=output_directory,
        step_time=args.step_time,
        border_px=args.border_px,
        min_photo_pct=args.min_photo_pct,
    )


if __name__ == "__main__":
    main()
