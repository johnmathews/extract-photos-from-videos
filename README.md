# Photograph Extractor

Extract still photographs from video files. The tool detects frames that display
a photograph with a solid-color border (e.g. white), deduplicates them, and
saves each as a JPEG.

Built for studying other photographers' work from YouTube videos -- view photos
at your own pace, in any order, and annotate them.

## How it works

1. Point the tool at a directory containing one or more video files.
2. Each video is split into chunks and processed in parallel using
   multiprocessing.
3. Frames are sampled at a configurable interval (default: every 0.5 seconds).
4. A frame is extracted as a photo when:
   - It has uniform-color borders on all four sides.
   - It is sufficiently different from the previous extracted photo (SSIM-based
     deduplication, default threshold: 0.90).
   - The bordered content is at least 1000x1000 pixels.
   - The frame is static (the same image is held for several frames).
5. Borders are trimmed and replaced with a clean border matching the original
   color.
6. Output is organized into per-video subdirectories.

Supported video formats: `.mp4`, `.mkv`, `.avi`, `.mov`, `.webm`.

## Setup

Requires Python >= 3.13 and [uv](https://github.com/astral-sh/uv).

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

| Argument | Description |
|----------|-------------|
| `INPUT_DIR` | Directory containing video files |

### Options

| Option | Default | Description |
|--------|---------|-------------|
| `-o, --output_subdirectory` | `extracted_photos` | Name of the output subdirectory within `INPUT_DIR` |
| `-s, --step_time` | `0.5` | Seconds between sampled frames |
| `-t, --ssim_threshold` | `0.90` | SSIM threshold for deduplication (0-1, higher = stricter) |

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
        video-name__chunk_0__0m0s_to_5m0s.log
        video-name__chunk_1__5m0s_to_10m0s.log
    another-video/
      ...
```

Each photo filename includes the video name and the timestamp where it was
found. Per-chunk log files record detailed extraction decisions.

## Remote extraction (`epm`)

`bin/epm` is a shell script that SSHes into a remote machine and runs the
extraction tool on a single video file. The repository and its dependencies are
auto-installed on the remote on first run.

### Prerequisites

`ssh media` must be configured and working (via `~/.ssh/config` or equivalent).

### Installation

Add `bin/` to your PATH, or symlink the script:

```bash
ln -s /path/to/extract-photos/bin/epm /usr/local/bin/epm
```

### Usage

```bash
epm VIDEO_FILE OUTPUT_DIR [options]
```

| Argument | Description |
|----------|-------------|
| `VIDEO_FILE` | Path to a video file on the remote machine |
| `OUTPUT_DIR` | Directory on the remote machine to copy extracted photos into |

Options `-s`, `-t`, and `-h` work the same as the local tool.

### Examples

```bash
epm /data/videos/sunset.mp4 /data/photos
epm /data/videos/sunset.mp4 /data/photos -s 1.0 -t 0.95
```

## License

MIT
