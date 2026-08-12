"""
ARES OpenCV Video Writer Factory & MJPEG Frame Generator
"""

import os
import cv2
import time
import numpy as np
import threading
from datetime import datetime, timezone

from ares_app.config import FRAME_WIDTH, FRAME_HEIGHT, DEFAULT_FPS
from ares_app.database import db_enqueue
from ares_app.telemetry.engine import compute_telemetry, startup_baseline
from ares_app.vision.detector import YOLO_PERSON_MODEL, YOLO_FIRE_MODEL, PERSON_MODEL_LOADED, FIRE_MODEL_LOADED
from ares_app.vision.spectral_mutator import apply_spectral_mutator
from ares_app.vision.fusion import apply_thermal_fusion
from ares_app.vision.hud_overlay import draw_hud_overlays
from ares_app.hardware.esp32_cam import get_latest_physical_frame

video_buffer_lock = threading.RLock()
_active_writers = {}
_active_captures = []
_latest_frame_data = {
    "session_id": None, "frame_idx": -1, "playback_sec": -1.0,
    "jpeg_bytes": None, "timestamp": 0.0
}

active_video_writer_normal = None
active_video_writer_thermal = None
active_video_writer_noir = None
active_video_writer_fused = None

_session_agg = {
    "max_gas_ppm": 0.0, "max_temperature": 0.0, "fire_incident_triggered": False,
    "total_victims_found": 0, "_peak_victims_in_frame": 0
}
_telemetry_log_tick = 0


def reset_frame_cache():
    """Clear shared MJPEG cache."""
    with video_buffer_lock:
        _latest_frame_data["session_id"] = None
        _latest_frame_data["frame_idx"] = -1
        _latest_frame_data["playback_sec"] = -1.0
        _latest_frame_data["jpeg_bytes"] = None
        _latest_frame_data["timestamp"] = 0.0


def close_all_video_resources():
    """Release all OpenCV captures/writers safely."""
    global active_video_writer_normal, active_video_writer_thermal, active_video_writer_noir, active_video_writer_fused
    with video_buffer_lock:
        for cap_instance in list(_active_captures):
            if cap_instance is not None:
                try: cap_instance.release()
                except Exception: pass
        _active_captures.clear()

        for path, w in list(_active_writers.items()):
            if w is not None:
                try: w.release()
                except Exception: pass
        _active_writers.clear()

        for w in [active_video_writer_normal, active_video_writer_thermal, active_video_writer_noir, active_video_writer_fused]:
            if w is not None:
                try: w.release()
                except Exception: pass
        active_video_writer_normal = None
        active_video_writer_thermal = None
        active_video_writer_noir = None
        active_video_writer_fused = None


def create_video_writer(video_out_path, fps, width, height):
    """Initializes cv2.VideoWriter with fallback handling."""
    global _active_writers
    with video_buffer_lock:
        if video_out_path in _active_writers:
            w = _active_writers[video_out_path]
            if w is not None and w.isOpened():
                return w

    writer = None
    try:
        fourcc = cv2.VideoWriter_fourcc(*'avc1')
        writer = cv2.VideoWriter(video_out_path, fourcc, fps, (width, height))
        if writer is not None and writer.isOpened():
            with video_buffer_lock: _active_writers[video_out_path] = writer
            return writer
        if writer is not None: writer.release()
    except Exception: pass

    try:
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        writer = cv2.VideoWriter(video_out_path, fourcc, fps, (width, height))
        if writer is not None and writer.isOpened():
            with video_buffer_lock: _active_writers[video_out_path] = writer
            return writer
        if writer is not None: writer.release()
    except Exception: pass

    return None


def generate_video_frames(sim_config, sim_lock, global_telemetry_cache, username=None, on_session_eos_fn=None):
    """Generator wrapper with crash recovery."""
    try:
        yield from _generate_video_frames_impl(sim_config, sim_lock, global_telemetry_cache, username=username, on_session_eos_fn=on_session_eos_fn)
    except Exception as e:
        print(f"[Generator Crash Recovery] Error: {e}")
        raise
    finally:
        try:
            video_buffer_lock.release()
        except RuntimeError:
            pass


