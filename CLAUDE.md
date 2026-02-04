# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project does

Extracts still photographs (with solid-color borders) from video files. Designed for studying photographers' work shown
in YouTube videos. The tool transcodes each video to low resolution, scans for photo frames, then extracts full-res
frames at discovered timestamps. Deduplicates using perceptual hashing and saves as JPEGs.

## Commands

```bash
# Run the tool locally
uv run python -m extract_photos.main "/path/to/video/directory"

# Run with options
uv run python -m extract_photos.main "/path/to/videos" -s 1.0 -b 10 --min-photo-pct 25

# Run on remote host (single video, default: media_vm)
epm input_file=/data/videos/sunset.mp4 output_dir=/data/photos

# Run on a different remote host
epm input_file=/data/videos/sunset.mp4 host=immich_lxc

# Run type checking
uv run pyright

# Run Python tests (fast unit tests only)
uv run pytest tests/

# Run slow integration tests (requires test video in test-video/)
uv run pytest tests/test_video_integration.py -m slow

# Run shell tests for bin/epm
bash tests/test_epm.sh

# Install dependencies
uv sync

# Enable pre-commit hook (runs tests before each commit)
git config core.hooksPath .githooks
```

## Architecture

**Processing pipeline:** `main.py` (CLI) -> `batch_processor.py` (discover videos, iterate) -> `extract.py` (three-phase:
transcode, scan, extract)

Each video goes through three phases:

1. **Transcode** — ffmpeg creates a 320px-wide low-res temp copy (no audio). Always uses software encoding (VAAPI
   overhead exceeds savings at 320px).
2. **Scan** — Single-threaded scan of the low-res copy. Steps through frames at `step_time` intervals, detects uniform
   borders, rejects near-uniform frames (black/white screens), deduplicates via perceptual hashing. Uses both
   step-to-step comparison (threshold 3, detects back-to-back photo transitions) and first-detection comparison
   (threshold 10, detects photos separated by non-photo content). Resets hash state when transitioning from photo to
   non-photo frames. Collects timestamps of unique photos.
3. **Extract** — Opens the original full-res video, seeks to each discovered timestamp, runs border trimming and
   validation (minimum area as % of frame, near-uniform, screenshot detection), saves as JPEG.

Key modules in `extract_photos/`:

- **main.py** - Entry point. Parses args (`input_directory`, `-o`, `-s`, `-b`, `--min-photo-pct`,
  `--include-text`/`--no-include-text`), creates output dir, calls batch processor.
- **batch_processor.py** - Scans directory for video files (.mp4/.mkv/.avi/.mov/.webm), creates per-video output
  subdirectories, calls extractor for each. Prompts skip-or-overwrite when a video's output directory already contains
  extracted photos (detected by presence of both `.jpg` and video files).
- **extract.py** - Core logic. `_is_vaapi_available()` detects VAAPI hardware acceleration at runtime (checks for
  `/dev/dri/renderD128` then runs a minimal ffmpeg probe; cached per process). `_lowres_encode_args()` always returns
  software encoding arguments (VAAPI `hwupload` overhead exceeds savings at 320px on shared-memory iGPUs).
  `_playback_encode_args()` returns VAAPI or software arguments depending on availability.
  `transcode_lowres()` creates the low-res temp file via ffmpeg. `scan_for_photos()` scans it single-threaded with
  progress display, rejecting near-uniform frames (black/white screens) before hashing.
  `extract_fullres_frames()` seeks to each timestamp in the original video. `_rejection_reason()` validates extracted
  frames: checks minimum area (as % of video frame area, default 25%, tunable via `--min-photo-pct`), rejects
  near-uniform frames via `_is_near_uniform()` (grayscale std dev < 5.0), and rejects screenshots via `_is_screenshot()`
  (two-stage: first rejects images with >30% near-white pixels as UI screens via `_white_background_percentage()`;
  then rejects images with <100 quantized colors at 128x128; skips effectively-grayscale images for the color-count
  stage using mean channel difference < 10). `get_video_metadata()` returns `(fps, duration_sec, width, height)`.
  `transcode_for_playback()` transcodes video to H.264/MP4 for Immich compatibility with a progress bar (or copies if
  already H.264/HEVC). `extract_photos_from_video()` orchestrates all three extraction phases.
- **transcode_playback.py** - Thin CLI wrapper for `transcode_for_playback()`. Called by `bin/epm` to copy/transcode the
  video with progress display.
