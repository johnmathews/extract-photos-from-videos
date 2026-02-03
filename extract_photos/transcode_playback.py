"""CLI wrapper for transcode_for_playback.

Transcodes a video to H.264/MP4 for Immich playback compatibility,
with a progress bar. Prints the output filename to stdout.

Usage: python -m extract_photos.transcode_playback VIDEO OUTPUT_DIR
"""

import argparse
import sys

from extract_photos.extract import transcode_for_playback


def main():
    parser = argparse.ArgumentParser(description="Transcode video to H.264/MP4 for playback compatibility")
    parser.add_argument("video_file", help="Path to the input video file")
    parser.add_argument("output_dir", help="Directory to write the output file")
    args = parser.parse_args()

    out_name = transcode_for_playback(args.video_file, args.output_dir)
    # Print basename to stdout for the caller to capture
    print(out_name)


if __name__ == "__main__":
    main()
