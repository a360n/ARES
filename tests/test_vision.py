"""
Unit Test: Multi-Spectral Vision Mutators & Fusion Algorithms
"""

import unittest
import numpy as np
import cv2
from ares_app.vision.spectral_mutator import apply_spectral_mutator
from ares_app.vision.fusion import apply_thermal_fusion


class TestVision(unittest.TestCase):

    def setUp(self):
        self.blank_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        self.blank_frame[100:200, 100:200] = [0, 0, 255]  # Red square

    def test_apply_spectral_mutator_rgb(self):
        output = apply_spectral_mutator(self.blank_frame, "RGB")
        self.assertEqual(output.shape, self.blank_frame.shape)

    def test_apply_spectral_mutator_thermal(self):
        output = apply_spectral_mutator(self.blank_frame, "THERMAL")
        self.assertEqual(output.shape, (480, 640, 3))

    def test_apply_spectral_mutator_infrared(self):
        output = apply_spectral_mutator(self.blank_frame, "INFRARED")
        self.assertEqual(output.shape, (480, 640, 3))

    def test_apply_thermal_fusion(self):
        rgb = self.blank_frame.copy()
        thermal = apply_spectral_mutator(self.blank_frame, "THERMAL")
        fused = apply_thermal_fusion(rgb, thermal)
        self.assertEqual(fused.shape, (480, 640, 3))


if __name__ == '__main__':
    unittest.main()
