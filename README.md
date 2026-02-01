# Photograph Extractor

Extract still photographs from video files. The tool detects frames that display
a photograph with a solid-color border (e.g. white), deduplicates them, and
saves each as a JPEG.

Built for studying other photographers' work from YouTube videos -- view photos
at your own pace, in any order, and annotate them.

## How it works

1. Point the tool at a directory containing one or more video files.
2. Each video goes through a three-phase pipeline:
   - **Transcode** — ffmpeg creates a 320px-wide low-res copy for fast scanning.
   - **Scan** — The low-res copy is scanned single-threaded at a configurable
     interval (default: every 0.5 seconds). Frames with uniform borders are
     detected and deduplicated using perceptual hashing.
   - **Extract** — Only the frames identified as photos are decoded from the
     original full-resolution video, trimmed, validated, and saved.
3. A frame is extracted as a photo when:
   - It has uniform-color borders on all four sides.
   - It is sufficiently different from the previous extracted photo (perceptual
     hash deduplication).
   - The bordered content is at least 1000x1000 pixels.
4. Borders are trimmed and replaced with a clean border matching the original
   color.
5. Output is organized into per-video subdirectories.

Supported video formats: `.mp4`, `.mkv`, `.avi`, `.mov`, `.webm`.

## Setup

Requires Python >= 3.13, [uv](https://github.com/astral-sh/uv), and
[ffmpeg](https://ffmpeg.org/).

```bash
git clone https://github.com/johnmathews/extract-photos-from-videos.git
cd extract-photos
uv sync
```

## Usage

```bash
uv run python extract_photos/main.py INPUT_DIR [options]
```

### Arguments

| Argument    | Description                      |
| ----------- | -------------------------------- |
| `INPUT_DIR` | Directory containing video files |

### Options

| Option                      | Default            | Description                                               |
| --------------------------- | ------------------ | --------------------------------------------------------- |
| `-o, --output_subdirectory` | `extracted_photos` | Name of the output subdirectory within `INPUT_DIR`        |
| `-s, --step_time`           | `0.5`              | Seconds between sampled frames                            |
| `-t, --ssim_threshold`      | `0.90`             | SSIM threshold for deduplication (0-1, higher = stricter) |
| `-b, --border_px`           | `5`                | Border size in pixels to add around extracted photos      |

### Examples

```bash
# Process all videos in a directory
uv run python extract_photos/main.py ~/Videos

# Slower sampling, stricter deduplication
uv run python extract_photos/main.py ~/Videos -s 1.0 -t 0.95
```

### Shell function

To run from anywhere without activating the virtualenv, add to your
`~/.zshrc` or `~/.bashrc`:

```bash
extract_photos() {
    (source /path/to/extract-photos/.venv/bin/activate && \
     uv run python /path/to/extract-photos/extract_photos/main.py "$@")
}
```

## Output structure

```
INPUT_DIR/
  extracted_photos/
    video-name/
      video-name_0m30s.jpg
      video-name_2m15s.jpg
      logs/
        video-name.log
    another-video/
      ...
```

Each photo filename includes the video name and the timestamp where it was
found. A single log file per video records detailed extraction decisions.

## Testing

```bash
# Python unit tests (utils, borders, border detection, Immich integration)
uv run pytest tests/ -v

# Shell tests for bin/epm argument parsing
bash tests/test_epm.sh
```

The Python tests use synthetic numpy arrays for image-processing logic, and
mocked HTTP responses for the Immich integration. The tested pure functions
(`make_safe_folder_name`, `is_valid_photo`, `calculate_ssim`,
`detect_almost_uniform_borders`, `trim_and_add_border`) are where the core
detection logic lives. The Immich module (`immich.py`) is tested at 92%
coverage, covering the HTTP wrapper, polling, album creation, asset addition,
user lookup, sharing, and the CLI orchestration.

The untested code (`transcode_lowres`, `scan_for_photos`,
`extract_fullres_frames`, `extract_photos_from_video`, `batch_processor`,
`main`) is orchestration -- transcoding, scanning, seeking, and file I/O.
Testing that with real video files would be an integration test: slow, requiring
test fixtures, and mostly validating that OpenCV and ffmpeg work rather than
project logic.

## Remote extraction (`epm`)

`bin/epm` is a shell script that SSHes into a remote machine and runs the
extraction tool on a single video file. The repository and its dependencies are
auto-installed on the remote on first run and auto-updated on subsequent runs.

### Prerequisites

`ssh media` must be configured and working (via `~/.ssh/config` or equivalent).

### Installation

Symlink the script into a directory on your PATH so it can be run from any
shell:

```bash
ln -s "$(pwd)/bin/epm" /usr/local/bin/epm
```

Run this from the root of the repository. After that, `epm` is available
globally. The symlink points back to the repo, so updates to the script take
effect immediately.

### Usage

```bash
epm input_file=VIDEO output_dir=DIR [options]
```

| Argument          | Description                                                   |
| ----------------- | ------------------------------------------------------------- |
| `input_file=PATH` | Path to a video file on the remote machine                    |
| `output_dir=PATH` | Directory on the remote machine to copy extracted photos into |

| Option                 | Default | Description                                               |
| ---------------------- | ------- | --------------------------------------------------------- |
| `step_time=SECONDS`    | `0.5`   | Seconds between sampled frames                            |
| `ssim_threshold=FLOAT` | `0.90`  | SSIM threshold for deduplication (0-1, higher = stricter) |
| `border_px=INT`        | `5`     | Border size in pixels to add around extracted photos      |
| `update_immich=BOOL`   | `true`  | Run Immich integration (rescan, album creation, sharing)  |
| `help`                 |         | Show usage                                                |

### Example Commands

```bash
epm input_file=/data/videos/sunset.mp4 output_dir=/data/photos
epm input_file=/data/videos/sunset.mp4 output_dir=/data/photos step_time=1.0 ssim_threshold=0.95

# Quote arguments containing shell special characters (e.g. brackets)
epm input_file="/data/videos/video-[abc123].mkv" output_dir=/data/photos
```

### Immich integration

After extracting photos, `epm` can automatically create an
[Immich](https://immich.app/) album containing the new photos. Set these
environment variables on the media VM (e.g. in `~/.bashrc`):

| Variable           | Required | Description                                            |
| ------------------ | -------- | ------------------------------------------------------ |
| `IMMICH_API_KEY`   | Yes      | API key (create in Immich under Account Settings)      |
| `IMMICH_LIBRARY_ID`| Yes      | External library ID to rescan                          |
| `IMMICH_API_URL`   | Yes      | Immich server URL (e.g. `http://localhost:2283`)       |
| `IMMICH_SHARE_USER`| No       | Immich username to share created albums with           |

If all three required variables are set and the output directory is the
default (`/mnt/nfs/photos/reference`), `epm` will:

1. Trigger a library rescan so Immich indexes the new files.
2. Wait for the new assets to appear (polls every 5s, up to 5 minutes).
3. Parse the video filename into an album name (e.g.
   `Willem Verbeeck - Shooting Los Angeles on 8x10 Film`).
4. Create a shared album (or reuse an existing one with the same name).
5. Add the new assets to the album.
6. If `IMMICH_SHARE_USER` is set, share the album with that user as an editor.

If any required variables are unset, the reason is shown in the output. To
disable the integration entirely, pass `update_immich=false`.
