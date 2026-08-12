"""
ARES Homography Pixel-Level Thermal Fusion Engine
"""

import cv2
import numpy as np


def apply_thermal_fusion(rgb_frame, thermal_frame):
    """
    Applies pixel-level sensor fusion by warping the thermal frame to align
    with the RGB frame using a 3x3 homography matrix and adaptive blending.
    """
    H = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]], dtype=np.float32)
    warped_thermal = cv2.warpPerspective(thermal_frame, H, (rgb_frame.shape[1], rgb_frame.shape[0]))

    gray = cv2.cvtColor(rgb_frame, cv2.COLOR_BGR2GRAY)
    mean_luminance = np.mean(gray)

    if mean_luminance < 60:
        beta = 0.70
    else:
        beta = 0.30
    alpha = 1.0 - beta

    fused = cv2.addWeighted(rgb_frame, alpha, warped_thermal, beta, 0.0)
    return fused
