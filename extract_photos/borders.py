#!/usr/bin/env python3

import cv2
import numpy as np


def _find_text_gap_from_edge(density: np.ndarray, content_fraction: float = 0.3, min_gap_px: int = 10) -> tuple[int, int]:
    """
    Given a 1D density profile (from one edge inward), detect a text-gap-photo pattern.

    Looks for: sparse content (text) -> gap (zero density) -> dense content (photo).
    Returns (gap_width, dense_start) if found, otherwise (0, 0).
    - gap_width: width of the gap between text and photo (used as padding when including text)
    - dense_start: distance from edge to where photo content begins (used as crop when excluding text)
    """
    n = len(density)
    if n == 0:
        return 0, 0

    # Find where dense content (photo) starts
    dense_start = None
    for i in range(n):
        if density[i] >= content_fraction:
            dense_start = i
            break

    if dense_start is None or dense_start < min_gap_px:
        return 0, 0

    # Walk backward from dense_start to find the gap (zero-density region)
    gap_end = dense_start
    gap_start = None
    for i in range(dense_start - 1, -1, -1):
        if density[i] > 0:
            gap_start = i + 1
            break
    else:
        # All zero from edge to dense_start — no text before the gap
        return 0, 0

    if gap_start is None:
        return 0, 0

    gap_width = gap_end - gap_start
    if gap_width < min_gap_px:
        return 0, 0

    # Verify there's sparse content (text) before the gap
    has_text = any(0 < density[i] < content_fraction for i in range(gap_start))
    if not has_text:
        return 0, 0

    return gap_width, dense_start


def _detect_text_padding(cropped_gray: np.ndarray, border_gray_value: int, border_diff_threshold: int = 30, content_fraction: float = 0.3, min_gap_px: int = 10) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int]]:
    """
    Detect text/watermark near edges and return padding and crop values per side.

    Computes a binary content mask (pixels differing from border color), then
    checks column/row density profiles from each edge for a text-gap-photo pattern.

    Returns two 4-tuples:
    - padding: (top, bottom, left, right) gap widths for including text (border widening)
    - crop: (top, bottom, left, right) dense_start distances for excluding text (cropping)
    """
    mask = (np.abs(cropped_gray.astype(np.int16) - int(border_gray_value)) > border_diff_threshold).astype(np.float32)

    col_density = np.mean(mask, axis=0)  # density per column (left-to-right)
    row_density = np.mean(mask, axis=1)  # density per row (top-to-bottom)

    left_gap, left_dense = _find_text_gap_from_edge(col_density, content_fraction, min_gap_px)
    right_gap, right_dense = _find_text_gap_from_edge(col_density[::-1], content_fraction, min_gap_px)
    top_gap, top_dense = _find_text_gap_from_edge(row_density, content_fraction, min_gap_px)
    bottom_gap, bottom_dense = _find_text_gap_from_edge(row_density[::-1], content_fraction, min_gap_px)

    padding = (top_gap, bottom_gap, left_gap, right_gap)
    crop = (top_dense, bottom_dense, left_dense, right_dense)
    return padding, crop


def trim_and_add_border(image: np.ndarray, border_px: int = 5, uniformity_threshold: int = 10, include_text: bool = True) -> np.ndarray:
    """
    Trims uniform borders from an image using edge-scanning, then adds a
    fixed-size border in the original border color.

    Scans inward from each edge (row-by-row for top/bottom, column-by-column
    for left/right). A row/column is considered "border" if its grayscale
    standard deviation is below uniformity_threshold. The first non-uniform
    row/column from each edge marks the content boundary.

    Parameters:
    - image: The input image (NumPy array, BGR or grayscale).
    - border_px: Number of pixels to add as border on each side.
    - uniformity_threshold: Max std deviation for a row/column to be "border".

    Returns:
    - The image with trimmed and re-added border (NumPy array).
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
    h, w = gray.shape

    # Scan from top: first row with std > threshold
    top = 0
    for i in range(h):
        if np.std(gray[i, :]) > uniformity_threshold:  # type: ignore[reportArgumentType]
            top = i
            break
    else:
        # All rows uniform — return original
        return image

    # Scan from bottom: last row with std > threshold
    bottom = h - 1
    for i in range(h - 1, -1, -1):
        if np.std(gray[i, :]) > uniformity_threshold:  # type: ignore[reportArgumentType]
            bottom = i
            break

    # Scan from left: first col with std > threshold
    left = 0
    for j in range(w):
        if np.std(gray[:, j]) > uniformity_threshold:  # type: ignore[reportArgumentType]
            left = j
            break

    # Scan from right: last col with std > threshold
    right = w - 1
    for j in range(w - 1, -1, -1):
        if np.std(gray[:, j]) > uniformity_threshold:  # type: ignore[reportArgumentType]
            right = j
            break

    # Sample border color from the original border region (top-left corner)
    border_sample = image[: max(top, 1), : max(left, 1)]

    # Crop to content
    cropped = image[top : bottom + 1, left : right + 1]

    # Detect text/watermarks near edges and compute extra padding
    cropped_gray = cv2.cvtColor(cropped, cv2.COLOR_BGR2GRAY) if len(cropped.shape) == 3 else cropped
    border_gray_value = int(np.mean(cv2.cvtColor(border_sample, cv2.COLOR_BGR2GRAY) if len(border_sample.shape) == 3 else border_sample))  # type: ignore[reportArgumentType]
    padding, crop_amounts = _detect_text_padding(cropped_gray, border_gray_value)

    if include_text:
        pad_top = max(border_px, padding[0])
        pad_bottom = max(border_px, padding[1])
        pad_left = max(border_px, padding[2])
        pad_right = max(border_px, padding[3])
    else:
        # Crop out text regions before adding border
        ct, cb, cl, cr = crop_amounts
        ch, cw = cropped.shape[:2]
        if ch - ct - cb > 0 and cw - cl - cr > 0:
            cropped = cropped[ct : ch - cb, cl : cw - cr]
        pad_top = border_px
        pad_bottom = border_px
        pad_left = border_px
        pad_right = border_px

    # Add new border
    if len(image.shape) == 2:
        border_color = int(np.mean(border_sample))
    else:
        border_color = [int(c) for c in np.mean(border_sample, axis=(0, 1))]

    result = cv2.copyMakeBorder(  # type: ignore[reportCallIssue]
        cropped,
        pad_top,
        pad_bottom,
        pad_left,
        pad_right,
        borderType=cv2.BORDER_CONSTANT,
        value=border_color,  # type: ignore[reportArgumentType]
    )

    return result
