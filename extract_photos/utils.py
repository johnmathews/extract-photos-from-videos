#!/usr/bin/env python3

import re
import logging

import cv2
import numpy as np
from skimage.metrics import structural_similarity as ssim


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


def setup_logger(log_file):
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


def calculate_ssim(frame1, frame2):
    """
    Compute the Structural Similarity Index (SSIM) between two frames.
    """
    gray1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2GRAY)
    gray2 = cv2.cvtColor(frame2, cv2.COLOR_BGR2GRAY)
    score, _ = ssim(gray1, gray2, full=True)
    return score


def is_valid_photo(image):
    """
    Check if the photo is valid:
    - Minimum dimensions: 1000x1000 pixels.
    - Not a single color.

    Parameters:
    - image: The input photo (NumPy array).

    Returns:
    - True if valid, False otherwise.
    """
    h, w = image.shape[:2]

    # Check dimensions
    if h < 1000 or w < 1000:
        return False

    # Check if the photo is a single color
    if len(image.shape) == 2:  # Grayscale image
        if np.all(image == image[0, 0]):
            return False
    else:  # Color image
        if (
            np.all(image[:, :, 0] == image[0, 0, 0])
            and np.all(image[:, :, 1] == image[0, 0, 1])
            and np.all(image[:, :, 2] == image[0, 0, 2])
        ):
            return False

    return True
