"""
ARES Raspberry Pi Pico Serial Communication Protocol Definitions
"""

from ares_app.config import (
    UART0_BAUDRATE, UART0_TX_PIN, UART0_RX_PIN,
    UART1_BAUDRATE, UART1_RX_PIN, UART1_TX_PIN,
    PICO_PINS_LEFT_DRIVER, PICO_PINS_RIGHT_DRIVER,
    ULTRASONIC_TRIG_PIN, ULTRASONIC_ECHO_PIN,
    ADC_BATTERY_PIN, ADC_MQ9_PIN, ADC_MQ135_PIN,
    DHT22_DATA_PIN, ENCODER_PINS
)


def get_pico_pinout_summary():
    """Returns a structured dictionary of hardware pinouts for diagnostic verification."""
    return {
        "uart0": {"baudrate": UART0_BAUDRATE, "tx": UART0_TX_PIN, "rx": UART0_RX_PIN},
        "uart1_gps": {"baudrate": UART1_BAUDRATE, "rx": UART1_RX_PIN, "tx": UART1_TX_PIN},
        "left_driver": PICO_PINS_LEFT_DRIVER,
        "right_driver": PICO_PINS_RIGHT_DRIVER,
        "ultrasonic": {"trig": ULTRASONIC_TRIG_PIN, "echo": ULTRASONIC_ECHO_PIN},
        "adc": {"battery": ADC_BATTERY_PIN, "mq9": ADC_MQ9_PIN, "mq135": ADC_MQ135_PIN},
        "dht22": DHT22_DATA_PIN,
        "encoders": ENCODER_PINS
    }
