#!/usr/bin/env python3

import re
import logging

import cv2
import numpy as np


def make_safe_folder_name(title: str) -> str:
    """
    Converts a video title into a safe folder name by:
    - Replacing whitespace with hyphens.
    - Removing punctuation and special characters.
    - Converting to lowercase.

    Parameters:
    - title: The original video title.

    Returns:
    - A safe folder name string.
    """

    # Replace whitespace with hyphens
    title = re.sub(r"\s+", "-", title.strip())

    # Remove punctuation and special characters
    title = re.sub(r"[^\w\-]", "", title)

    # Convert to lowercase
    title = title.lower()

    return title


def setup_logger(log_file: str) -> logging.Logger:
    """
    Set up a logger for a specific worker.
    """
    logger = logging.getLogger(log_file)
    logger.setLevel(logging.DEBUG)
    handler = logging.FileHandler(log_file)
    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


def is_valid_photo(image: np.ndarray, std_threshold: float = 5.0) -> bool:
    """
    Check if the photo is valid:
    - Minimum dimensions: 1000x1000 pixels.
    - Not near-uniform (solid color or near-solid with codec noise).

    Parameters:
    - image: The input photo (NumPy array).
    - std_threshold: Maximum grayscale std dev to consider near-uniform.

    Returns:
    - True if valid, False otherwise.
    """
    h, w = image.shape[:2]

    # Check dimensions
    if h < 1000 or w < 1000:
        return False

    # Check if the photo is near-uniform
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
    if np.std(gray) < std_threshold:  # type: ignore[reportArgumentType]
        return False

    return True