def _generate_video_frames_impl(sim_config, sim_lock, global_telemetry_cache, username=None, on_session_eos_fn=None):
    global active_video_writer_normal, active_video_writer_thermal, active_video_writer_noir, active_video_writer_fused
    global _telemetry_log_tick, _session_agg

    default_frame_idx = 0
    default_fps = DEFAULT_FPS
    iteration_count = 0
    playback_start_time = time.time()

    while True:
        frame = None
        cap = None
        fps = DEFAULT_FPS
        video_active = False

        with sim_lock:
            v_path = sim_config.get("video_path")
            is_sim = sim_config.get("is_simulating", False)

        if is_sim and v_path and os.path.exists(v_path):
            with video_buffer_lock:
                cap = cv2.VideoCapture(v_path)
                if cap.isOpened():
                    fps = cap.get(cv2.CAP_PROP_FPS)
                    if fps <= 0: fps = DEFAULT_FPS
                    video_active = True
                    _active_captures.append(cap)
                    playback_start_time = time.time() - sim_config.get("current_second", 0.0)

        frame_idx = 0

        while True:
            with sim_lock:
                current_is_sim = sim_config.get("is_simulating", False)
            if video_active and not current_is_sim:
                if cap is not None:
                    with video_buffer_lock: cap.release()
                cap = None
                video_active = False
                frame_idx = 0

            iteration_count += 1
            if username != 'admin' and iteration_count % 2 == 0:
                cached_jpeg = None
                with video_buffer_lock:
                    cached_jpeg = _latest_frame_data.get("jpeg_bytes")
                if cached_jpeg is not None:
                    yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + cached_jpeg + b'\r\n')
                    if video_active: frame_idx += 1
                    else: default_frame_idx += 1
                    time.sleep(1.0 / fps)
                    continue

            current_time = time.time()
            session_id = sim_config.get("active_session_id")
            fps_target = sim_config.get("fps", DEFAULT_FPS)
            if fps_target <= 0: fps_target = DEFAULT_FPS
            tick_threshold = (1.0 / fps_target) * 0.8

            cached_jpeg = None
            with video_buffer_lock:
                time_since_last = current_time - _latest_frame_data["timestamp"]
                if _latest_frame_data["jpeg_bytes"] is not None and time_since_last < tick_threshold:
                    cached_jpeg = _latest_frame_data["jpeg_bytes"]

            if cached_jpeg is not None:
                yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + cached_jpeg + b'\r\n')
                time.sleep(0.01)
                continue

            lock_acquired = False
            ret = False
            jpeg_bytes = None
            start_proc_time = time.time()

            try:
                video_buffer_lock.acquire()
                lock_acquired = True

                with sim_lock:
                    realtime_mode = (sim_config.get("dashboard_mode") == "realtime")

                if realtime_mode:
                    phys_frame = get_latest_physical_frame()
                    if phys_frame is not None:
                        frame = phys_frame
                        ret = True
                    else:
                        frame = np.zeros((FRAME_HEIGHT, FRAME_WIDTH, 3), dtype=np.uint8)
                        for x in range(0, FRAME_WIDTH, 40): cv2.line(frame, (x, 0), (x, FRAME_HEIGHT), (22, 28, 22), 1)
                        for y in range(0, FRAME_HEIGHT, 40): cv2.line(frame, (0, y), (FRAME_WIDTH, y), (22, 28, 22), 1)
                        cv2.putText(frame, "WAITING FOR ARES-CAMERA HARDWARE FEED...", (65, 230), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (0, 180, 255), 2, cv2.LINE_AA)
                        cv2.putText(frame, "CONNECT TO SSID: ARES-CAMERA // WPA2: ARES2026", (85, 265), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 120, 180), 1, cv2.LINE_AA)
                        ret = True

                    playback_sec = (default_frame_idx / default_fps) % 3600.0
                    default_frame_idx += 1

                elif video_active and cap is not None:
                    ret, frame = cap.read()
                    if not ret or frame is None or frame.size == 0:
                        if lock_acquired:
                            try: video_buffer_lock.release()
                            except RuntimeError: pass
                            lock_acquired = False
                        try:
                            cap.release()
                            if cap in _active_captures: _active_captures.remove(cap)
                        except Exception: pass
                        cap = None
                        video_active = False

                        should_finalize_session = False
                        with sim_lock:
                            sim_config["is_playing"] = False
                            sim_config["is_simulating"] = False
                            sim_config["launch_pending"] = False
                            sim_config["mission_aborted"] = True
                            should_finalize_session = bool(sim_config.get("session_logging_active") and sim_config.get("active_session_id"))

                        if should_finalize_session and on_session_eos_fn:
                            on_session_eos_fn()

                        reset_frame_cache()
                        global_telemetry_cache["current_live_telemetry"] = startup_baseline.copy()
                        global_telemetry_cache["trajectory"] = []
                        if session_id: global_telemetry_cache[session_id] = startup_baseline.copy()
                        print(f"[EOS] Video finished cleanly at frame {frame_idx}.")
                        break

                    playback_sec = frame_idx / fps
                    frame_idx += 1
                else:
                    playback_sec = (default_frame_idx / default_fps) % 180.0
                    default_frame_idx += 1
                    frame = np.zeros((FRAME_HEIGHT, FRAME_WIDTH, 3), dtype=np.uint8)
                    for x in range(0, FRAME_WIDTH, 40): cv2.line(frame, (x, 0), (x, FRAME_HEIGHT), (22, 28, 22), 1)
                    for y in range(0, FRAME_HEIGHT, 40): cv2.line(frame, (0, y), (FRAME_WIDTH, y), (22, 28, 22), 1)
                    radar_angle = int(playback_sec * 85) % 360
                    radar_rad = np.radians(radar_angle)
                    center = (320, 240)
                    cv2.circle(frame, center, 180, (0, 65, 0), 1)
                    cv2.circle(frame, center, 100, (0, 45, 0), 1)
                    cv2.line(frame, center, (int(center[0] + 180 * np.cos(radar_rad)), int(center[1] + 180 * np.sin(radar_rad))), (0, 180, 0), 2)
                    ret = True

                if not ret or frame is None:
                    if lock_acquired:
                        try: video_buffer_lock.release()
                        except RuntimeError: pass
                        lock_acquired = False
                    time.sleep(0.033)
                    continue

                frame = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT))
                frame_base = frame.copy()

                with sim_lock:
                    vision_mode = sim_config.get("current_vision_mode", "RGB")
                    current_is_sim = sim_config.get("is_simulating", False)
                    realtime_mode = (sim_config.get("dashboard_mode") == "realtime")

                if current_is_sim or realtime_mode:
                    tel = compute_telemetry(playback_sec, sim_config, sim_lock)
                    pos = tel["status"]["position"]
                    traj = global_telemetry_cache.get("trajectory", [])
                    if not traj: traj = [{"x": pos["x"], "y": pos["y"]}]
                    else:
                        if traj[-1]["x"] != pos["x"] or traj[-1]["y"] != pos["y"]:
                            if pos["x"] != 0.0 or pos["y"] != 0.0:
                                traj.append({"x": pos["x"], "y": pos["y"]})
                                if len(traj) > 60: traj.pop(0)
                    global_telemetry_cache["trajectory"] = traj
                    tel["status"]["trajectory"] = traj
                else:
                    tel = startup_baseline.copy()
                    global_telemetry_cache["trajectory"] = []
                    tel["status"]["trajectory"] = []

                with sim_lock:
                    tel["status"]["current_vision_mode"] = vision_mode
                    sim_config["current_live_telemetry"] = tel
                    sim_config["current_second"] = playback_sec if (current_is_sim or realtime_mode) else 0.0

                flame_state = tel["status"].get("fire_detected", False)
                gas_mq9 = tel["sensors"]["gas"]["mq9"]
                lidar_val = tel["sensors"]["ultrasonic"]["distance"]
                temp_val = tel["sensors"]["dht22"]["temperature"]

                combined_boxes = []
                ai_latency = 0.0
                models_ran = []

                if PERSON_MODEL_LOADED and YOLO_PERSON_MODEL is not None:
                    inf_start = time.time()
                    try:
                        results = YOLO_PERSON_MODEL(frame_base, verbose=False)
                        ai_latency += (time.time() - inf_start) * 1000.0
                        models_ran.append("PERSON")
                        for r in results:
                            for box in r.boxes:
                                if int(box.cls[0]) == 0:
                                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                                    conf = float(box.conf[0])
                                    w, h = x2 - x1, y2 - y1
                                    is_unconscious = (h > 0) and ((w / h) >= 1.3)
                                    color = (180, 0, 255) if is_unconscious else (0, 255, 0)
                                    label = f"CRITICAL: UNCONSCIOUS VICTIM [{conf:.2f}]" if is_unconscious else f"RESCUER/HUMAN [{conf:.2f}]"
                                    combined_boxes.append({"box": (x1, y1, x2, y2), "conf": conf, "class": "person", "color": color, "label": label})
                    except Exception: pass

                if FIRE_MODEL_LOADED and YOLO_FIRE_MODEL is not None:
                    inf_start = time.time()
                    try:
                        results = YOLO_FIRE_MODEL(frame_base, verbose=False)
                        ai_latency += (time.time() - inf_start) * 1000.0
                        models_ran.append("FIRE")
                        for r in results:
                            for box in r.boxes:
                                cls_name = YOLO_FIRE_MODEL.names.get(int(box.cls[0]), "unknown").lower()
                                if "fire" in cls_name or "smoke" in cls_name:
                                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                                    conf = float(box.conf[0])
                                    color = (0, 0, 255) if "fire" in cls_name else (0, 255, 255)
                                    label = f"FIRE {conf:.2f}" if "fire" in cls_name else f"SMOKE {conf:.2f}"
                                    combined_boxes.append({"box": (x1, y1, x2, y2), "conf": conf, "class": cls_name, "color": color, "label": label})
                    except Exception: pass
                else:
                    hsv = cv2.cvtColor(frame_base, cv2.COLOR_BGR2HSV)
                    mask1 = cv2.inRange(hsv, np.array([0, 160, 210]), np.array([18, 255, 255]))
                    mask2 = cv2.inRange(hsv, np.array([165, 160, 210]), np.array([180, 255, 255]))
                    mask = cv2.bitwise_or(mask1, mask2)
                    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)))
                    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (21, 21)))
                    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

                    raw_fire_boxes = []
                    for c in contours:
                        if cv2.contourArea(c) >= 1000:
                            x, y, w, h = cv2.boundingRect(c)
                            raw_fire_boxes.append([x, y, x + w, y + h, cv2.contourArea(c), 1])

                    for item in raw_fire_boxes:
                        x1, y1, x2, y2, area, merge_count = item
                        combined_boxes.append({
                            "box": (x1, y1, x2, y2), "conf": min(0.99, 0.70 + (area / 15000.0)),
                            "class": "fire", "color": (0, 0, 255), "label": "FIRE SOURCE" if merge_count > 1 else "AI INTERACTION: FIRE HOTSPOT"
                        })

                    if flame_state and len(raw_fire_boxes) == 0:
                        pulse = int(140 + 70 * np.sin(time.time() * 8))
                        combined_boxes.append({"box": (120, 140, 280, 320), "conf": 0.91, "class": "fire", "color": (0, 0, pulse), "label": "AI INTERACTION: FIRE HOTSPOT", "is_emulated": True})

                    if gas_mq9 > 150.0:
                        pulse = int(150 + 60 * np.sin(time.time() * 5))
                        combined_boxes.append({"box": (350, 80, 530, 240), "conf": 0.88, "class": "smoke", "color": (0, pulse, 255), "label": "AI DETECT: SMOKE CLOUD [88.5%]", "is_emulated": True})

                inference_status = "MULTI-MODEL ONLINE" if (PERSON_MODEL_LOADED and FIRE_MODEL_LOADED) else "AI FALLBACK ACTIVE"

                thermal_base = apply_spectral_mutator(frame_base.copy(), "THERMAL")
                warped_thermal_base = cv2.warpPerspective(thermal_base, np.eye(3, dtype=np.float32), (FRAME_WIDTH, FRAME_HEIGHT))

                is_thermal_lock_active = False
                for item in combined_boxes:
                    if item.get("class") == "person":
                        x1, y1, x2, y2 = item["box"]
                        w_box, h_box = x2 - x1, y2 - y1
                        is_unconscious = (h_box > 0) and ((w_box / h_box) >= 1.3)
                        cx1, cy1 = max(0, x1), max(0, y1)
                        cx2, cy2 = min(FRAME_WIDTH, x2), min(FRAME_HEIGHT, y2)
                        if cx2 > cx1 and cy2 > cy1:
                            crop = warped_thermal_base[cy1:cy2, cx1:cx2]
                            mean_r = np.mean(crop[:, :, 2])
                            temp_c = 34.0 + 5.5 * (mean_r / 255.0)
                        else: temp_c = 0.0

                        if 35.0 <= temp_c <= 38.0:
                            item["label"] = f"CONFIRMED_LIFE_SIGN // {'UNCONSCIOUS' if is_unconscious else 'HUMAN'} [{item['conf']:.2f}]"
                            item["color"] = (0, 255, 0)
                            is_thermal_lock_active = True

                fallen_count = sum(1 for item in combined_boxes if item.get("class") == "person" and "CONFIRMED_LIFE_SIGN" in item.get("label", "") and "UNCONSCIOUS" in item.get("label", ""))
                fire_present = any(item.get("class") in ["fire", "smoke"] for item in combined_boxes)

                with sim_lock:
                    sim_config["fire_visual_alert"] = fire_present
                    if "status" in sim_config["current_live_telemetry"]:
                        sim_config["current_live_telemetry"]["status"]["unconscious_victims"] = fallen_count
                        sim_config["current_live_telemetry"]["status"]["fire_detected"] = fire_present
                        sim_config["current_live_telemetry"]["status"]["thermal_lock"] = "ACTIVE" if is_thermal_lock_active else "INACTIVE"
                        sim_config["latest_ai_detections"] = combined_boxes

                    if sim_config.get("session_logging_active") and sim_config.get("active_session_id"):
                        _telemetry_log_tick += 1
                        if gas_mq9 > _session_agg["max_gas_ppm"]: _session_agg["max_gas_ppm"] = gas_mq9
                        if temp_val > _session_agg["max_temperature"]: _session_agg["max_temperature"] = temp_val
                        if fire_present: _session_agg["fire_incident_triggered"] = True
                        if fallen_count > _session_agg["_peak_victims_in_frame"]: _session_agg["_peak_victims_in_frame"] = fallen_count
                        _session_agg["total_victims_found"] = max(_session_agg["total_victims_found"], _session_agg["_peak_victims_in_frame"])

                        if _telemetry_log_tick % 15 == 0:
                            ai_summary = "; ".join([it.get("label", "") for it in combined_boxes]) if combined_boxes else "CLEAR"
                            db_enqueue(
                                'INSERT INTO telemetry_logs (session_id, timestamp, gas_mq9, gas_mq135, temperature, flame_state, lidar_distance, gps_latitude, gps_longitude, voltage, ai_detections_summary, unconscious_victims) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                                (sim_config["active_session_id"], datetime.now(timezone.utc).isoformat(),
                                 round(tel["sensors"]["gas"]["mq9"], 2), round(tel["sensors"]["gas"]["mq135"], 2),
                                 round(tel["sensors"]["dht22"]["temperature"], 2), 1 if flame_state else 0,
                                 round(tel["sensors"]["ultrasonic"]["distance"], 1), round(tel["sensors"]["gps"]["latitude"], 6),
                                 round(tel["sensors"]["gps"]["longitude"], 6), round(tel["sensors"]["power"]["voltage"], 2),
                                 ai_summary[:500], fallen_count)
                            )

                rec_normal = frame_base.copy()
                rec_thermal = thermal_base.copy()
                rec_noir = apply_spectral_mutator(frame_base.copy(), "INFRARED")
                rec_fused = apply_thermal_fusion(frame_base.copy(), thermal_base)

                draw_hud_overlays(rec_normal, combined_boxes, inference_status, ai_latency, "RGB", flame_state, gas_mq9, lidar_val, temp_val, tel, playback_sec)
                draw_hud_overlays(rec_thermal, combined_boxes, inference_status, ai_latency, "THERMAL", flame_state, gas_mq9, lidar_val, temp_val, tel, playback_sec)
                draw_hud_overlays(rec_noir, combined_boxes, inference_status, ai_latency, "INFRARED", flame_state, gas_mq9, lidar_val, temp_val, tel, playback_sec)
                draw_hud_overlays(rec_fused, combined_boxes, inference_status, ai_latency, "FUSION", flame_state, gas_mq9, lidar_val, temp_val, tel, playback_sec)

                if vision_mode == "FUSION": frame_live = apply_thermal_fusion(frame_base.copy(), thermal_base)
                else: frame_live = apply_spectral_mutator(frame_base.copy(), vision_mode)
                draw_hud_overlays(frame_live, combined_boxes, inference_status, ai_latency, vision_mode, flame_state, gas_mq9, lidar_val, temp_val, tel, playback_sec)

                target_size = (FRAME_WIDTH, FRAME_HEIGHT)
                for w, f_var, name in [(active_video_writer_normal, rec_normal, "normal"), (active_video_writer_thermal, rec_thermal, "thermal"), (active_video_writer_noir, rec_noir, "noir"), (active_video_writer_fused, rec_fused, "fused")]:
                    if w is not None:
                        try: w.write(cv2.resize(f_var, target_size))
                        except Exception: pass

                ret, jpeg = cv2.imencode('.jpg', frame_live)
                if ret:
                    jpeg_bytes = jpeg.tobytes()
                    _latest_frame_data["jpeg_bytes"] = jpeg_bytes
                    _latest_frame_data["timestamp"] = time.time()
                    _latest_frame_data["session_id"] = session_id

                with sim_lock:
                    telemetry_copy = sim_config["current_live_telemetry"].copy()
                    global_telemetry_cache["current_live_telemetry"] = telemetry_copy
                    if session_id: global_telemetry_cache[session_id] = telemetry_copy

            finally:
                if lock_acquired:
                    try: video_buffer_lock.release()
                    except RuntimeError: pass
                    lock_acquired = False

            if ret:
                yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + jpeg_bytes + b'\r\n')

            if video_active and frame_idx > 0:
                expected_dur = frame_idx / fps
                actual_dur = time.time() - playback_start_time
                drift = expected_dur - actual_dur
                if drift > 0.001: time.sleep(drift)
            else:
                elapsed = time.time() - start_proc_time
                time.sleep(max(0.001, (1.0 / fps) - elapsed))

        if cap is not None:
            with video_buffer_lock: cap.release()
