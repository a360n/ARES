"""
ARES Tactical Cyber-HUD Overlay Renderer
"""

import time
import cv2
import numpy as np
from ares_app.vision.detector import PERSON_MODEL_LOADED, FIRE_MODEL_LOADED


def draw_hud_overlays(target_frame, combined_boxes, inference_status, ai_latency, vision_mode_label, flame_state, gas_mq9, lidar_val, temp_val, tel, playback_sec):
    """Draws target identification overlays, object trackers, and system telemetry indicators."""
    for item in combined_boxes:
        x1, y1, x2, y2 = item["box"]
        color = item["color"]
        label = item["label"]
        cv2.rectangle(target_frame, (x1, y1), (x2, y2), color, 2)
        cv2.putText(target_frame, label, (x1, max(15, y1 - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)

    if not PERSON_MODEL_LOADED and not FIRE_MODEL_LOADED:
        if flame_state:
            pulse = int(140 + 70 * np.sin(time.time() * 8))
            cv2.rectangle(target_frame, (120, 140), (280, 320), (0, 0, pulse), 2)
            cv2.putText(target_frame, "EMULATOR TARGET: FIRE HAZARD LOCK [98.5%]", (120, 132),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 1, cv2.LINE_AA)

        if gas_mq9 > 150.0:
            pulse = int(150 + 60 * np.sin(time.time() * 5))
            cv2.rectangle(target_frame, (350, 80), (530, 240), (0, pulse, 255), 2)
            cv2.putText(target_frame, "EMULATOR TARGET: SMOKE CLOUD LOCK [92.1%]", (350, 72),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 140, 255), 1, cv2.LINE_AA)

    sensors = tel.get("sensors", {})
    dht22_temp = sensors.get("dht22", {}).get("temperature", 0.0)
    dht22_hum = sensors.get("dht22", {}).get("humidity", 0.0)
    mq9_val = sensors.get("gas", {}).get("mq9", 0.0)
    mq135_val = sensors.get("gas", {}).get("mq135", 0.0)
    dist_val = sensors.get("ultrasonic", {}).get("distance", 0.0)
    voltage_val = sensors.get("power", {}).get("voltage", 0.0)
    gps_info = sensors.get("gps", {})
    lat = gps_info.get("latitude", 33.3128)
    lon = gps_info.get("longitude", 44.3615)

    if dist_val < 60.0:
        cv2.rectangle(target_frame, (240, 340), (400, 440), (255, 0, 255), 2)
        cv2.putText(target_frame, "RANGE WARN: CLOSE OBSTACLE", (240, 332),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 0, 255), 1, cv2.LINE_AA)

    if not PERSON_MODEL_LOADED:
        if not flame_state and mq9_val < 150.0:
            bounce_x = int(280 + 35 * np.sin(time.time() * 1.8))
            bounce_y = int(180 + 15 * np.cos(time.time() * 1.8))
            cv2.rectangle(target_frame, (bounce_x, bounce_y), (bounce_x + 90, bounce_y + 130), (0, 255, 0), 1)
            cv2.putText(target_frame, "EMULATOR SEARCH: RESCUER/HUMAN [95%]", (bounce_x, bounce_y - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1, cv2.LINE_AA)

    # Cyber-Tactical Reticle Crosshair
    cx, cy = 320, 240
    cv2.line(target_frame, (cx - 12, cy), (cx - 4, cy), (0, 255, 0), 1)
    cv2.line(target_frame, (cx + 4, cy), (cx + 12, cy), (0, 255, 0), 1)
    cv2.line(target_frame, (cx, cy - 12), (cx, cy - 4), (0, 255, 0), 1)
    cv2.line(target_frame, (cx, cy + 4), (cx, cy + 12), (0, 255, 0), 1)

    hud_color = (0, 255, 0) if "ONLINE" in inference_status else (0, 255, 120)
    c_len = 25
    t = 2
    # Corner markers
    cv2.line(target_frame, (15, 15), (15 + c_len, 15), hud_color, t)
    cv2.line(target_frame, (15, 15), (15, 15 + c_len), hud_color, t)

    cv2.line(target_frame, (625, 15), (625 - c_len, 15), hud_color, t)
    cv2.line(target_frame, (625, 15), (625, 15 + c_len), hud_color, t)

    cv2.line(target_frame, (15, 465), (15 + c_len, 465), hud_color, t)
    cv2.line(target_frame, (15, 465), (15, 465 - c_len), hud_color, t)

    cv2.line(target_frame, (625, 465), (625 - c_len, 465), hud_color, t)
    cv2.line(target_frame, (625, 465), (625, 465 - c_len), hud_color, t)

    # Dynamic HUD info
    cv2.putText(target_frame, f"ARES PATROL FEED: {tel['status']['video_filename'].upper()}", (25, 38),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1, cv2.LINE_AA)

    time_label = f"TIMECODE: {int(playback_sec)//60:02d}:{int(playback_sec)%60:02d} / {int(tel['status']['duration'])//60:02d}:{int(tel['status']['duration'])%60:02d}"
    cv2.putText(target_frame, time_label, (25, 58),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (200, 200, 200), 1, cv2.LINE_AA)

    coord_label = f"NEO-8M GPS: {lat:.6f}, {lon:.6f}"
    cv2.putText(target_frame, coord_label, (25, 78),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (200, 200, 200), 1, cv2.LINE_AA)

    cv2.putText(target_frame, f"DHT22: {dht22_temp:.1f}C / {dht22_hum:.0f}%", (440, 38),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 255, 0), 1, cv2.LINE_AA)
    cv2.putText(target_frame, f"MQ-9: {mq9_val:.1f}ppm | MQ-135: {mq135_val:.1f}ppm", (440, 58),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 255, 120), 1, cv2.LINE_AA)
    cv2.putText(target_frame, f"RANGE: {dist_val:.1f}cm", (440, 78),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 180, 255), 1, cv2.LINE_AA)

    if flame_state:
        pulse = int(127 + 128 * np.sin(time.time() * 10))
        cv2.rectangle(target_frame, (10, 10), (630, 470), (0, 0, pulse), 2)
        cv2.putText(target_frame, "!!! HAZARD ALERT: SIMULATED FLAME !!!", (160, 445),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 255), 2, cv2.LINE_AA)
    elif gas_mq9 > 150:
        pulse = int(127 + 128 * np.sin(time.time() * 6))
        cv2.rectangle(target_frame, (10, 10), (630, 470), (0, pulse, 255), 2)
        cv2.putText(target_frame, "!!! HAZARD ALERT: SIMULATED GAS LEAK !!!", (150, 445),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 140, 255), 2, cv2.LINE_AA)
