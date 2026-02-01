"""Immich integration: scan library, create album, add assets, share."""

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def immich_request(url: str, api_key: str, method: str = "GET", data: dict | None = None) -> dict | list | None:
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


def poll_for_assets(api_url: str, api_key: str, asset_path: str, timeout: int = 300) -> list[dict]:
    """Poll Immich until assets matching asset_path appear, or timeout."""
    url = f"{api_url}/api/search/metadata"
    deadline = time.monotonic() + timeout
    while True:
        result = immich_request(url, api_key, method="POST", data={"originalPath": asset_path})
        assets = result.get("assets", {}).get("items", []) if isinstance(result, dict) else []
        if assets:
            return assets
        if time.monotonic() >= deadline:
            return []
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
    return result["id"]


def add_assets_to_album(api_url: str, api_key: str, album_id: str, asset_ids: list[str]) -> None:
    """Add assets to an album."""
    url = f"{api_url}/api/albums/{album_id}/assets"
    immich_request(url, api_key, method="PUT", data={"ids": asset_ids})


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
    immich_request(url, api_key, method="PUT", data={"albumUsers": [{"userId": user_id, "role": "editor"}]})


def main() -> None:
    parser = argparse.ArgumentParser(description="Immich integration: scan, create album, add assets, share")
    parser.add_argument("--api-url", required=True, help="Immich server URL")
    parser.add_argument("--api-key", required=True, help="Immich API key")
    parser.add_argument("--library-id", required=True, help="Immich library ID to scan")
    parser.add_argument("--asset-path", required=True, help="Path prefix to search for new assets")
    parser.add_argument("--video-filename", required=True, help="Original video filename for album naming")
    parser.add_argument("--share-user", default=None, help="Immich username to share album with")
    args = parser.parse_args()

    api_url = args.api_url.rstrip("/")

    # 1. Trigger library scan
    print("Triggering Immich library scan...")
    try:
        trigger_scan(api_url, args.api_key, args.library_id)
        print("Library scan triggered")
    except urllib.error.URLError as e:
        print(f"Error: failed to trigger library scan: {e}", file=sys.stderr)
        sys.exit(1)

    # 2. Poll for new assets
    asset_search_path = args.asset_path.rstrip("/") + "/"
    print(f"Waiting for assets in {asset_search_path} ...")
    assets = poll_for_assets(api_url, args.api_key, asset_search_path)
    if not assets:
        print("Warning: no assets found after waiting — album creation skipped", file=sys.stderr)
        sys.exit(0)
    asset_ids = [a["id"] for a in assets]
    print(f"Found {len(asset_ids)} asset(s)")

    # 3. Create or find album
    album_name = parse_album_name(args.video_filename)
    print(f"Album: {album_name}")
    try:
        album_id = find_or_create_album(api_url, args.api_key, album_name)
        print(f"Album ready (id: {album_id})")
    except urllib.error.URLError as e:
        print(f"Error: failed to create/find album: {e}", file=sys.stderr)
        sys.exit(1)

    # 4. Add assets to album
    print(f"Adding {len(asset_ids)} asset(s) to album...")
    try:
        add_assets_to_album(api_url, args.api_key, album_id, asset_ids)
        print("Assets added to album")
    except urllib.error.URLError as e:
        print(f"Error: failed to add assets to album: {e}", file=sys.stderr)
        sys.exit(1)

    # 5. Share album if user specified
    if args.share_user:
        print(f"Sharing album with {args.share_user}...")
        try:
            user_id = find_user(api_url, args.api_key, args.share_user)
            if user_id:
                share_album(api_url, args.api_key, album_id, user_id)
                print(f"Album shared with {args.share_user}")
            else:
                print(f"Warning: user '{args.share_user}' not found — album not shared", file=sys.stderr)
        except urllib.error.URLError as e:
            print(f"Error: failed to share album: {e}", file=sys.stderr)

    print("Done")


if __name__ == "__main__":
    main()
