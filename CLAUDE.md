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
uv run python -m extract_photos.main "/path/to/videos" -s 1.0 -b 10 --min-photo-pct 25 --no-include-text

# Run on remote host (single video, default: immich_lxc)
epm input_file=/data/videos/sunset.mp4 output_dir=/data/photos

# Run on a different remote host
epm input_file=/data/videos/sunset.mp4 host=media_vm

# Run type checking
uv run pyright

# Run Python tests (fast unit tests only)
uv run pytest tests/

# Run slow integration tests (requires test videos in test-videos/test-video-*/)
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
2. **Scan** — Static-first architecture: single-threaded scan of the low-res copy steps through frames at `step_time`
   intervals and first identifies **static segments** — contiguous runs where consecutive frames are pixel-identical
   (Mean Absolute Difference < 0.5, `STATIC_MAD_THRESHOLD`). Segments shorter than `min_photo_duration` (default 0.5s)
   are discarded. Each surviving segment also tracks its average MAD across all frame pairs; when
   `require_borders` is False, segments with average MAD above `BORDERLESS_MAD_THRESHOLD` (0.25) are rejected — this
   filters talking-head frames (avg MAD 0.27–0.48) while keeping real photos (avg MAD 0.001–0.22). When borders are
   required, border detection alone is sufficient so the MAD threshold is not applied. Each surviving segment is then
   tested for uniform borders via `detect_almost_uniform_borders()` (supports three independently-toggleable patterns:
   all-4-borders uniform, pillarbox left+right borders, letterbox top+bottom borders — each pattern detects both black
   and white borders). Near-uniform frames (black/white screens) are rejected, and perceptual hashing deduplicates
   photos using two thresholds: tight (`HASH_STEP_THRESHOLD` 3) for
   segments separated by a single non-static frame (codec keyframe artifacts that split one photo into two segments),
   and wider (`HASH_DIFF_THRESHOLD` 10) for segments separated by sustained non-static content. Hash state resets after
   2+ consecutive non-static frames, or after a single non-static frame with MAD above `SCENE_CHANGE_MAD_THRESHOLD`
   (5.0) — this distinguishes real scene changes (MAD 5+) from codec keyframe artifacts (MAD 0.5–2.0). A single
   low-MAD non-static frame preserves the hash so the same photo isn't extracted twice.
   Collects timestamps of unique photos.
3. **Extract** — Opens the original full-res video, seeks to each discovered timestamp, runs border trimming and
   validation (minimum area as % of frame, near-uniform, screenshot detection), saves as JPEG.

Key modules in `extract_photos/`:

- **main.py** - Entry point. Parses args (`input_directory`, `-o`, `-s`, `-b`, `--min-photo-pct`,
  `--include-text`/`--no-include-text`, `--min-photo-duration`, `--detect-all-borders`/`--no-detect-all-borders`,
  `--detect-pillarbox`/`--no-detect-pillarbox`, `--detect-letterbox`/`--no-detect-letterbox`,
  `--require-borders`/`--no-require-borders`), creates output dir,
  calls batch processor.
- **batch_processor.py** - Scans directory for video files (.mp4/.mkv/.avi/.mov/.webm), creates per-video output
  subdirectories, calls extractor for each. Prompts skip-or-overwrite when a video's output directory already contains
  extracted photos (detected by presence of both `.jpg` and video files).
- **extract.py** - Core logic. `_is_vaapi_available()` detects VAAPI hardware acceleration at runtime (checks for
  `/dev/dri/renderD128` then runs a minimal ffmpeg probe; cached per process). `_lowres_encode_args()` always returns
  software encoding arguments (VAAPI `hwupload` overhead exceeds savings at 320px on shared-memory iGPUs).
  `_playback_encode_args()` returns VAAPI or software arguments depending on availability.
  `transcode_lowres()` creates the low-res temp file via ffmpeg. `scan_for_photos()` implements the static-first scan:
  tracks pixel-level MAD between consecutive frames to find static segments, filters by minimum duration, then applies
  border detection and hash dedup to candidates. `STATIC_MAD_THRESHOLD = 0.5` defines pixel-identity.
  Per-segment average MAD is tracked and used as a quality filter when `require_borders=False`
  (`BORDERLESS_MAD_THRESHOLD = 0.25`) to reject near-threshold segments like talking heads.
  `extract_fullres_frames()` seeks to each timestamp in the original video. `_rejection_reason()` validates extracted
  frames: checks minimum area (as % of video frame area, default 25%, tunable via `--min-photo-pct`), rejects
  near-uniform frames via `_is_near_uniform()` (grayscale std dev < 5.0), and rejects screenshots via `_is_screenshot()`
  (two-stage: first rejects images with >40% near-white pixels AND low color diversity (mean channel difference <15)
  as UI screens — the dual requirement prevents false positives on backlit photos with bright skies;
  then rejects images with <100 quantized colors at 128x128; skips effectively-grayscale images for the color-count
  stage using mean channel difference < 10). `get_video_metadata()` returns `(fps, duration_sec, width, height)`.
  `transcode_for_playback()` transcodes video to H.264/MP4 for Immich compatibility with a progress bar (or copies if
  already H.264/HEVC); includes explicit `fsync` after writing plus verification (existence + non-zero size) to ensure
  NFS persistence.
  `extract_photos_from_video()` orchestrates all three extraction phases.
- **transcode_playback.py** - Thin CLI wrapper for `transcode_for_playback()`. Called by `bin/epm` to copy/transcode the
  video with progress display.
