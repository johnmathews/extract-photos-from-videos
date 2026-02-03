"""Immich integration: scan library, create album, add assets, share."""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path


def immich_request(
    url: str, api_key: str, method: str = "GET", data: dict | None = None
) -> dict | list | None:
    """Make an authenticated request to the Immich API."""
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("x-api-key", api_key)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req) as resp:
        content = resp.read()
        if not content:
            return None
        return json.loads(content)


def trigger_scan(api_url: str, api_key: str, library_id: str) -> None:
    """Trigger an Immich library scan."""
    url = f"{api_url}/api/libraries/{library_id}/scan"
    immich_request(url, api_key, method="POST")


def poll_for_assets(
    api_url: str,
    api_key: str,
    asset_path: str,
    expected_count: int = 1,
    timeout: int = 300,
) -> list[dict]:
    """Poll Immich until expected number of assets appear, or timeout.

    Keeps polling until at least expected_count assets matching asset_path
    are found, or four consecutive polls return the same count (scan finished).
    """
    url = f"{api_url}/api/search/metadata"
    deadline = time.monotonic() + timeout
    prev_count = 0
    stable_polls = 0
    assets = []
    while True:
        result = immich_request(
            url, api_key, method="POST", data={"originalPath": asset_path}
        )
        assets = (
            result.get("assets", {}).get("items", [])
            if isinstance(result, dict)
            else []
        )
        if len(assets) >= expected_count:
            return assets
        # If count stabilised across two polls, the scan is done
        if assets and len(assets) == prev_count:
            stable_polls += 1
            if stable_polls >= 4:
                return assets
        else:
            stable_polls = 0
        prev_count = len(assets)
        if time.monotonic() >= deadline:
            return assets
        time.sleep(5)


def parse_album_name(video_filename: str) -> str:
    """Parse a video filename into a human-readable album name.

    Input:  Willem_Verbeeck-Shooting_Los_Angeles_on_8x10_Film_-_Paloma_Dooley-[ct4a89JIIkI].mkv
    Output: Willem Verbeeck - Shooting Los Angeles on 8x10 Film - Paloma Dooley
    """
    name = Path(video_filename).stem
    # Remove YouTube ID suffix like -[ct4a89JIIkI]
    name = re.sub(r"-\[[^\]]*\]$", "", name)
    # Split on first hyphen: channel-title
    parts = name.split("-", 1)
    channel = parts[0].replace("_", " ").strip()
    title = parts[1].replace("_", " ").strip() if len(parts) > 1 else ""
    if title:
        return f"{channel} - {title}"
    return channel


def find_or_create_album(api_url: str, api_key: str, album_name: str) -> str:
    """Find an existing album by name or create a new one. Returns the album ID."""
    url = f"{api_url}/api/albums"
    albums = immich_request(url, api_key, method="GET")
    if isinstance(albums, list):
        for album in albums:
            if album.get("albumName") == album_name:
                return album["id"]
    result = immich_request(url, api_key, method="POST", data={"albumName": album_name})
    assert isinstance(result, dict), f"Unexpected response creating album: {result}"
    return result["id"]


def add_assets_to_album(
    api_url: str, api_key: str, album_id: str, asset_ids: list[str]
) -> list[dict]:
    """Add assets to an album. Returns per-asset result list from Immich."""
    url = f"{api_url}/api/albums/{album_id}/assets"
    result = immich_request(url, api_key, method="PUT", data={"ids": asset_ids})
    return result if isinstance(result, list) else []


def find_user(api_url: str, api_key: str, username: str) -> str | None:
    """Find a user by name. Returns user ID or None."""
    url = f"{api_url}/api/users"
    users = immich_request(url, api_key, method="GET")
    if isinstance(users, list):
        for user in users:
            if user.get("name") == username:
                return user["id"]
    return None


def share_album(api_url: str, api_key: str, album_id: str, user_id: str) -> None:
    """Share an album with a user as editor."""
    url = f"{api_url}/api/albums/{album_id}/users"
    immich_request(
        url,
        api_key,
        method="PUT",
        data={"albumUsers": [{"userId": user_id, "role": "editor"}]},
    )


def send_pushover(user_key: str, app_token: str, title: str, message: str) -> None:
    """Send a Pushover notification."""
    data = urllib.parse.urlencode(
        {
            "token": app_token,
            "user": user_key,
            "title": title,
            "message": message,
        }
    ).encode()
    req = urllib.request.Request(
        "https://api.pushover.net/1/messages.json", data=data, method="POST"
    )
    with urllib.request.urlopen(req) as resp:
        resp.read()


