#!/usr/bin/env python3

import cv2
import numpy as np

def trim_and_add_border(image, target_border_fraction=0.05):
    """
    Adjusts the border of an image. Identifies the content inside the solid border,
    trims the solid border, and adds a resized solid border that matches the original border color.

    Parameters:
    - image: The input image (NumPy array).
    - target_border_fraction: Desired fraction of the photo's width and height for the border.

    Returns:
    - The image with adjusted border (NumPy array).
    """
    # Convert the image to grayscale for easier processing
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image

    # Sample a region of the border to calculate the average border color
    border_sample = image[:50, :50]  # Top-left 10x10 pixel region
    if len(image.shape) == 2:  # Grayscale image
        border_color = int(np.mean(border_sample))  # Average intensity
    else:  # Color image
        border_color = [int(c) for c in np.mean(border_sample, axis=(0, 1))]  # Average BGR color

    # Create a binary mask for the content (where pixel intensity ≠ border_color)
    mask = gray != int(np.mean(border_sample))

    # Find the bounding box of the content
    coords = np.argwhere(mask)
    y_min, x_min = coords.min(axis=0)
    y_max, x_max = coords.max(axis=0)

    # Crop the image to the content area
    cropped_image = image[y_min : y_max + 1, x_min : x_max + 1]

    # Calculate the new border size (5% of the photo dimensions)
    h, w = cropped_image.shape[:2]
    min_dim = min(h, w)
    border_w = int(min_dim * target_border_fraction)
    border_h = int(min_dim * target_border_fraction)

    # Add the new border around the cropped image
    if len(image.shape) == 2:  # Grayscale image
        adjusted_image = cv2.copyMakeBorder(
            cropped_image, border_h, border_h, border_w, border_w, borderType=cv2.BORDER_CONSTANT, value=border_color
        )
    else:  # Color image
        adjusted_image = cv2.copyMakeBorder(
            cropped_image, border_h, border_h, border_w, border_w, borderType=cv2.BORDER_CONSTANT, value=border_color
        )

    return adjusted_image


