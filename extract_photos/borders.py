#!/usr/bin/env python3

import cv2
import numpy as np


def trim_and_add_border(image, border_px=5, uniformity_threshold=10):
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
        if np.std(gray[i, :]) > uniformity_threshold:
            top = i
            break
    else:
        # All rows uniform — return original
        return image

    # Scan from bottom: last row with std > threshold
    bottom = h - 1
    for i in range(h - 1, -1, -1):
        if np.std(gray[i, :]) > uniformity_threshold:
            bottom = i
            break

    # Scan from left: first col with std > threshold
    left = 0
    for j in range(w):
        if np.std(gray[:, j]) > uniformity_threshold:
            left = j
            break

    # Scan from right: last col with std > threshold
    right = w - 1
    for j in range(w - 1, -1, -1):
        if np.std(gray[:, j]) > uniformity_threshold:
            right = j
            break

    # Sample border color from the original border region (top-left corner)
    border_sample = image[: max(top, 1), : max(left, 1)]

    # Crop to content
    cropped = image[top : bottom + 1, left : right + 1]

    # Add new border
    if len(image.shape) == 2:
        border_color = int(np.mean(border_sample))
        result = cv2.copyMakeBorder(
            cropped,
            border_px,
            border_px,
            border_px,
            border_px,
            borderType=cv2.BORDER_CONSTANT,
            value=border_color,
        )
    else:
        border_color = [int(c) for c in np.mean(border_sample, axis=(0, 1))]
        result = cv2.copyMakeBorder(
            cropped,
            border_px,
            border_px,
            border_px,
            border_px,
            borderType=cv2.BORDER_CONSTANT,
            value=border_color,
        )

    return result
