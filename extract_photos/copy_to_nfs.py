"""Copy files to NFS with fsync and verification for reliability."""
import argparse
import os
import shutil
import sys
import time


def copy_file_to_nfs(src: str, dest_dir: str) -> bool:
    """Copy a file to NFS destination with fsync and verification.

    Returns True if successful, False otherwise.
    """
    basename = os.path.basename(src)
    dest = os.path.join(dest_dir, basename)

    try:
        shutil.copy2(src, dest)
        # Explicit fsync to ensure NFS persistence
        with open(dest, "rb") as f:
            os.fsync(f.fileno())
        # Verify file exists and has non-zero size
        if not os.path.exists(dest):
            print(f"  {basename} -- FAILED: file does not exist after copy", file=sys.stderr)
            return False
        if os.path.getsize(dest) == 0:
            os.unlink(dest)
            print(f"  {basename} -- FAILED: empty file", file=sys.stderr)
            return False
        return True
    except Exception as e:
        print(f"  {basename} -- FAILED: {e}", file=sys.stderr)
        return False


def copy_photos_to_nfs(source_dir: str, dest_dir: str) -> tuple[int, int]:
    """Copy all photo files from source to dest with verification.

    Returns (success_count, failure_count).
    """
    os.makedirs(dest_dir, exist_ok=True)

    # Get list of files (not directories like logs/)
    files = [f for f in os.listdir(source_dir)
             if os.path.isfile(os.path.join(source_dir, f))]

    if not files:
        return 0, 0

    success = 0
    failed = 0

    for filename in files:
        src_path = os.path.join(source_dir, filename)
        if copy_file_to_nfs(src_path, dest_dir):
            success += 1
        else:
            failed += 1
        # Small delay between copies to avoid overwhelming NFS
        time.sleep(0.05)

    return success, failed


def main() -> None:
    parser = argparse.ArgumentParser(description="Copy photos to NFS with verification")
    parser.add_argument("source_dir", help="Source directory containing photos")
    parser.add_argument("dest_dir", help="Destination directory (NFS path)")
    args = parser.parse_args()

    success, failed = copy_photos_to_nfs(args.source_dir, args.dest_dir)

    if failed > 0:
        print(f"Copied {success} photo(s) to {args.dest_dir} ({failed} FAILED)", file=sys.stderr)
        sys.exit(1)
    else:
        print(f"Copied {success} photo(s) to {args.dest_dir}", file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    main()
