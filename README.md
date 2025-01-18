# Photograph Extractor

This script parses video files and extracts photographs from them, saving the
photographs as JPEGS images.

It is designed to take as input a directory containing numerous video files to
check. It identifies video files in the directory and then analyses each video
in turn.

A subdirectory is created for each video, using the name of the video as the
name of the subdirectory. Photographs from a video are then saved into that
video's subdirectory.

To save time, not every frame is analysed. One frame is analysed per second of
video.

Photographs are identified by having a solid color border around them, usually
white. Full frame photographs without a border will not be extracted. As long as
the border is a constant color, this tool should work.

If the same photograph is displayed for more than 1 second, the tool will avoid
extracting the same photographs more than once by measuring the similarity of a
candidate photo to the previously extracted photo. The similarity threshold is
0.98 but can be changed.

The project uses `uv` to manage dependencies and virtual environments. In order
to use the tool from anywhere without remembering commands to activate and
deactivate a virtualenv, the following snippet is put into my `.zshrc` file:

```
extract_photos() {
    (source <path-to-repo>/.venv/bin/activate && uv run python <path-to-repo>/extract_photos/main.py "$@")
}
```
