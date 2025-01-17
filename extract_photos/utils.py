#!/usr/bin/env python3

import cv2
import numpy as np
from skimage.metrics import structural_similarity as ssim

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


