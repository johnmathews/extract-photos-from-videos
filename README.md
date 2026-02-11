# Photograph Extractor

Extract still photographs from video files. The tool detects frames that display a photograph with a solid-color border
(e.g. white), deduplicates them, and saves each as a JPEG.

Built for studying other photographers' work from YouTube videos -- view photos at your own pace, in any order, and
annotate them.

## Known issues

### 1. ~~Movie playback in Immich~~ (fixed)

Videos are now transcoded to H.264+AAC in MP4 (capped at 1080p, CRF 28, preset faster) before being copied to the
reference directory, unless the video codec is already H.264 or HEVC. The original full-quality file is preserved in the
movies directory.

### 2. ~~Some photos are not extracted from a video~~ (fixed)

Photos were being missed for two reasons: the minimum size filter required both dimensions >= 1000px (rejecting
landscape photos from 1080p video after border trimming), and the perceptual hash deduplication only compared against
the last *recorded* photo (missing back-to-back photo transitions in continuous sequences). Fixed by switching to a
proportional area threshold (default 25% of video frame area, tunable via `--min-photo-pct`) and adding step-to-step
hash comparison that detects when consecutive frames change, even within a continuous photo sequence. Edge cases like
side-by-side photos and visually similar sequential photos are covered by integration tests.

### 3. ~~Screenshots are not photos~~ (fixed)

