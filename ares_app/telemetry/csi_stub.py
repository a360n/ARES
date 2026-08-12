"""
ARES WiFi CSI (Channel State Information) Sensing Stub
Extensibility point for non-invasive human presence & motion detection via WiFi signals.
"""

from ares_app.config import WIFI_CSI_ENABLED, WIFI_CSI_SAMPLE_RATE_HZ, WIFI_CSI_SUBCARRIERS


class WiFiCSISensingEngine:
    def __init__(self, enabled=WIFI_CSI_ENABLED):
        self.enabled = enabled
        self.sample_rate = WIFI_CSI_SAMPLE_RATE_HZ
        self.subcarriers = WIFI_CSI_SUBCARRIERS
        self.latest_respiration_rate = 0.0
        self.motion_detected = False

    def process_csi_frame(self, csi_amplitude_matrix):
        """Processes raw CSI amplitude matrix from ESP32-S3/C3 or router node."""
        if not self.enabled:
            return None
        # Extension point: apply Phase Sanitization, Butterworth Bandpass Filter & STFT
        return {
            "respiration_bpm": self.latest_respiration_rate,
            "motion_detected": self.motion_detected
        }

    def get_status(self):
        return {
            "enabled": self.enabled,
            "sample_rate_hz": self.sample_rate,
            "subcarriers": self.subcarriers
        }


csi_engine = WiFiCSISensingEngine()
