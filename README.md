# ARES: Autonomous Rescue & Emergency System (UGV Edition)

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg?style=for-the-badge&logo=python)](https://www.python.org/)
[![Framework: Flask](https://img.shields.io/badge/Framework-Flask_2.3-emerald.svg?style=for-the-badge&logo=flask)](https://flask.palletsprojects.org/)
[![AI Vision: YOLOv8](https://img.shields.io/badge/AI_Vision-YOLOv8-orange.svg?style=for-the-badge&logo=ultralytics)](https://docs.ultralytics.com/)
[![Computer Vision: OpenCV](https://img.shields.io/badge/Computer_Vision-OpenCV_4.8-red.svg?style=for-the-badge&logo=opencv)](https://opencv.org/)
[![Platform: UGV Ground Vehicle](https://img.shields.io/badge/Platform-UGV_Autonomous_Ground_Vehicle-indigo.svg?style=for-the-badge&logo=robot)](https://github.com/a360n/ARES)
[![Tests: 22 Passed](https://img.shields.io/badge/Tests-22%20Passed%20OK-success.svg?style=for-the-badge)]()

**ARES (Autonomous Rescue & Emergency System)** is a state-of-the-art Unmanned Ground Vehicle (UGV) Mission Control & Telemetry Operations Platform engineered for disaster response, victim localization, toxic plume tracking, and hazard monitoring. 

Combining real-time multi-spectral video streams, edge AI vision models (YOLOv8), environmental sensor telemetry, keypress-emulated route navigation, and an autonomous AI search engine, ARES provides emergency operators with total situational awareness and autonomous field exploration capabilities.

---

## 🚀 Key System Features

### 🤖 1. Autonomous AI Search Engine (`/ai-objectives`)
- **Fixed Pattern Search Loop**: Drives 1 second forward (`'w'`), scans camera Left (135°) & Right (45°) for 2 seconds each, turns Right 0.5s (`'d'`), pauses 3 seconds to analyze telemetry, and repeats.
- **Vision Target Lock**: Leverages YOLOv8 Person & Fire detectors. Immediately halts UGV (`'x'`), centers camera (90°, 30°), and alerts operators upon detecting human victims or flame anomalies.
- **Environmental Threshold Halts**: Triggers target locks on toxic gas plumes (MQ-9 > 30 PPM / MQ-135 > 300 PPM) or high temperature hotspots (DHT22 ≥ 50°C).

### 🗺️ 2. Keypress-Emulated Route Planner (`/planned-routes`)
- **Metric-to-Time Translation**: Translates metric distance coordinates directly into hardware motor timings (`1 meter = 1 second` linear movement, `0.5 seconds` turns).
- **Asynchronous Burst-Stop Transmission**: Dispatches motor commands (`'w'`, `'a'`, `'s'`, `'d'`, `'x'`) directly to hardware over WiFi with double-burst stop signals (`'x'`) to prevent runaway motion on packet drop.

### 🎥 3. Multi-Spectral Vision & Live Telemetry Stream (`/dashboard`)
- **Spectral Overlays**: Supports RGB, Thermal, Infrared, and Multi-Sensor Fusion rendering modes with live HUD overlays.
- **Real-Time Feed Default**: Automatically opens dashboard in **LIVE HARDWARE FEED** mode upon launching routes or AI search objectives.
- **Visual Telemetry Map**: 2D coordinate tracker mapping UGV position, heading yaw, and trail breadcrumbs in real time.

### 🛡️ 4. Enterprise Security & Audit Infrastructure
- **Role-Based Access Control (RBAC)**: Enforces permission boundaries across Administrator, Operator, and Auditor user roles.
- **Auditing & Logging**: SQLite mission logging database with PDF/HTML mission summary report generators.

---

## 🛠️ System Architecture

```
                                  +---------------------------------------+
                                  |     ARES Mission Control Server       |
                                  |    (Flask / OpenCV / YOLOv8 / SSE)    |
                                  +-------------------+-------------------+
                                                      |
                                             WiFi Access Point
                                              (192.168.4.1)
                                                      |
                                  +-------------------+-------------------+
                                  |      ESP32-CAM Video & WiFi Link      |
                                  |     (HTTP /move, /servo, /stream)     |
                                  +-------------------+-------------------+
                                                      |
                                                 UART Serial
                                                      |
                                  +-------------------+-------------------+
                                  |    Raspberry Pi Pico 2 W Controller   |
                                  |       (Motor Drivers & Sensors)       |
                                  +---------+-------------------+---------+
                                            |                   |
                         +------------------+--+             +--+------------------+
                         |  Dual Motor Driver  |             | Sensor Array Grid   |
                         | (Left/Right Wheels) |             | DHT22 / MQ9 / MQ135 |
                         +---------------------+             | Ultrasonic / GPS    |
                                                             +---------------------+
```

---

## 📂 Modular Repository Layout

```
ARES/
├── app.py                      # Production Application Entrypoint
├── config.py                   # Centralized Configuration & Constants
├── start_ares.sh               # Quick Launch Shell Script (macOS / Linux)
├── start_ares.command          # One-Click macOS App Launcher
├── requirements.txt            # Python Dependencies Specification
├── yolov8n_fire.pt             # Specialized YOLOv8 Fire Classification Model
├── ares_app/                   # Modular Application Core
│   ├── database.py             # SQLite Mission Log & User Manager
│   ├── hardware/               # ESP32-CAM & Pico Hardware Drivers
│   ├── reports/                # PDF & HTML Report Generator Engine
│   ├── routes/                 # Blueprint HTTP API & SSE Handlers
│   ├── security/               # RBAC Auth & Security Audit Logging
│   ├── telemetry/              # Telemetry Calculation & SSE Stream Engine
│   ├── ugv/                    # Route Planner & AI Objective Search Threads
│   ├── utils/                  # Network IP Discovery & SSL Management
│   └── vision/                 # YOLOv8 Detector & Multi-Spectral Mutators
├── ARES Hardware System/       # Hardware Micro-Code & Firmware Documentation
│   ├── ESP 32 Cam/             # ESP32-CAM C++ Firmware Source
│   ├── Raspberry Pi Pico 2 W/  # MicroPython Pico 2 W Main Loop
│   └── Interface/              # Legacy Reference Interface & Specifications
├── templates/                  # Modern Glassmorphism UI Templates
│   ├── dashboard.html          # Main Operations Hub & Telemetry Canvas
│   ├── ai_objectives.html      # Autonomous AI Objective Selector
│   ├── planned_routes.html     # Custom Route Planner UI
│   ├── hardware_control.html   # Manual Teleoperation Interface
│   └── admin_settings.html     # System Security & User Management
└── tests/                      # Automated Unit Test Suite (22 Tests)
```

---

## ⚡ Quick Start & Installation Guide

### Prerequisites
- **Python 3.10+**
- **Git**
- **OpenCV & PyTorch Compatible System**

### 1. Clone & Set Up Virtual Environment

```bash
# Clone repository
git clone https://github.com/a360n/ARES.git
cd ARES

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
# On macOS / Linux:
source venv/bin/activate
# On Windows (PowerShell):
# .\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

### 2. Launch Mission Control Server

#### On macOS / Linux:
```bash
./start_ares.sh
# Or run manually:
venv/bin/python3 app.py
```

#### On Windows:
```powershell
python app.py
```

Once started, open your browser and navigate to:
- **Local Control Hub**: `https://127.0.0.1:5001`
- **Default Credentials**:
  - **Username**: `admin`
  - **Password**: `admin123`

---

## 🧪 Running Automated Unit Tests

ARES includes a full suite of automated unit tests validating database connectivity, RBAC security, telemetry calculations, vision inference, and UGV route planners.

```bash
# Run unit test suite
venv/bin/python3 -m unittest discover tests
```

---

## 📡 API Endpoints Reference

| Category | Endpoint | Method | Description |
| :--- | :--- | :--- | :--- |
| **Telemetry** | `/api/telemetry/stream` | `GET` | Real-time Server-Sent Events (SSE) telemetry feed |
| **Hardware** | `/api/hardware/manual_control` | `POST` | Dispatches manual WASD driving commands |
| **Hardware** | `/api/hardware/set_dashboard_mode` | `POST` | Switches between `simulation` and `realtime` feed modes |
| **Route Execution**| `/api/ugv/routes/launch` | `POST` | Launches planned metric route thread |
| **Route Execution**| `/api/ugv/routes/cancel` | `POST` | Emergency halts active planned route thread |
| **AI Objectives** | `/api/ugv/ai/launch` | `POST` | Launches autonomous vision AI search thread |
| **AI Objectives** | `/api/ugv/ai/cancel` | `POST` | Emergency halts active AI search thread |

---

## 📄 License & Attribution

Designed and developed for **ARES Rescue Operations**. All rights reserved.