Screenshots and UI screens from ad segments are now detected with a two-stage approach. Stage 1 requires all three of:
many straight H/V lines (UI chrome), high white-pixel percentage, and low color diversity — this catches white-background
UI while avoiding false positives on high-key B&W photographs and backlit sky photos. Stage 2 counts unique quantized
colors to catch flat-color UI blocks. See [Screenshot detection](#screenshot-detection) for details.

### 4. ~~Black screens or white screens are not photos~~ (fixed)

Near-uniform frames (solid color or near-solid with codec noise/slight gradients) are now rejected by checking the
grayscale standard deviation. Pure black/white frames have std ~0, codec noise gives std ~1-3, while even the darkest
real photo has std > 15. Checked during both scanning (Phase 2) and full-res extraction (Phase 3).

## How it works

1. Point the tool at a directory containing one or more video files.
2. Each video goes through a three-phase pipeline:
   - **Transcode** — ffmpeg creates a 320px-wide low-res copy for fast scanning.
   - **Scan** — The low-res copy is scanned single-threaded at a configurable interval (default: every 0.5 seconds).
     Frames with uniform borders are detected and deduplicated using perceptual hashing.
   - **Extract** — Only the frames identified as photos are decoded from the original full-resolution video, trimmed,
     validated, and saved.
3. A frame is extracted as a photo when:
   - It has uniform-color borders (all four sides, or pillarbox/letterbox with black side/top-bottom borders).
   - It is not near-uniform (solid black/white or near-solid with codec noise).
   - It is sufficiently different from the previous extracted photo (perceptual hash deduplication).
   - The bordered content covers at least 25% of the video frame area (tunable via `--min-photo-pct`).
   - It is not a screenshot (see [Screenshot detection](#screenshot-detection)).
4. Borders are trimmed and replaced with a clean border matching the original color. Cross-validation against
   perpendicular edges prevents dark photo content from being misclassified as border. If text/annotations are
   detected next to the photo, they are cropped out by default; use `--include-text` to keep them.
5. Output is organized into per-video subdirectories.

Supported video formats: `.mp4`, `.mkv`, `.avi`, `.mov`, `.webm`.

## Screenshot detection

Screenshots and UI screens (ad segments, template galleries, web pages) are rejected during Phase 3 (full-res
extraction) via `_is_screenshot()`. Detection uses two independent stages — a frame is rejected if **either** stage
triggers.

### Stage 1: White-background UI detection

Rejects images that satisfy **all three** conditions simultaneously:

| Signal | Threshold | What it measures |
| --- | --- | --- |
| Straight lines | `line_count_threshold = 10` | Near-horizontal/vertical lines detected by Canny edge detection + HoughLinesP on 128x128 grayscale. UI chrome (nav bars, buttons, table rows, card edges) produces 15-50+ lines; photos have organic shapes producing 0-8. |
| White pixels | `white_pct_threshold = 30.0%` | Percentage of pixels with brightness > 240 at 128x128. UI screens are typically 40-70% white; most photos are below 10%. |
| Color diversity | `color_var_threshold = 15.0` | Mean per-pixel channel difference across B-G, B-R, and G-R pairs. Near-grayscale UI has ch_diff 6-9; colour photos have ch_diff 15+. |

The triple requirement prevents false positives on:
- **High-key B&W photographs** — lots of white pixels and low color diversity, but organic shapes (0-8 straight lines)
- **Backlit sky/sunset photos** — high white-pixel percentage, but rich color gradients (ch_diff 15+)

**Line detection details** (`_count_hv_lines()`): Canny edges are computed on 128x128 grayscale with thresholds 50/150.
A 5% margin is cropped from each edge before detection to exclude the uniform border added by `trim_and_add_border()`.
HoughLinesP parameters: `threshold=30`, `minLineLength=20`, `maxLineGap=5`. Lines within 5 degrees of horizontal or
vertical are counted.

### Stage 2: Flat-color UI detection

Catches simple screenshots with large flat-colored blocks (solid buttons, panels, backgrounds) that may not have enough
white to trigger Stage 1.

| Parameter | Value | Description |
| --- | --- | --- |
| `color_count_threshold` | `100` | Minimum unique colors at 128x128 after quantization to 32 levels/channel |
| `sample_size` | `128` | Downscale resolution for analysis |

Simple screenshots have 4-30 unique quantized colors; real photos have 100+. This stage is skipped for
effectively-grayscale images (mean channel difference < 10) since B&W photos can't be reliably distinguished from
B&W screenshots using color count alone.

## Setup

Requires Python >= 3.13, [uv](https://github.com/astral-sh/uv), and [ffmpeg](https://ffmpeg.org/).

```bash
git clone https://github.com/johnmathews/extract-photos-from-videos.git
cd extract-photos
uv sync
git config core.hooksPath .githooks
```

The last command enables the pre-commit hook which runs tests automatically before each commit.

## Usage

```bash
uv run python -m extract_photos.main INPUT_DIR [options]
```

### Arguments

| Argument    | Description                      |
| ----------- | -------------------------------- |
| `INPUT_DIR` | Directory containing video files |

### Options

| Option                      | Default            | Description                                          |
| --------------------------- | ------------------ | ---------------------------------------------------- |
| `-o, --output_subdirectory` | `extracted_photos` | Name of the output subdirectory within `INPUT_DIR`   |
| `-s, --step_time`           | `0.5`              | Seconds between sampled frames                       |
| `-b, --border_px`           | `5`                | Border size in pixels to add around extracted photos |
| `--min-photo-pct`           | `25`               | Minimum photo area as % of video frame area          |
| `--min-photo-duration`      | `0.5`              | Minimum seconds a photo must persist on screen       |
| `--include-text` / `--no-include-text` | `no`    | Include text/annotations next to photos              |
| `--detect-all-borders` / `--no-detect-all-borders` | `yes` | Enable all-4-borders detection pattern     |
| `--detect-pillarbox` / `--no-detect-pillarbox` | `yes` | Enable pillarbox (left+right) border detection |
| `--detect-letterbox` / `--no-detect-letterbox` | `yes` | Enable letterbox (top+bottom) border detection |
| `--require-borders` / `--no-require-borders` | `yes` | Require uniform borders to detect photos. Set `--no-require-borders` for full-frame photos without borders |

### Examples

```bash
# Process all videos in a directory
uv run python -m extract_photos.main ~/Videos

# Slower sampling, larger borders
uv run python -m extract_photos.main ~/Videos -s 1.0 -b 10
```

### Shell function

To run from anywhere without activating the virtualenv, add to your `~/.zshrc` or `~/.bashrc`:

```bash
extract_photos() {
    (cd /path/to/extract-photos && \
     uv run python -m extract_photos.main "$@")
}
```

## Output structure

```
INPUT_DIR/
  extracted_photos/
    video-name/
      video-name_0m30s.jpg
      video-name_1m23.5s.jpg
      video-name_2m15s.jpg
      logs/
        video-name.log
    another-video/
      ...
```

Each photo filename includes the video name and the timestamp where it was found. Whole-second timestamps use the format
`5m04s`; sub-second timestamps include a decimal (`1m23.5s`) to avoid filename collisions when `step_time` is less than 1
second. A single log file per video records detailed extraction decisions.

## Testing

```bash
# Run fast unit tests
uv run pytest tests/

# Run slow integration tests (requires test videos in test-videos/test-video-*/)
uv run pytest tests/test_video_integration.py -m slow

# Run with verbose output
uv run pytest tests/ -v

# Shell tests for bin/epm argument parsing
bash tests/test_epm.sh
```

The unit tests use synthetic numpy arrays for image-processing logic and mocked HTTP responses for the Immich
integration. Integration tests run the full pipeline against real test videos and verify expected timestamps are
found.

**Test files:**

| File                      | Module            | What it tests                                                      |
| ------------------------- | ----------------- | ------------------------------------------------------------------ |
| `test_extract.py`         | `extract.py`      | Border detection, near-uniform rejection, screenshot detection, perceptual hashing, rejection pipeline |
| `test_utils.py`           | `utils.py`        | Folder name sanitization, photo validation, logger setup           |
| `test_borders.py`         | `borders.py`      | Border trimming and re-addition                                    |
| `test_display_progress.py`| `display_progress.py` | Time formatting, progress bar rendering                        |
| `test_immich.py`          | `immich.py`       | HTTP wrapper, polling, album CRUD, asset ordering, date handling, sharing, push notifications, CLI orchestration |
| `test_video_integration.py` | `extract.py`    | End-to-end: transcode, scan, extract against real test videos (slow, parametrized across test-video-1 through test-video-6) |
| `test_epm.sh`             | `bin/epm`         | Argument parsing, required/optional args, error messages (shell)   |

## Remote extraction (`epm`)

`bin/epm` is a shell script that SSHes into a remote machine and runs the extraction tool on a single video file. The
repository and its dependencies are auto-installed on the remote on first run and auto-updated on subsequent runs.
The extraction runs inside a **tmux session** on the remote host, so it survives SSH disconnections (e.g. closing the
laptop lid). If the connection drops, re-running the same `epm` command reattaches to the ongoing session. Ctrl-C while
attached cancels the extraction as before. After the extraction finishes, the session waits for Enter so you can see the
results before it closes. Temporary working files are cleaned up automatically on exit.

### Prerequisites

- `ssh immich` (default) or `ssh media` must be configured and working (via `~/.ssh/config` or equivalent).
- `tmux` must be installed on the remote host (checked automatically on each run).

### Installation

Symlink the script into a directory on your PATH so it can be run from any shell:

```bash
ln -s "$(pwd)/bin/epm" /usr/local/bin/epm
```

Run this from the root of the repository. After that, `epm` is available globally. The symlink points back to the repo,
so updates to the script take effect immediately.

### Usage

```bash
epm VIDEO [output_dir=DIR] [options]
epm input_file=VIDEO [output_dir=DIR] [options]
```

| Argument          | Description                                                   |
| ----------------- | ------------------------------------------------------------- |
| `VIDEO`           | Path to a video file on the remote machine (positional)       |
| `input_file=PATH` | Same, as a named argument                                     |
| `output_dir=PATH` | Directory on the remote machine to copy extracted photos into |

| Option              | Default | Description                                              |
| ------------------- | ------- | -------------------------------------------------------- |
| `host=NAME`         | `immich_lxc` | Remote host: `immich_lxc` (SSH host `immich`) or `media_vm` (SSH host `media`) |
| `step_time=SECONDS` | `0.5`   | Seconds between sampled frames                           |
| `border_px=INT`     | `5`     | Border size in pixels to add around extracted photos     |
| `min_photo_pct=INT` | `25`    | Minimum photo area as % of video frame area              |
| `min_photo_duration=FLOAT` | `0.5` | Minimum seconds a photo must persist on screen      |
| `detect_all_borders=BOOL` | `true` | Enable all-4-borders detection pattern              |
| `detect_pillarbox=BOOL` | `true` | Enable pillarbox (left+right) border detection        |
| `detect_letterbox=BOOL` | `true` | Enable letterbox (top+bottom) border detection        |
| `require_borders=BOOL` | `true` | Require uniform borders to detect photos. Set to `false` for full-frame photos |
| `include_text=BOOL` | `false` | Include text/annotations next to photos                  |
| `update_immich=BOOL`| `true`  | Run Immich integration (rescan, album creation, sharing) |
| `help`              |         | Show usage                                               |

### Example Commands

```bash
epm /data/videos/sunset.mp4
epm /data/videos/sunset.mp4 output_dir=/data/photos
epm /data/videos/sunset.mp4 step_time=1.0

# Quote arguments containing shell special characters (e.g. brackets)
epm "/data/videos/video-[abc123].mkv" output_dir=/data/photos
```

### Immich integration

After extracting photos, `epm` can automatically create an [Immich](https://immich.app/) album containing the new photos.
Set these environment variables on the remote host (e.g. in `~/.bashrc`):

| Variable             | Required | Description                                       |
| -------------------- | -------- | ------------------------------------------------- |
| `IMMICH_API_KEY`     | Yes      | API key (create in Immich under Account Settings) |
| `IMMICH_LIBRARY_ID`  | Yes      | External library ID to rescan                     |
| `IMMICH_API_URL`     | Yes      | Immich server URL (e.g. `http://localhost:2283`)  |
| `IMMICH_SHARE_USER`  | No       | Immich username to share created albums with      |
| `PUSHOVER_USER_KEY`  | No       | Pushover user key for notifications               |
| `PUSHOVER_APP_TOKEN` | No       | Pushover application API token                    |

If all three required variables are set and the output directory is the default (`/mnt/nfs/photos/reference`), `epm`
will:

1. Trigger a library rescan so Immich indexes the new files.
2. Wait for the new assets to appear (polls every 5s, up to 5 minutes).
3. Order assets: video first, then photos sorted by their timestamp in the video.
4. Set `dateTimeOriginal` on each asset so Immich's date sort matches the video timeline. The video gets its YouTube
   upload date (from embedded metadata) or the file's download time as a fallback. Photos get that base date plus their
   offset in the video.
5. Parse the video filename into an album name (e.g. `Willem Verbeeck - Shooting Los Angeles on 8x10 Film`).
6. Create a shared album (or reuse an existing one with the same name).
7. Add the ordered assets to the album.
8. If `IMMICH_SHARE_USER` is set, share the album with that user as an editor.
9. If `PUSHOVER_USER_KEY` and `PUSHOVER_APP_TOKEN` are set, send a push notification with the album name and extraction
   summary.

If any required variables are unset, the reason is shown in the output. To disable the integration entirely, pass
`update_immich=false`.

### Logging

`epm` maintains logs at three levels:

| Location | Content | Lifetime |
| --- | --- | --- |
| `logs/{timestamp}_{video}.log` (local, in repo) | Full console output copied from remote after each run | Permanent |
| `~/extract-photos/logs/{timestamp}_{video}/` (remote) | Console output captured via tmux `pipe-pane` | 30-day auto-cleanup |
| `{output}/{video}/logs/{timestamp}_console.log` (remote) | Copy of console output alongside extracted photos | Permanent |

Local log files are named like `2026-02-04_143000_sunset.log` (timestamp + sanitized video name). Remote log
directories use timestamped prefixes (`2026-02-04_143000_sunset/`) so each run gets its own directory.

## Architecture Documentation

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for diagrams showing:
- EPM control flow (main decision tree)
- Local ↔ remote sequence diagram (SSH/tmux interaction)
- Python pipeline detail (three-phase extraction)
- Function call graphs (manual, auto-generated, and UML)
