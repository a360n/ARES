"""
Unit Test: Hardware Pinouts & Central Config Validation
"""

import unittest
from config import (
    UART0_BAUDRATE, UART0_TX_PIN, UART0_RX_PIN,
    UART1_BAUDRATE, UART1_RX_PIN, UART1_TX_PIN,
    PICO_PINS_LEFT_DRIVER, PICO_PINS_RIGHT_DRIVER,
    ULTRASONIC_TRIG_PIN, ULTRASONIC_ECHO_PIN,
    ADC_BATTERY_PIN, ADC_MQ9_PIN, ADC_MQ135_PIN,
    DHT22_DATA_PIN, ENCODER_PINS, ESP32_CAM_IP
)


class TestConfigPinouts(unittest.TestCase):

    def test_uart_baudrates_and_pins(self):
        self.assertEqual(UART0_BAUDRATE, 115200)
        self.assertEqual(UART0_TX_PIN, 0)
        self.assertEqual(UART0_RX_PIN, 1)

        self.assertEqual(UART1_BAUDRATE, 9600)
        self.assertEqual(UART1_RX_PIN, 21)
        self.assertEqual(UART1_TX_PIN, 24)

    def test_motor_driver_pins(self):
        self.assertEqual(PICO_PINS_LEFT_DRIVER["PWM_FRONT"], 2)
        self.assertEqual(PICO_PINS_LEFT_DRIVER["IN1_FRONT"], 3)
        self.assertEqual(PICO_PINS_LEFT_DRIVER["IN2_FRONT"], 4)
        self.assertEqual(PICO_PINS_LEFT_DRIVER["IN3_REAR"], 5)
        self.assertEqual(PICO_PINS_LEFT_DRIVER["IN4_REAR"], 6)
        self.assertEqual(PICO_PINS_LEFT_DRIVER["PWM_REAR"], 7)

        self.assertEqual(PICO_PINS_RIGHT_DRIVER["PWM_FRONT"], 11)
        self.assertEqual(PICO_PINS_RIGHT_DRIVER["IN1_FRONT"], 13)
        self.assertEqual(PICO_PINS_RIGHT_DRIVER["IN2_FRONT"], 12)
        self.assertEqual(PICO_PINS_RIGHT_DRIVER["IN3_REAR"], 17)
        self.assertEqual(PICO_PINS_RIGHT_DRIVER["IN4_REAR"], 16)
        self.assertEqual(PICO_PINS_RIGHT_DRIVER["PWM_REAR"], 18)

    def test_sensors_pins(self):
        self.assertEqual(ULTRASONIC_TRIG_PIN, 20)
        self.assertEqual(ULTRASONIC_ECHO_PIN, 8)
        self.assertEqual(ADC_BATTERY_PIN, 26)
        self.assertEqual(ADC_MQ9_PIN, 27)
        self.assertEqual(ADC_MQ135_PIN, 28)
        self.assertEqual(DHT22_DATA_PIN, 22)

        self.assertEqual(ENCODER_PINS["RR"], 9)
        self.assertEqual(ENCODER_PINS["FR"], 10)
        self.assertEqual(ENCODER_PINS["FL"], 14)
        self.assertEqual(ENCODER_PINS["RL"], 15)

    def test_esp32_cam_ip(self):
        self.assertEqual(ESP32_CAM_IP, "192.168.4.1")


if __name__ == '__main__':
    unittest.main()