def get_video_date(video_path: str) -> datetime:
    """Get the video's original date: YouTube upload date from metadata, or file mtime.

    yt-dlp embeds the upload date as a DATE tag in YYYYMMDD format.
    Falls back to the file's modification time (i.e. download time).
    Returns a timezone-aware UTC datetime.
    """
    # Try ffprobe to get upload date from embedded metadata
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                video_path,
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            tags = data.get("format", {}).get("tags", {})
            # yt-dlp embeds upload date as DATE tag in YYYYMMDD format
            date_val = tags.get("DATE") or tags.get("date") or tags.get("upload_date")
            if date_val and len(date_val) >= 8:
                return datetime(
                    int(date_val[:4]),
                    int(date_val[4:6]),
                    int(date_val[6:8]),
                    tzinfo=timezone.utc,
                )
    except (FileNotFoundError, ValueError, KeyError, json.JSONDecodeError):
        pass

    # Fall back to file modification time (download time)
    try:
        mtime = os.path.getmtime(video_path)
        return datetime.fromtimestamp(mtime, tz=timezone.utc)
    except OSError:
        return datetime(2000, 1, 1, tzinfo=timezone.utc)


def parse_video_timestamp(filename: str) -> float | None:
    """Extract seconds from a filename like '_5m04s.jpg' or '_1m23.5s.jpg'.

    Returns total seconds as a float, or None for non-matching files (e.g. videos).
    """
    match = re.search(r"_(\d+)m(\d+(?:\.\d+)?)s\.jpg$", filename)
    if not match:
        return None
    minutes = int(match.group(1))
    seconds = float(match.group(2))
    return minutes * 60 + seconds


def update_asset_date(api_url: str, api_key: str, asset_id: str, date_str: str) -> None:
    """Set dateTimeOriginal on an Immich asset via PUT /api/assets/{id}."""
    url = f"{api_url}/api/assets/{asset_id}"
    immich_request(url, api_key, method="PUT", data={"dateTimeOriginal": date_str})


