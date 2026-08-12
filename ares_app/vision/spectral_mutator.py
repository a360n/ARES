"""
ARES Multi-Spectral Frame Mutator (RGB, FLIR Thermal, NoIR Night-Vision)
"""

import cv2
import numpy as np


def apply_spectral_mutator(frame, mode):
    """Applies conditional OpenCV matrix transformations to emulate Thermal and Night Vision."""
    if mode == "THERMAL":
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        thermal = cv2.applyColorMap(gray, cv2.COLORMAP_JET)
        return thermal

    elif mode == "INFRARED":
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        enhanced = cv2.equalizeHist(gray)
        gain_enhanced = cv2.convertScaleAbs(enhanced, alpha=1.1, beta=15)

        green_tint = np.zeros_like(frame)
        green_tint[:, :, 1] = gain_enhanced                      # Bright green
        green_tint[:, :, 0] = cv2.multiply(gain_enhanced, 0.12)  # Low blue bleed
        green_tint[:, :, 2] = cv2.multiply(gain_enhanced, 0.08)  # Low red bleed
        return green_tint

    return frame  # RGB: return raw frame unchanged
