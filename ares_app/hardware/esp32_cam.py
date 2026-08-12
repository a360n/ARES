"""
ARES ESP32-CAM Hardware Stream & Control Link
"""

import time
import json
import cv2
import threading
import urllib.request
from ares_app.config import ESP32_CAM_STREAM_URL, ESP32_CAM_TELEMETRY_URL, ESP32_CAM_IP

_latest_physical_frame = None
_latest_physical_frame_lock = threading.Lock()
_latest_physical_telemetry = {}
_latest_physical_telemetry_lock = threading.Lock()

_reader_thread = None
_fetcher_thread = None


def get_latest_physical_frame():
    with _latest_physical_frame_lock:
        if _latest_physical_frame is not None:
            return _latest_physical_frame.copy()
        return None


def get_latest_physical_telemetry():
    with _latest_physical_telemetry_lock:
        return _latest_physical_telemetry.copy()


def physical_camera_stream_reader(get_realtime_active_fn):
    """Background loop reading MJPEG stream from ESP32-CAM via OpenCV."""
    global _latest_physical_frame
    cap = None
    stream_url = ESP32_CAM_STREAM_URL

    while True:
        realtime_active = get_realtime_active_fn()
        if not realtime_active:
            if cap is not None:
                cap.release()
                cap = None
            time.sleep(1.0)
            continue

        if cap is None:
            print(f"[Physical Camera] Connecting to ESP32-CAM MJPEG stream at {stream_url}...")
            cap = cv2.VideoCapture(stream_url)

        if not cap.isOpened():
            print("[Physical Camera] Stream failed to open. Retrying in 2s...")
            cap.release()
            cap = None
            time.sleep(2.0)
            continue

        ret, frame = cap.read()
        if ret and frame is not None:
            with _latest_physical_frame_lock:
                _latest_physical_frame = frame
        else:
            print("[Physical Camera] Frame read error or connection dropped. Reconnecting...")
            cap.release()
            cap = None
            time.sleep(1.0)


def physical_telemetry_fetcher(get_realtime_active_fn, on_telemetry_updated_fn=None):
    """Fetches sensor JSON payloads from ESP32-CAM every 500ms."""
    global _latest_physical_telemetry
    url = ESP32_CAM_TELEMETRY_URL

    while True:
        realtime_active = get_realtime_active_fn()
        if not realtime_active:
            time.sleep(1.0)
            continue

        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=0.4) as response:
                payload = json.loads(response.read().decode('utf-8'))
                with _latest_physical_telemetry_lock:
                    _latest_physical_telemetry = payload
                if on_telemetry_updated_fn:
                    on_telemetry_updated_fn(payload)
        except Exception:
            pass

        time.sleep(0.5)


def transmit_robot_command_direct(new_cmd, sim_config_ref=None, sim_lock=None):
    """Sends movement command directly to ESP32-CAM (emulating keypress) asynchronously with burst stop logic."""
    actual_cmd = new_cmd
    if new_cmd == 'a': actual_cmd = 'd'
    elif new_cmd == 'd': actual_cmd = 'a'
    elif new_cmd == 'w': actual_cmd = 's'
    elif new_cmd == 's': actual_cmd = 'w'
    elif new_cmd in ['x', 'STOP', 'STANDBY']: actual_cmd = 'x'

    if sim_config_ref and sim_lock:
        with sim_lock:
            sim_config_ref["last_sent_physical_command"] = actual_cmd

    def _send():
        url = f"http://{ESP32_CAM_IP}/move?dir={actual_cmd}"
        try:
            urllib.request.urlopen(url, timeout=0.3).close()
            print(f"[Robot Direct Keypress] Dispatched '{actual_cmd}' (input: '{new_cmd}') to ESP32-CAM.")
        except Exception as e:
            print(f"[Robot Direct Link Error] Command '{actual_cmd}' failed: {e}")

        if actual_cmd == 'x':
            time.sleep(0.05)
            try:
                urllib.request.urlopen(url, timeout=0.3).close()
            except Exception:
                pass

    threading.Thread(target=_send, daemon=True).start()


def transmit_robot_command_if_new(new_cmd, sim_config_ref, sim_lock):
    """Dispatches movement command to ESP32-CAM matching Test_interface.js motor direction inversion."""
    actual_cmd = new_cmd
    if new_cmd == 'a': actual_cmd = 'd'
    elif new_cmd == 'd': actual_cmd = 'a'
    elif new_cmd == 'w': actual_cmd = 's'
    elif new_cmd == 's': actual_cmd = 'w'
    elif new_cmd in ['x', 'STOP', 'STANDBY']: actual_cmd = 'x'

    with sim_lock:
        last_sent = sim_config_ref.get("last_sent_physical_command", "x")
        # Always allow 'x' (stop) through immediately
        if actual_cmd != 'x' and last_sent == actual_cmd:
            return
        sim_config_ref["last_sent_physical_command"] = actual_cmd

    def _send():
        url = f"http://{ESP32_CAM_IP}/move?dir={actual_cmd}"
        try:
            urllib.request.urlopen(url, timeout=0.3).close()
            print(f"[Robot Hardware] Dispatched movement command '{actual_cmd}' (input: '{new_cmd}') to ESP32-CAM.")
        except Exception as e:
            print(f"[Robot Hardware Link Error] Command '{actual_cmd}' failed: {e}")

    threading.Thread(target=_send, daemon=True).start()


def transmit_realtime_servo(pan, tilt):
    """Dispatches pan/tilt servo angles to ESP32-CAM (pan: 0-180, tilt: 0-90, center: pan=90, tilt=30)."""
    pan_val = max(0, min(180, int(pan)))
    tilt_val = max(0, min(90, int(tilt)))

    def _send():
        url = f"http://{ESP32_CAM_IP}/servo?pan={pan_val}&tilt={tilt_val}"
        try:
            urllib.request.urlopen(url, timeout=0.3).close()
            print(f"[Robot Hardware] Sent Servo pan={pan_val} tilt={tilt_val} to ESP32-CAM.")
        except Exception as e:
            print(f"[Robot Hardware Servo Error] Set pan={pan_val} tilt={tilt_val} failed: {e}")

    threading.Thread(target=_send, daemon=True).start()


def start_hardware_loops(get_realtime_active_fn, on_telemetry_updated_fn=None):
    global _reader_thread, _fetcher_thread
    if _reader_thread is None or not _reader_thread.is_alive():
        _reader_thread = threading.Thread(target=physical_camera_stream_reader, args=(get_realtime_active_fn,), daemon=True)
        _reader_thread.start()

    if _fetcher_thread is None or not _fetcher_thread.is_alive():
        _fetcher_thread = threading.Thread(target=physical_telemetry_fetcher, args=(get_realtime_active_fn, on_telemetry_updated_fn), daemon=True)
        _fetcher_thread.start()
