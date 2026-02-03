import sys


def format_time(seconds: float) -> str:
    """Format seconds as M:SS or H:MM:SS."""
    seconds = int(seconds)
    if seconds < 0:
        seconds = 0
    if seconds >= 3600:
        h, remainder = divmod(seconds, 3600)
        m, s = divmod(remainder, 60)
        return f"{h}:{m:02d}:{s:02d}"
    else:
        m, s = divmod(seconds, 60)
        return f"{m}:{s:02d}"


def build_progress_bar(pct: float, width: int = 30) -> str:
    """Build an ASCII progress bar like [===========-------------------]."""
    filled = int(pct / 100 * width)
    filled = min(filled, width)
    return "[" + "=" * filled + "-" * (width - filled) + "]"


def print_scan_progress(
    filename: str,
    pct: float,
    video_pos_sec: float,
    video_duration_sec: float,
    photo_count: int,
    eta_str: str,
) -> None:
    """
    Print a 3-line in-place progress display for the scanning phase.

    Line 1: Video filename (bold)
    Line 2: ASCII progress bar + overall percentage + ETA
    Line 3: Video position / duration + total photos found
    """
    bar = build_progress_bar(pct)
    pos_str = f"{format_time(video_pos_sec)} / {format_time(video_duration_sec)}"

    sys.stdout.write("\033[3A")
    sys.stdout.write(f"\033[K\033[1m{filename}\033[0m\n")
    sys.stdout.write(f"\033[K {bar}  {pct:5.1f}%   {eta_str}\n")
    sys.stdout.write(f"\033[K {pos_str:28s}{photo_count} photos\n")
    sys.stdout.flush()
