#!/usr/bin/env python3
"""
ARES (Autonomous Rescue & Emergency System)
Central Configuration Module

Centralizes hardware pinouts, communication ports, baud rates, network addresses,
sensor calibration thresholds, AI model parameters, and database paths.
"""

import os

# ============================================================================
# 1. Base Paths & Directories
# ============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'ares_mission_control.db')
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
REPORTS_DIR = os.path.join(BASE_DIR, 'reports')
STATIC_DIR = os.path.join(BASE_DIR, 'static')
CERT_DIR = os.path.join(STATIC_DIR, 'certs')

MAX_CONTENT_LENGTH = 500 * 1024 * 1024  # 500 MB max upload limit

# Ensure required directories exist
for folder in [UPLOAD_FOLDER, REPORTS_DIR, STATIC_DIR, CERT_DIR]:
    os.makedirs(folder, exist_ok=True)

# ============================================================================
# 2. Server & Security Settings
# ============================================================================
SERVER_HOST = '0.0.0.0'
SERVER_PORT = 5001
SSH_PORT = 22
SECRET_KEY = os.environ.get('ARES_SECRET_KEY') or os.urandom(32).hex()

# Flask-Limiter defaults
DEFAULT_RATE_LIMITS = ["200 per day", "50 per hour"]

# Security Header Defaults
SECURITY_HEADERS = {
    'Content-Security-Policy': (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.tailwindcss.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: blob: http: https:; "
        "connect-src 'self' ws: wss: http: https:;"
    ),
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'DENY',
    'X-XSS-Protection': '1; mode=block',
    'Strict-Transport-Security': 'max-age=31536000; includeSubDomains'
}

# ============================================================================
# 3. Physical Hardware Pinouts & Comm Ports (Raspberry Pi Pico 2 W)
# ============================================================================
# Serial Line 0: Communication with ESP32-CAM / Central Host
UART0_BAUDRATE = 115200
UART0_TX_PIN = 0
UART0_RX_PIN = 1

# Serial Line 1: GPS Module (NEO-8M)
UART1_BAUDRATE = 9600
UART1_RX_PIN = 21
UART1_TX_PIN = 24

# Left Motor Driver (L298N / Dual H-Bridge)
PICO_PINS_LEFT_DRIVER = {
    "PWM_FRONT": 2,
    "IN1_FRONT": 3,
    "IN2_FRONT": 4,
    "IN3_REAR": 5,
    "IN4_REAR": 6,
    "PWM_REAR": 7
}

# Right Motor Driver (L298N / Dual H-Bridge)
PICO_PINS_RIGHT_DRIVER = {
    "PWM_FRONT": 11,
    "IN1_FRONT": 13,
    "IN2_FRONT": 12,
    "IN3_REAR": 17,
    "IN4_REAR": 16,
    "PWM_REAR": 18
}

# PWM Frequency (Hz)
MOTOR_PWM_FREQ = 1000

# Sensor Pins
ULTRASONIC_TRIG_PIN = 20
ULTRASONIC_ECHO_PIN = 8

ADC_BATTERY_PIN = 26
ADC_MQ9_PIN = 27
ADC_MQ135_PIN = 28

DHT22_DATA_PIN = 22

ENCODER_PINS = {
    "RR": 9,   # Rear Right
    "FR": 10,  # Front Right
    "FL": 14,  # Front Left
    "RL": 15   # Rear Left
}

# ============================================================================
# 4. ESP32-CAM Hardware & Control URLs
# ============================================================================
ESP32_CAM_IP = "192.168.4.1"
ESP32_CAM_STREAM_URL = f"http://{ESP32_CAM_IP}:81/stream"
ESP32_CAM_TELEMETRY_URL = f"http://{ESP32_CAM_IP}/telemetry"
ESP32_CAM_MOVE_URL_TEMPLATE = f"http://{ESP32_CAM_IP}/move?dir={{cmd}}"
ESP32_CAM_SERVO_URL_TEMPLATE = f"http://{ESP32_CAM_IP}/servo?pan={{pan}}&tilt={{tilt}}"

# ============================================================================
# 5. Sensor Calibration & Thresholds
# ============================================================================
BATTERY_VOLTAGE_DIVIDER_FACTOR = 4.12
BATTERY_FULL_VOLTAGE = 12.4
BATTERY_EMPTY_VOLTAGE = 10.2

GAS_MQ9_HAZARD_THRESHOLD = 150.0    # PPM threshold for gas warning
GAS_MQ135_TOXIC_THRESHOLD = 400.0   # PPM threshold for toxic gas warning

TEMP_WARNING_THRESHOLD = 35.0       # deg C
TEMP_CRITICAL_THRESHOLD = 50.0      # deg C

LIDAR_WARN_DISTANCE = 60.0          # cm close obstacle warning
LIDAR_CRITICAL_DISTANCE = 80.0      # cm structural proximity limit

DEFAULT_GPS_BAGHDAD_LAT = 33.3128
DEFAULT_GPS_BAGHDAD_LNG = 44.3615

# ============================================================================
# 6. Computer Vision & AI Inference Settings
# ============================================================================
FRAME_WIDTH = 640
FRAME_HEIGHT = 480
DEFAULT_FPS = 30.0

YOLO_PERSON_MODEL_PATH = os.path.join(BASE_DIR, "yolov8n.pt")
YOLO_FIRE_MODEL_PATH = os.path.join(BASE_DIR, "yolov8n_fire.pt")

VISION_MODES = ["RGB", "THERMAL", "INFRARED", "FUSION"]

# ============================================================================
# 7. WiFi CSI Sensing Extensibility Configuration
# ============================================================================
WIFI_CSI_ENABLED = False
WIFI_CSI_SAMPLE_RATE_HZ = 100
WIFI_CSI_SUBCARRIERS = 64
