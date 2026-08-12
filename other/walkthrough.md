# Walkthrough - ARES Hardware System Interconnectivity & Real-Time Feed Integration

This walkthrough details the changes made to connect the ARES central Flask server and dashboards (Main Dashboard, Co-Pilot Modes, Planned Routes, AI Objectives, and User Control Panels) with the physical UGV robot components (ESP32-CAM and Raspberry Pi Pico 2 W) when operating under `REALTIME FEED` (real-time hardware) mode.

---

## 1. Asynchronous Hardware Telemetry & Video Threads
Added backend thread loops in [app.py](file:///Users/alial-khazali/Documents/ARES/app.py) to manage robot connectivity:
- **`physical_camera_stream_reader()`**: Opens a background MJPEG stream connection to the robot's camera at `http://192.168.4.1:81/stream`. It decodes the incoming JPEG frames and caches them.
- **`physical_telemetry_fetcher()`**: Fetches sensor JSON packets from `http://192.168.4.1/telemetry` every 500ms, caching DHT22 weather, MQ gas, Ultrasonic distance, GPS coordinates, and Battery voltage.
- **Boot Safety Fallback**: If the MacBook/phone client is not yet connected to the robot AP, the dashboard stream viewport displays a high-tech grid overlay instructing: `CONNECT TO SSID: ARES-CAMERA // WPA2: ARES2026` rather than showing a broken resource image.

---

## 2. Dynamic GPS Coordinate Map Tracker
Integrated physical coordinates mapping inside `compute_telemetry()` in [app.py](file:///Users/alial-khazali/Documents/ARES/app.py):
- Reads the real GPS latitude and longitude values from the robot NEO-8M sensors.
- Translates delta changes relative to the Baghdad coordinates anchor `(33.3128, 44.3615)` into canvas `(X, Y)` grid points:
  $$X = 200.0 + (\text{lng} - \text{lng}_0) \times \text{scale} \times \cos(\text{lat})$$
  $$Y = 200.0 - (\text{lat} - \text{lat}_0) \times \text{scale}$$
- Animates the physical UGV movements dynamically on the 2D Tracker Grid map.

---

## 3. Secure Command Forwarding Pathway (Mixed Content Fixed)
Optimized manual controls on the `/hardware-control` interface:
- **Secure Local HTTPS Forwarder**: Bypassed browser Mixed Content blocking (which restricts HTTPS sites like `https://127.0.0.1:5001` from requesting insecure HTTP items at `http://192.168.4.1`) by introducing the `/api/hardware/forward_command` endpoint in [app.py](file:///Users/alial-khazali/Documents/ARES/app.py).
- **Asynchronous Background Dispatches**: Flask receives the secure HTTPS forward request and immediately dispatches the corresponding raw HTTP request to the ESP32-CAM (for motor driving, camera servos, and the tactical LED light) in an independent background thread. It returns an HTTP 200 immediately, avoiding browser blocking and preventing thread/socket starvation.

---

## 4. Multi-Spectral Vision & YOLO Inference on Live Feed
- The physical camera feed frames are passed through standard YOLOv8 models (`yolov8n.pt` and `yolov8n_fire.pt`) to run live Person and Fire/Smoke detection.
- Applies active spectral filters (Thermal, Infrared, Spectral Fusion) and draws the tactical HUD elements on top of the physical robot's camera feed, displaying real-time sensor metrics.

---

## 5. Rate Limit Exemptions & Polling Fixes
- **`Status Polling Rate Limit Exempted`**: Added the `@limiter.exempt` annotation to `/api/hardware/status` in [app.py](file:///Users/alial-khazali/Documents/ARES/app.py) to prevent Flask-Limiter from throwing `429 (TOO MANY REQUESTS)` errors during high-frequency client polling.
- **`180-Degree Rotation Removed`**: Removed Python 180-degree image rotation from the ESP32-CAM decoder loop, allowing frames to render upright as configured in the camera's firmware.

---

## 6. Advanced Interactive Controls & Flashlight Integration
- **`Computer vs Mobile Mode Switcher`**: Added interactive toggles on `/hardware-control` to swap layouts:
  - **Computer Mode (Default)**: Hides touch overlays. Actively binds Keyboard WASD keys to drive the UGV, and Keyboard Arrow Keys to pan/tilt camera servos.
  - **Mobile Mode**: Displays touch controls. Shows toggles to swap between overlaid D-Pad buttons and overlaid Analog Joysticks.
- **`Auto-Centering Camera Logic`**: Implemented a 50ms interval interpolation thread. Upon releasing the Arrow keys, the D-Pad camera buttons, or the Analog Joystick, the camera Pan/Tilt servos smoothly sweep back to center (Pan: 90°, Tilt: 75°). Pan range: 0° to 180°, Tilt range: 0° to 90°.
- **`Tactical front LED Flashlight Integration`**: Added an emergency flashlight card to control light state (ON/OFF) and sweep brightness intensity from `0` to `255` using a local slider. Transmits commands securely via the local forwarder endpoint.
- **`Full-Screen & Refresh Spectral Overrides`**: Added `Refresh` and `Fullscreen` buttons to the spectral override grid inside both `dashboard.html` and `hardware_control.html`.

---

## 7. Bug Fixes & Syntax Error Rectification
- Resolved a script syntax error in `templates/dashboard.html` caused by a missing closing brace `}` in the `toggleVideoFullscreen()` else-statement block, which previously blocked the entire script from being parsed by the client's browser.
- Corrected the spectral override button API fetch target in `templates/dashboard.html` from the invalid `/api/vision/spectral_override` (which returned a 404 and threw JSON parse SyntaxErrors) to the valid `/api/set_vision_mode` route.
