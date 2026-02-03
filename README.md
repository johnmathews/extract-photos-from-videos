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

Screenshots and UI screens from ad segments are now detected by counting unique quantized colors. The image is downscaled
to 128x128 and quantized to 32 levels per channel. Screenshots have flat UI regions with very few unique colors (4-30),
while real photos have natural color diversity (100+). Checked during full-res extraction (Phase 3).

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
   - It has uniform-color borders on all four sides.
   - It is not near-uniform (solid black/white or near-solid with codec noise).
   - It is sufficiently different from the previous extracted photo (perceptual hash deduplication).
   - The bordered content covers at least 25% of the video frame area (tunable via `--min-photo-pct`).
   - It is not a screenshot (has enough color diversity to be a real photo).
4. Borders are trimmed and replaced with a clean border matching the original color.
5. Output is organized into per-video subdirectories.

Supported video formats: `.mp4`, `.mkv`, `.avi`, `.mov`, `.webm`.

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
# Run all Python tests
uv run pytest tests/

# Run with verbose output
uv run pytest tests/ -v

# Shell tests for bin/epm argument parsing
bash tests/test_epm.sh
```

The Python tests use synthetic numpy arrays for image-processing logic and mocked HTTP responses for the Immich
integration.

**Test files:**

| File                      | Module            | What it tests                                                      |
| ------------------------- | ----------------- | ------------------------------------------------------------------ |
| `test_extract.py`         | `extract.py`      | Border detection, near-uniform rejection, screenshot detection, perceptual hashing, rejection pipeline |
| `test_utils.py`           | `utils.py`        | Folder name sanitization, photo validation, logger setup           |
| `test_borders.py`         | `borders.py`      | Border trimming and re-addition                                    |
| `test_display_progress.py`| `display_progress.py` | Time formatting, progress bar rendering                        |
| `test_immich.py`          | `immich.py`       | HTTP wrapper, polling, album CRUD, asset ordering, date handling, sharing, push notifications, CLI orchestration |
| `test_epm.sh`             | `bin/epm`         | Argument parsing, required/optional args, error messages (shell)   |

The untested code (`transcode_lowres`, `scan_for_photos`, `extract_fullres_frames`, `extract_photos_from_video`,
`batch_processor`, `main`) is orchestration that calls ffmpeg/ffprobe and does file I/O. Testing it would require real
video fixtures and mostly validate that OpenCV and ffmpeg work, not project logic.

## Remote extraction (`epm`)

`bin/epm` is a shell script that SSHes into a remote machine and runs the extraction tool on a single video file. The
repository and its dependencies are auto-installed on the remote on first run and auto-updated on subsequent runs.
Ctrl-C cancels both the local and remote processes (the SSH connection uses `-tt` to allocate a remote PTY, so signals
propagate correctly). Temporary working files are cleaned up automatically on exit.

### Prerequisites

`ssh media` must be configured and working (via `~/.ssh/config` or equivalent).

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
| `step_time=SECONDS` | `0.5`   | Seconds between sampled frames                           |
| `border_px=INT`     | `5`     | Border size in pixels to add around extracted photos     |
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
Set these environment variables on the media VM (e.g. in `~/.bashrc`):

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
