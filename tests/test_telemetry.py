"""
Unit Test: Telemetry Engine & Decision Tree Hazard Classifier
"""

import unittest
import threading
from ares_app.telemetry.risk_assessment import classify_hazard_level
from ares_app.telemetry.engine import get_baseline_telemetry, compute_telemetry, startup_baseline


class TestTelemetry(unittest.TestCase):

    def test_classify_hazard_level_normal(self):
        grade, status, summary = classify_hazard_level(
            temp_c=22.0, gas_mq9=10.0, gas_mq135=100.0, lidar_cm=180.0, fire_detected=False
        )
        self.assertEqual(grade, 1)
        self.assertEqual(status, "NORMAL")

    def test_classify_hazard_level_gas_warning(self):
        grade, status, summary = classify_hazard_level(
            temp_c=25.0, gas_mq9=200.0, gas_mq135=500.0, lidar_cm=150.0, fire_detected=False
        )
        self.assertEqual(grade, 2)
        self.assertEqual(status, "GAS LEAK WARNING")

    def test_classify_hazard_level_fire_contingency(self):
        grade, status, summary = classify_hazard_level(
            temp_c=65.0, gas_mq9=300.0, gas_mq135=200.0, lidar_cm=120.0, fire_detected=True
        )
        self.assertEqual(grade, 3)
        self.assertEqual(status, "FIRE CONTINGENCY")

    def test_classify_hazard_level_critical_flashover(self):
        grade, status, summary = classify_hazard_level(
            temp_c=65.0, gas_mq9=300.0, gas_mq135=500.0, lidar_cm=40.0, fire_detected=True
        )
        self.assertEqual(grade, 4)
        self.assertEqual(status, "CRITICAL FLASHOVER")

    def test_get_baseline_telemetry(self):
        tel = get_baseline_telemetry(second=5.0)
        self.assertIn("status", tel)
        self.assertIn("sensors", tel)
        self.assertIn("dht22", tel["sensors"])
        self.assertIn("gas", tel["sensors"])
        self.assertIn("ultrasonic", tel["sensors"])
        self.assertIn("power", tel["sensors"])

    def test_compute_telemetry(self):
        sim_lock = threading.Lock()
        sim_config = {
            "dashboard_mode": "simulation",
            "ugv_mode": "USER_CONTROL",
            "navigation_override_status": "AUTOPILOT",
            "engine_power_status": "ONLINE",
            "last_manual_command": "STANDBY",
            "manual_x": 50.0,
            "manual_y": 50.0,
            "current_vision_mode": "RGB",
            "is_simulating": True,
            "telemetry_timeline": [
                {"second": 2.0, "gas_ppm": 250.0, "flame_alert": True, "temperature": 60.0}
            ]
        }
        tel = compute_telemetry(second=3.0, sim_config=sim_config, sim_lock=sim_lock)
        self.assertEqual(tel["status"]["fire_detected"], True)
        self.assertEqual(tel["sensors"]["gas"]["mq9"], 250.0)


if __name__ == '__main__':
    unittest.main()