- **borders.py** - `trim_and_add_border()`: scans inward from each edge to find content boundaries using per-row/column
  std deviation, crops original borders, detects text/watermarks near edges via `_detect_text_padding()` (looks for
  sparse-content → zero-density-gap → dense-content pattern in column/row density profiles). Behavior depends on
  `include_text`: when `True` (default), adds extra padding on edges with text (matching the gap width), default 5px on
  clean edges; when `False`, crops the text region out entirely and adds uniform `border_px` padding on all sides.
- **utils.py** - Photo validation, safe folder names, logging.
- **display_progress.py** - `format_time()`, `build_progress_bar()`, and `print_scan_progress()` for 3-line in-place
  terminal progress.
- **immich.py** - Standalone Immich integration script called by `bin/epm` after extraction. First purges any existing
  assets (including trashed) at the target path via `purge_existing_assets()` to prevent stale records from blocking
  re-import. Then triggers a library scan, polls for new assets (with early exit when poll count stabilises at zero),
  orders them (video first, photos sorted by timestamp), sets `dateTimeOriginal` on each asset (video gets its YouTube
  upload date via ffprobe or file mtime as fallback; photos get that base date plus their video offset), creates/reuses
  an album named after the video, adds assets in order, optionally shares the album, and optionally sends a Pushover
  notification. Uses stdlib (`urllib.request`, `urllib.parse`, `json`, `subprocess`, `os`, `datetime`) plus ffprobe for
  metadata. Can be run directly:
  `python extract_photos/immich.py --api-url ... --api-key ... --library-id ... --asset-path ... --video-filename ...`.

**test-video/** - Contains a test video and ground-truth timestamp files: `photo-timestamps.txt` (standard single photos)
and `edge-cases.txt` (side-by-side photos and similar sequential photos). Used by the slow integration tests in
`tests/test_video_integration.py`.

**bin/epm** - Bash wrapper that SSHes into a remote host to run the tool on a single video. Accepts `host=NAME` to select
the target: `media_vm` (default, SSH host `media`) or `immich_lxc` (SSH host `immich`). Auto-installs repo/deps on first
run and auto-updates (`git pull` + `uv sync`) on subsequent runs. Arguments with special shell characters (e.g. `[]` in
filenames) must be quoted. Computes the sanitized output subdirectory name early (via `make_safe_folder_name`) and prompts
skip-or-overwrite if it already contains extracted photos. Creates a temp dir with a symlink to bridge single-file input
to the tool's directory-based interface. After extraction, calls `immich.py` to scan the library, create an album, and
optionally share it (when output is `/mnt/nfs/photos/reference` and Immich env vars are set).

## Output structure

The tool creates `extracted_photos/` inside the input directory, with subdirectories per video. Photos are named with
video name + timestamp. Each video subdirectory also has a `logs/` folder with a single log file per video.

## Hardware acceleration

`transcode_for_playback()` automatically uses VAAPI hardware encoding when a compatible GPU is available (e.g. Ryzen 5
Pro 4650G Vega iGPU on the Immich LXC). Detection is zero-config: checks for `/dev/dri/renderD128`, verifies with a
minimal ffmpeg probe, and caches the result per process. On hosts without a GPU (e.g. media VM), the existing software
pipeline (`libx264`) runs unchanged. The approach is software decode + hwupload + VAAPI scale/encode (`h264_vaapi` +
`scale_vaapi`), which works regardless of input codec (important for YouTube AV1 videos that can't be HW-decoded on
Vega).

`transcode_lowres()` always uses software encoding. At 320px output, H.264 encoding is trivially cheap on CPU — the
VAAPI overhead (format conversion, `hwupload` memory transfer, GPU encode, sync) adds latency that exceeds the encoding
time saved, especially on shared-memory iGPUs where `hwupload` competes for memory bandwidth with CPU decode.

## Dependencies

Requires Python >=3.13 and ffmpeg (for low-res transcoding). Uses `uv` for dependency management. Key libraries:
opencv-python (video/image I/O), numpy.

## Code style

Line length: 120 (configured for black, flake8 in pyproject.toml). All functions have type annotations; pyright is
configured in standard mode, scoped to `extract_photos/` via `include` (`uv run pyright`). Numpy/opencv stub false
positives are suppressed with inline `# type: ignore` comments.