- **borders.py** - `trim_and_add_border()`: scans inward from each edge to find content boundaries using per-row/column
  std deviation, then cross-validates each boundary using perpendicular content strips — if rows/cols just past the
  boundary differ in mean from the reference border color (sampled from image corners), the boundary expands outward.
  This prevents dark photo content (low std but different mean from border) from being misclassified as border.
  Validation only activates when perpendicular borders exist (>10px), so pillarbox/letterbox layouts are unaffected.
  After trimming, detects text/watermarks near edges via `_detect_text_padding()` (looks for sparse-content →
  zero-density-gap → dense-content pattern in column/row density profiles). Behavior depends on `include_text`: when
  `False` (default), crops the text region out entirely and adds uniform `border_px` padding on all sides; when `True`,
  adds extra padding on edges with text (matching the gap width), default 5px on clean edges.
- **utils.py** - Photo validation, safe folder names, logging.
- **display_progress.py** - `format_time()`, `build_progress_bar()`, and `print_scan_progress()` for 3-line in-place
  terminal progress.
- **immich.py** - Standalone Immich integration script called by `bin/epm` after extraction. Triggers a library
  scan, polls for new assets (with early exit when poll count stabilises at zero),
  orders them (video first, photos sorted by timestamp), sets `dateTimeOriginal` on each asset (video gets its YouTube
  upload date via ffprobe or file mtime as fallback; photos get that base date plus their video offset), creates/reuses
  an album named after the video, adds assets in order, optionally shares the album, and optionally sends a Pushover
  notification. `immich_request()` includes retry logic with exponential backoff (2s, 4s, 8s, 16s, 32s) for transient
  connection errors (HTTP errors are re-raised immediately without retry); API calls are paced with brief delays to
  avoid overloading the server. Album sharing detects "already shared" via response body matching rather than assuming
  all HTTP 400s are benign. Log output includes `[HH:MM:SS]` timestamps for debugging. Uses stdlib (`urllib.request`, `urllib.parse`,
  `json`, `subprocess`, `os`, `datetime`) plus ffprobe for metadata. Can be run directly:
  `python extract_photos/immich.py --api-url ... --api-key ... --library-id ... --asset-path ... --video-filename ...`.
- **copy_to_nfs.py** - Copies files to NFS with fsync and verification for reliability. Called by `bin/epm` to copy
  extracted photos to the NFS destination. Each file is copied with `shutil.copy2()`, then `os.fsync()` is called to
  ensure NFS persistence, followed by verification (existence + non-zero size). Includes a small delay between copies
  to avoid overwhelming NFS. Reports per-file failures and exits non-zero if any copies fail.

**test-videos/** - Contains test video directories (`test-video-1/` through `test-video-5/`), each with a test video and
ground-truth timestamp files: `photo-timestamps.txt` (expected photos) and optionally `edge-cases.txt` (side-by-side
photos and similar sequential photos). `test-video-1` has white-bordered photos (all-4-borders uniform), `test-video-2`
has black pillarbox-bordered photos, `test-video-3` has white pillarbox-bordered photos, `test-video-4` has
`require_borders=false` photos, `test-video-5` has dark photo content near black borders (validates cross-validated
border expansion). Integration tests auto-discover all `test-video-*` directories and run parametrized across them.

**bin/epm** - Bash wrapper that SSHes into a remote host to run the tool on a single video. Accepts `host=NAME` to select
the target: `immich_lxc` (default, SSH host `immich`) or `media_vm` (SSH host `media`). Auto-installs repo/deps on first
run and auto-updates (`git pull` + `uv sync`) on subsequent runs. Arguments with special shell characters (e.g. `[]` in
filenames) must be quoted. Computes the sanitized output subdirectory name early (via `make_safe_folder_name`) and prompts
skip-or-overwrite if it already contains extracted photos. On overwrite, deletion of old files is deferred until after
extraction succeeds — old output is preserved as a safety net if extraction fails or finds no photos. Just before
copying new files, the old output directory is removed and an Immich library scan is triggered (so Immich detects the
removed files before new files are copied to the same paths); the Immich Integration phase triggers a second scan after
new files are in place.
Creates a temp dir with a symlink to bridge single-file input
to the tool's directory-based interface. After extraction, copies photos to NFS via `copy_to_nfs.py` (with fsync +
verification for reliability), then calls `immich.py` to scan the library, create an album, and optionally share it
(when output is `/mnt/nfs/photos/reference` and Immich env vars are set). Runs the extraction inside
a tmux session on the remote host for resilience: if the SSH connection drops (e.g. laptop lid close), tmux keeps the
process alive. Re-running the same epm command detects the existing tmux session and reattaches. The session name is
derived from the video path (`epm-<hash>`). After the extraction finishes, the tmux session waits for Enter so the user
can see the final output before the session closes. Requires tmux on the remote host (checked during auto-setup).
The script resolves symlinks to find the actual repo location, so it works correctly when symlinked from `/usr/local/bin/epm`.

## Logging structure

Logs are organized by video name with timestamps to preserve multiple runs:

```
Remote host:
~/extract-photos/logs/
  {video_name}/
    {timestamp}_console.log       # Console output (tmux pipe-pane)

Output directory (NFS):
{output}/{video_name}/
  logs/
    {timestamp}_{video_name}_extraction.log   # Python extraction log
    {timestamp}_console.log                   # Copy of console log

Local repo:
{repo}/logs/
  {timestamp}_{video_name}.log    # Console log copy
```

Logs older than 30 days are auto-cleaned on each run. Legacy `~/epm-logs/` directory is automatically removed.

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

## User shorthand commands

- **dcp** — "document, commit, push": 1. Update documentation (CLAUDE.md, README, docstrings, etc.) to reflect recent
  changes, 2. Commit the changes with a helpful commit message, 3. Push the repo to the remote.