def order_assets(assets: list[dict]) -> list[dict]:
    """Separate video and photo assets, sort photos by timestamp.

    Returns ordered list: video(s) first, then photos in chronological order.
    """
    videos = []
    photos = []
    for asset in assets:
        path = asset.get("originalPath", "")
        if path.lower().endswith((".mkv", ".mp4", ".avi", ".webm", ".mov")):
            videos.append(asset)
        else:
            photos.append(asset)

    photos.sort(key=lambda a: parse_video_timestamp(a.get("originalPath", "")) or 0)
    return videos + photos


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Immich integration: scan, create album, add assets, share"
    )
    parser.add_argument("--api-url", required=True, help="Immich server URL")
    parser.add_argument("--api-key", required=True, help="Immich API key")
    parser.add_argument("--library-id", required=True, help="Immich library ID to scan")
    parser.add_argument(
        "--asset-path", required=True, help="Path prefix to search for new assets"
    )
    parser.add_argument(
        "--video-filename",
        required=True,
        help="Original video filename for album naming",
    )
    parser.add_argument(
        "--share-user", default=None, help="Immich username to share album with"
    )
    parser.add_argument("--pushover-user-key", default=None, help="Pushover user key")
    parser.add_argument(
        "--pushover-app-token", default=None, help="Pushover application API token"
    )
    parser.add_argument(
        "--photo-count", type=int, default=None, help="Number of photos extracted"
    )
    args = parser.parse_args()

    api_url = args.api_url.rstrip("/")
    album_name = parse_album_name(args.video_filename)
    notification_parts = []

    print("\n📚 Immich Integration")

    # 1. Trigger library scan
    print("  Scanning library...       ", end="", flush=True)
    try:
        trigger_scan(api_url, args.api_key, args.library_id)
        print("done")
    except urllib.error.URLError as e:
        print("failed")
        print(f"Error: failed to trigger library scan: {e}", file=sys.stderr)
        sys.exit(1)

    # 2. Poll for new assets
    asset_search_path = args.asset_path.rstrip("/") + "/"
    expected = (args.photo_count + 1) if args.photo_count else 1
    print("  Waiting for assets...     ", end="", flush=True)
    assets = poll_for_assets(
        api_url, args.api_key, asset_search_path, expected_count=expected
    )
    if not assets:
        print("none found")
        print(
            "Warning: no assets found after waiting — album creation skipped",
            file=sys.stderr,
        )
        sys.exit(0)
    print(f"{len(assets)} found")
    if args.photo_count and len(assets) < expected:
        print(
            f"  Warning: expected {expected} assets, found {len(assets)}"
            " (library scan may still be running)"
        )

    # 3. Order assets: video first, photos by timestamp
    print("  Ordering assets...        ", end="", flush=True)
    ordered = order_assets(assets)
    asset_ids = [a["id"] for a in ordered]
    print("done")

    # 4. Set dateTimeOriginal so Immich sorts by video timeline
    video_path = os.path.join(args.asset_path, args.video_filename)
    base_date = get_video_date(video_path)
    print(f"  Video date: {base_date.strftime('%Y-%m-%d')}")
    print("  Setting asset dates...    ", end="", flush=True)
    try:
        for asset in ordered:
            path = asset.get("originalPath", "")
            ts = parse_video_timestamp(path)
            if ts is None:
                # Video asset — 1s before base so it sorts before the 0m00s photo
                dt = base_date - timedelta(seconds=1)
            else:
                # Photo asset — base date + offset from position in video
                dt = base_date + timedelta(seconds=ts)
            date_str = dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
            update_asset_date(api_url, args.api_key, asset["id"], date_str)
        print("done")
    except urllib.error.URLError as e:
        print("failed")
        print(f"Warning: failed to set asset dates: {e}", file=sys.stderr)

    # 5. Create or find album, set sort order to oldest first
    print(f"  Album: {album_name}")
    print("  Creating album...         ", end="", flush=True)
    try:
        album_id = find_or_create_album(api_url, args.api_key, album_name)
        # Set album sort to oldest first so video appears first, photos in order
        immich_request(
            f"{api_url}/api/albums/{album_id}",
            args.api_key,
            method="PATCH",
            data={"order": "asc"},
        )
        print("done")
    except urllib.error.URLError as e:
        print("failed")
        print(f"Error: failed to create/find album: {e}", file=sys.stderr)
        sys.exit(1)

    # 6. Add assets to album
    print(f"  Adding {len(asset_ids)} asset(s)...     ", end="", flush=True)
    try:
        results = add_assets_to_album(api_url, args.api_key, album_id, asset_ids)
        added = sum(1 for r in results if r.get("success"))
        dupes = sum(1 for r in results if r.get("error") == "duplicate")
        failed = [
            r for r in results if not r.get("success") and r.get("error") != "duplicate"
        ]
        if failed:
            print(f"{added} added, {len(failed)} failed")
            # Retry after a brief delay — assets may still be processing
            time.sleep(5)
            failed_ids = [r["id"] for r in failed]
            print(f"  Retrying {len(failed_ids)} asset(s)... ", end="", flush=True)
            retry = add_assets_to_album(api_url, args.api_key, album_id, failed_ids)
            retry_ok = sum(1 for r in retry if r.get("success"))
            added += retry_ok
            still_bad = len(failed_ids) - retry_ok
            if still_bad:
                print(f"{retry_ok} added, {still_bad} still failed")
                errors = {
                    r.get("error", "unknown") for r in retry if not r.get("success")
                }
                print(f"  Failure reasons: {', '.join(errors)}", file=sys.stderr)
            else:
                print(f"all {retry_ok} added")
        else:
            msg = f"done ({added} new"
            if dupes:
                msg += f", {dupes} already in album"
            print(msg + ")")
        notification_parts.append(f"{added + dupes} assets in album")
    except urllib.error.URLError as e:
        print("failed")
        print(f"Error: failed to add assets to album: {e}", file=sys.stderr)
        sys.exit(1)

    # 7. Share album if user specified
    if not args.share_user:
        print("  Sharing...                not configured (IMMICH_SHARE_USER not set)")
    else:
        print(f"  Sharing with {args.share_user}...      ", end="", flush=True)
        try:
            user_id = find_user(api_url, args.api_key, args.share_user)
            if user_id:
                share_album(api_url, args.api_key, album_id, user_id)
                print("done")
                notification_parts.append(f"shared with {args.share_user}")
            else:
                print("user not found")
                print(
                    f"Warning: user '{args.share_user}' not found — album not shared",
                    file=sys.stderr,
                )
        except urllib.error.HTTPError as e:
            if e.code == 400:
                print("already shared")
            else:
                print("failed")
                print(f"Error: failed to share album: {e}", file=sys.stderr)
        except urllib.error.URLError as e:
            print("failed")
            print(f"Error: failed to share album: {e}", file=sys.stderr)

    # 8. Send Pushover notification if configured
    if args.pushover_user_key and args.pushover_app_token:
        print("  Sending notification...   ", end="", flush=True)
        try:
            lines = []
            if args.photo_count is not None:
                lines.append(f"{args.photo_count} photos extracted")
            lines.append(f"Album: {album_name}")
            if notification_parts:
                lines.append(", ".join(notification_parts))
            message = "\n".join(lines)
            send_pushover(
                args.pushover_user_key, args.pushover_app_token, album_name, message
            )
            print("done")
        except urllib.error.URLError as e:
            print("failed")
            print(f"Error: failed to send notification: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
