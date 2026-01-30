# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project does

Extracts still photographs (with solid-color borders) from video files. Designed for studying photographers' work shown in YouTube videos. The tool processes videos in parallel, detects frames showing bordered photos, deduplicates using SSIM, and saves them as JPEGs.

## Commands

```bash
# Run the tool locally
uv run python extract_photos/main.py "/path/to/video/directory"

# Run with options
uv run python extract_photos/main.py "/path/to/videos" -s 1.0 -t 0.95

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

**Processing pipeline:** `main.py` (CLI) -> `batch_processor.py` (discover videos, iterate) -> `extract.py` (parallel chunk processing via `multiprocessing.Pool`)

Key modules in `extract_photos/`:
- **main.py** - Entry point. Parses args (`input_directory`, `-o`, `-s`, `-t`), creates output dir, calls batch processor.
- **batch_processor.py** - Scans directory for video files (.mp4/.mkv/.avi/.mov/.webm), creates per-video output subdirectories, calls parallel extractor for each.
- **extract.py** - Core logic. Divides video into chunks (cpu_count // 4), processes in parallel. Each chunk: samples frames at `step_time` intervals, detects uniform borders, compares via SSIM, validates dimensions (1000x1000 min), saves photos.
- **borders.py** - `trim_and_add_border()`: detects border color from top-left region, crops original borders, adds new 5% border.
- **utils.py** - SSIM calculation (via scikit-image), photo validation, safe folder names, per-chunk logging.
- **display_progress.py** - Real-time terminal progress display using ANSI escape codes, updated per-chunk.

**bin/epm** - Bash wrapper that SSHes into `media` VM to run the tool on a single video. Auto-installs repo/deps on first run and auto-updates (`git pull` + `uv sync`) on subsequent runs. Arguments with special shell characters (e.g. `[]` in filenames) must be quoted. Creates a temp dir with a symlink to bridge single-file input to the tool's directory-based interface.

## Output structure

The tool creates `extracted_photos/` inside the input directory, with subdirectories per video. Photos are named with video name + timestamp. Each video subdirectory also has a `logs/` folder with per-chunk log files.

## Dependencies

Requires Python >=3.13. Uses `uv` for dependency management. Key libraries: opencv-python (video/image I/O), scikit-image (SSIM), numpy.

## Code style

Line length: 120 (configured for black, flake8, pyright in pyproject.toml).
