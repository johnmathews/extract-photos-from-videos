# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project does

Extracts still photographs (with solid-color borders) from video files. Designed for studying photographers' work shown in YouTube videos. The tool transcodes each video to low resolution, scans for photo frames, then extracts full-res frames at discovered timestamps. Deduplicates using perceptual hashing and saves as JPEGs.

## Commands

```bash
# Run the tool locally
uv run python extract_photos/main.py "/path/to/video/directory"

# Run with options
uv run python extract_photos/main.py "/path/to/videos" -s 1.0 -t 0.95 -b 10

# Run on remote media VM (single video)
epm input_file=/data/videos/sunset.mp4 output_dir=/data/photos

# Run Python tests
uv run pytest tests/

# Run shell tests for bin/epm
bash tests/test_epm.sh

# Install dependencies
uv sync

# Build standalone executable
pyinstaller main.spec
```

## Architecture

**Processing pipeline:** `main.py` (CLI) -> `batch_processor.py` (discover videos, iterate) -> `extract.py` (three-phase: transcode, scan, extract)

Each video goes through three phases:
1. **Transcode** — ffmpeg creates a 320px-wide low-res temp copy (no audio).
2. **Scan** — Single-threaded scan of the low-res copy. Steps through frames at `step_time` intervals, detects uniform borders, deduplicates via perceptual hashing. Collects timestamps of unique photos.
3. **Extract** — Opens the original full-res video, seeks to each discovered timestamp, runs border trimming and validation, saves as JPEG.

Key modules in `extract_photos/`:

- **main.py** - Entry point. Parses args (`input_directory`, `-o`, `-s`, `-t`, `-b`), creates output dir, calls batch processor.
- **batch_processor.py** - Scans directory for video files (.mp4/.mkv/.avi/.mov/.webm), creates per-video output subdirectories, calls extractor for each.
- **extract.py** - Core logic. `transcode_lowres()` creates the low-res temp file via ffmpeg. `scan_for_photos()` scans it single-threaded with progress display. `extract_fullres_frames()` seeks to each timestamp in the original video. `extract_photos_from_video()` orchestrates all three phases.
- **borders.py** - `trim_and_add_border()`: scans inward from each edge to find content boundaries using per-row/column std deviation, crops original borders, adds new fixed-pixel border (default 5px).
- **utils.py** - SSIM calculation (via scikit-image), photo validation, safe folder names, logging.
- **display_progress.py** - `format_time()`, `build_progress_bar()`, and `print_scan_progress()` for 3-line in-place terminal progress.

**bin/epm** - Bash wrapper that SSHes into `media` VM to run the tool on a single video. Auto-installs repo/deps on first run and auto-updates (`git pull` + `uv sync`) on subsequent runs. Arguments with special shell characters (e.g. `[]` in filenames) must be quoted. Creates a temp dir with a symlink to bridge single-file input to the tool's directory-based interface. Optionally triggers an Immich library rescan after extraction if `IMMICH_API_KEY` and `IMMICH_LIBRARY_ID` env vars are set on the remote.

## Output structure

The tool creates `extracted_photos/` inside the input directory, with subdirectories per video. Photos are named with video name + timestamp. Each video subdirectory also has a `logs/` folder with a single log file per video.

## Dependencies

Requires Python >=3.13 and ffmpeg (for low-res transcoding). Uses `uv` for dependency management. Key libraries: opencv-python (video/image I/O), scikit-image (SSIM), numpy.

## Code style

Line length: 120 (configured for black, flake8, pyright in pyproject.toml).
