"""
ARES Telemetry Calculation & Timeline Engine
"""

import numpy as np
from ares_app.config import DEFAULT_GPS_BAGHDAD_LAT, DEFAULT_GPS_BAGHDAD_LNG
from ares_app.telemetry.risk_assessment import classify_hazard_level
from ares_app.hardware.esp32_cam import get_latest_physical_telemetry, transmit_robot_command_if_new

startup_baseline = {
    "status": {
        "mode": "Idle Sandbox",
        "position": {"x": 200.0, "y": 200.0},
        "video_time": 0.0,
        "video_filename": "Default Sandbox Feed",
        "is_simulating": False,
        "duration": 0.0,
        "current_vision_mode": "RGB",
        "camera_recommendation": None,
        "hazard_grade": 1,
        "hazard_status": "NORMAL",
        "unconscious_victims": 0,
        "fire_detected": False,
        "engine_power_status": "ONLINE",
        "navigation_override_status": "AUTOPILOT",
        "last_manual_command": "STANDBY",
        "trajectory": []
    },
    "sensors": {
        "dht22": {"temperature": 0.0, "humidity": 0.0},
        "gas": {"mq9": 0.0, "mq135": 0.0},
        "ultrasonic": {"distance": 0.0},
        "gps": {"latitude": DEFAULT_GPS_BAGHDAD_LAT, "longitude": DEFAULT_GPS_BAGHDAD_LNG, "altitude": 34.0, "satellites": 8},
        "power": {"voltage": 0.0}
    }
}


def get_baseline_telemetry(second=0.0, is_simulating=False, video_filename="Default Sandbox Feed", duration=0.0, current_vision_mode="RGB"):
    """Generates dynamic oscillating baseline sensor readings for telemetry simulation."""
    ultrasonic_val = 185.0 + 55.0 * np.cos(second * 0.45)
    temp_val = 22.4 + 0.15 * np.sin(second * 0.12)
    hum_val = 47.8 + 0.3 * np.cos(second * 0.06)
    mq9_val = 12.5 + 0.8 * np.sin(second * 0.7)
    mq135_val = 120.0 + 5.5 * np.cos(second * 0.35)
    voltage_val = max(10.2, 12.4 - (second * 0.005) + 0.02 * np.sin(second * 0.01))

    pos_x = 200.0 + 120.0 * np.cos(second * 0.22)
    pos_y = 200.0 + 120.0 * np.sin(second * 0.22)
    lat_val = DEFAULT_GPS_BAGHDAD_LAT + 0.001 * np.cos(second * 0.22)
    lon_val = DEFAULT_GPS_BAGHDAD_LNG + 0.001 * np.sin(second * 0.22)

    return {
        "status": {
            "mode": "Simulation Active" if is_simulating else "Idle Sandbox",
            "position": {"x": round(pos_x, 1), "y": round(pos_y, 1)},
            "video_time": round(second, 1),
            "video_filename": video_filename,
            "is_simulating": is_simulating,
            "duration": round(duration, 1),
            "current_vision_mode": current_vision_mode,
            "camera_recommendation": None,
            "hazard_grade": 1,
            "hazard_status": "NORMAL",
            "unconscious_victims": 0,
            "fire_detected": False,
            "trajectory": []
        },
        "sensors": {
            "dht22": {"temperature": round(temp_val, 2), "humidity": round(hum_val, 2)},
            "gas": {"mq9": round(mq9_val, 2), "mq135": round(mq135_val, 2)},
            "ultrasonic": {"distance": round(max(5.0, ultrasonic_val), 1)},
            "gps": {"latitude": round(lat_val, 6), "longitude": round(lon_val, 6), "altitude": 34.0, "satellites": 8},
            "power": {"voltage": round(voltage_val, 2)}
        }
    }


def compute_telemetry(second, sim_config, sim_lock):
    """Calculates active state by compounding custom timeline triggers over baseline."""
    with sim_lock:
        realtime_mode = (sim_config.get("dashboard_mode") == "realtime")
        mode = sim_config.get("ugv_mode", "USER_CONTROL")
        steps = sim_config.get("active_route_steps", [])
        ai_obj = sim_config.get("ai_objective")
        ai_tx = sim_config.get("ai_target_x")
        ai_ty = sim_config.get("ai_target_y")
        yaw_val = float(sim_config.get("yaw", 0.0))
        vision_mode = sim_config.get("current_vision_mode", "RGB")
        is_simulating = sim_config.get("is_simulating", False)
        video_filename = sim_config.get("video_filename", "Default Sandbox Feed")
        duration = sim_config.get("duration", 0.0)

    if realtime_mode:
        data = get_latest_physical_telemetry()
        lat_0 = DEFAULT_GPS_BAGHDAD_LAT
        lng_0 = DEFAULT_GPS_BAGHDAD_LNG

        def safe_float(val, fallback):
            try:
                if val is None:
                    return fallback
                if isinstance(val, str):
                    val = val.strip()
                v = float(val)
                return fallback if v == 0.0 else v
            except (ValueError, TypeError):
                return fallback

        temp_val = safe_float(data.get("temp"), 22.4)
        hum_val = safe_float(data.get("hum"), 47.8)
        mq9_val = safe_float(data.get("mq9"), 12.5)
        mq135_val = safe_float(data.get("mq135"), 120.0)
        dist_val = safe_float(data.get("distance"), 185.0)
        lat_val = safe_float(data.get("lat"), lat_0)
        lng_val = safe_float(data.get("lng"), lng_0)
        voltage_val = safe_float(data.get("battery"), 12.4)

        raw_lat_str = str(data.get("lat", "No Fix"))
        raw_lng_str = str(data.get("lng", "No Fix"))
        encR_val = safe_float(data.get("encR"), 0.0)
        encL_val = safe_float(data.get("encL"), 0.0)

        if lat_val == 0.0: lat_val = lat_0
        if lng_val == 0.0: lng_val = lng_0

        scale = 100000.0
        x_val = 200.0 + (lng_val - lng_0) * scale * np.cos(np.radians(lat_val))
        y_val = 200.0 - (lat_val - lat_0) * scale
        x_val = max(10.0, min(390.0, x_val))
        y_val = max(10.0, min(390.0, y_val))

        tel = {
            "status": {
                "mode": "Live Hardware Connection" if mode == "USER_CONTROL" else f"Autonomous: {mode}",
                "position": {"x": round(x_val, 1), "y": round(y_val, 1)},
                "video_time": round(second, 1),
                "video_filename": "Live Robot Feed",
                "is_simulating": False,
                "duration": 9999.0,
                "current_vision_mode": vision_mode,
                "camera_recommendation": None,
                "hazard_grade": 1,
                "hazard_status": "NORMAL",
                "unconscious_victims": 0,
                "fire_detected": False,
                "trajectory": []
            },
            "sensors": {
                "dht22": {"temperature": round(temp_val, 2), "humidity": round(hum_val, 2)},
                "gas": {"mq9": round(mq9_val, 2), "mq135": round(mq135_val, 2)},
                "ultrasonic": {"distance": round(dist_val, 1)},
                "gps": {
                    "latitude": round(lat_val, 6),
                    "longitude": round(lng_val, 6),
                    "raw_lat": raw_lat_str,
                    "raw_lng": raw_lng_str,
                    "display": f"{raw_lat_str}, {raw_lng_str}",
                    "altitude": 34.0,
                    "satellites": 8
                },
                "power": {"voltage": round(voltage_val, 2)},
                "encoders": {"encR": encR_val, "encL": encL_val}
            }
        }
    else:
        tel = get_baseline_telemetry(second, is_simulating, video_filename, duration, vision_mode)
        x_val, y_val = tel["status"]["position"]["x"], tel["status"]["position"]["y"]
        yaw_val = float(tel["status"].get("yaw", 0.0))

    tel["status"]["ugv_mode"] = mode

    if mode == "PLANNED_ROUTE" and steps:
        import time as _time
        realtime_mode = (sim_config.get("dashboard_mode") == "realtime")
        if realtime_mode:
            launch_time = sim_config.get("route_launch_timestamp", _time.time())
            rel_second = max(0.0, _time.time() - launch_time)
        else:
            launch_sec = sim_config.get("route_launch_second", 0.0)
            rel_second = max(0.0, second - launch_sec)

        t_accum = 0.0
        active_direction = "STOP"
        step_desc = "Route complete"
        step_found = False

        for idx, step in enumerate(steps):
            direction = step.get("direction", "FORWARD").upper()
            val = float(step.get("distance", 0))

            if direction in ["FORWARD", "BACKWARD"]:
                speed = 1.0  # 1 meter = 1 second execution rate
                step_dur = max(0.1, val / speed)
                if not step_found and rel_second < t_accum + step_dur:
                    active_direction = direction
                    step_found = True
                    step_desc = f"Step {idx+1}/{len(steps)}: {direction} {val:.1f}m ({step_dur:.1f}s)"
                    t_in_step = rel_second - t_accum
                    dist = speed * t_in_step
                    if direction == "BACKWARD": dist = -dist
                    rad = np.radians(yaw_val)
                    if not realtime_mode:
                        x_val += dist * np.sin(rad)
                        y_val -= dist * np.cos(rad)
                elif not step_found:
                    dist = val
                    if direction == "BACKWARD": dist = -dist
                    rad = np.radians(yaw_val)
                    if not realtime_mode:
                        x_val += dist * np.sin(rad)
                        y_val -= dist * np.cos(rad)
                    t_accum += step_dur
            elif direction in ["LEFT", "RIGHT"]:
                step_dur = 0.5  # Turning executes for exactly 0.5 seconds
                target_angle = val if val > 0 else 90.0
                turn_rate = target_angle / step_dur
                if not step_found and rel_second < t_accum + step_dur:
                    active_direction = direction
                    step_found = True
                    step_desc = f"Step {idx+1}/{len(steps)}: TURN {direction} (0.5s)"
                    t_in_step = rel_second - t_accum
                    delta_angle = turn_rate * t_in_step
                    if direction == "LEFT": delta_angle = -delta_angle
                    yaw_val += delta_angle
                elif not step_found:
                    delta_angle = target_angle
                    if direction == "LEFT": delta_angle = -delta_angle
                    yaw_val += delta_angle
                    t_accum += step_dur

        # If all steps finished, complete route and halt robot
        if not step_found:
            active_direction = "STOP"
            step_desc = "Route Completed // UGV Stopped"
            with sim_lock:
                sim_config["ugv_mode"] = "USER_CONTROL"
                sim_config["navigation_override_status"] = "MANUAL"
                sim_config["active_route_steps"] = []

        if not realtime_mode:
            tel["status"]["position"]["x"] = round(x_val, 1)
            tel["status"]["position"]["y"] = round(y_val, 1)

        tel["status"]["yaw"] = round(yaw_val, 1)
        tel["status"]["mode"] = f"Executing Planned Route... [{step_desc}]"

    elif mode == "AI_AUTONOMOUS" and ai_obj:
        if ai_obj == "GOTO_COORDS" and ai_tx is not None and ai_ty is not None:
            dx = ai_tx - x_val
            dy = ai_ty - y_val
            dist = np.hypot(dx, dy)
            speed = 15.0
            step_dur = dist / speed if dist > 0 else 0.1
            if second < step_dur:
                if realtime_mode:
                    target_yaw = np.degrees(np.arctan2(dx, -dy)) % 360
                    yaw_diff = (target_yaw - yaw_val + 180) % 360 - 180
                    if abs(yaw_diff) > 20:
                        transmit_robot_command_if_new("a" if yaw_diff < 0 else "d", sim_config, sim_lock)
                    else:
                        transmit_robot_command_if_new("w", sim_config, sim_lock)
                else:
                    fraction = second / step_dur
                    x_val = 200.0 + dx * fraction
                    y_val = 200.0 - dy * fraction
                    yaw_val = np.degrees(np.arctan2(dx, dy))
                tel["status"]["mode"] = "AI Autonomous: Navigating to targets..."
            else:
                if realtime_mode:
                    transmit_robot_command_if_new("x", sim_config, sim_lock)
                else:
                    x_val = ai_tx
                    y_val = ai_ty
                    yaw_val = np.degrees(np.arctan2(dx, dy))
                tel["status"]["mode"] = "AI Autonomous: Target reached"
        else:
            if realtime_mode:
                if second >= 12.0:
                    transmit_robot_command_if_new("x", sim_config, sim_lock)
                else:
                    phase = int(second * 0.5) % 4
                    if phase == 0: transmit_robot_command_if_new("w", sim_config, sim_lock)
                    elif phase == 1: transmit_robot_command_if_new("d", sim_config, sim_lock)
                    elif phase == 2: transmit_robot_command_if_new("w", sim_config, sim_lock)
                    else: transmit_robot_command_if_new("a", sim_config, sim_lock)
            else:
                x_val = 200.0 + 80.0 * np.sin(second * 0.3)
                y_val = 200.0 + 50.0 * np.cos(second * 0.15)
                yaw_val = np.degrees(second * 0.5) % 360

            tel["status"]["mode"] = f"AI Search: Hunting target ({ai_obj.replace('FIND_', '')})..."

            if second >= 12.0:
                tel["status"]["mode"] = "AI Autonomous: Objective Cleared // TARGET ACQUIRED"
                if ai_obj == "FIND_HUMAN":
                    tel["status"]["unconscious_victims"] = 1
                    tel["status"]["has_victim_lock"] = True
                elif ai_obj == "FIND_FIRE":
                    tel["status"]["fire_detected"] = True
                elif ai_obj == "FIND_GAS":
                    tel["sensors"]["gas"]["mq9"] = 280.0
                    tel["sensors"]["gas"]["mq135"] = 680.0
                elif ai_obj == "FIND_TEMP":
                    tel["sensors"]["dht22"]["temperature"] = 72.5
                    tel["sensors"]["dht22"]["humidity"] = 12.0

        if not realtime_mode:
            tel["status"]["position"]["x"] = round(x_val, 1)
            tel["status"]["position"]["y"] = round(y_val, 1)
        tel["status"]["yaw"] = round(yaw_val, 1)

    else:
        active_kf = None
        with sim_lock:
            timeline = sim_config.get("telemetry_timeline", [])
            for kf in timeline:
                if kf["second"] <= second:
                    active_kf = kf

        flame_state = False
        if active_kf:
            if "gas_ppm" in active_kf and active_kf["gas_ppm"] is not None:
                gas_val = float(active_kf["gas_ppm"])
                tel["sensors"]["gas"]["mq9"] = round(gas_val, 2)
                tel["sensors"]["gas"]["mq135"] = round(gas_val * 2.5, 2)
            if "gas_mq9" in active_kf and active_kf["gas_mq9"] is not None:
                tel["sensors"]["gas"]["mq9"] = round(float(active_kf["gas_mq9"]), 2)
            if "gas_mq135" in active_kf and active_kf["gas_mq135"] is not None:
                tel["sensors"]["gas"]["mq135"] = round(float(active_kf["gas_mq135"]), 2)
            if "flame_alert" in active_kf:
                flame_state = bool(active_kf["flame_alert"])
                tel["status"]["fire_detected"] = flame_state
            if "temperature" in active_kf and active_kf["temperature"] is not None:
                temp_val = float(active_kf["temperature"])
                tel["sensors"]["dht22"]["temperature"] = round(temp_val, 2)
                tel["sensors"]["dht22"]["humidity"] = round(max(5.0, 48.0 - (temp_val - 22.4) * 0.75), 2)
            if "lidar_distance" in active_kf and active_kf["lidar_distance"] is not None:
                tel["sensors"]["ultrasonic"]["distance"] = round(float(active_kf["lidar_distance"]) * 100.0, 1)
            if "camera_recommendation" in active_kf and active_kf["camera_recommendation"]:
                tel["status"]["camera_recommendation"] = active_kf["camera_recommendation"].upper()

    dht22_temp = tel["sensors"]["dht22"]["temperature"]
    gas_mq9 = tel["sensors"]["gas"]["mq9"]
    gas_mq135 = tel["sensors"]["gas"]["mq135"]
    ultrasonic_distance = tel["sensors"]["ultrasonic"]["distance"]
    fire_detected = tel["status"].get("fire_detected", False)

    hazard_grade, hazard_status, hazard_summary = classify_hazard_level(
        dht22_temp, gas_mq9, gas_mq135, ultrasonic_distance, fire_detected
    )

    tel["status"]["hazard_grade"] = hazard_grade
    tel["status"]["hazard_status"] = hazard_status
    tel["status"]["hazard_summary"] = hazard_summary
    tel["status"]["hazard_level"] = hazard_grade
    tel["hazard_level"] = hazard_grade

    with sim_lock:
        nav_mode = sim_config.get("navigation_override_status", "AUTOPILOT")
        engine_status = sim_config.get("engine_power_status", "ONLINE")
        last_cmd = sim_config.get("last_manual_command", "STANDBY")
        man_x = sim_config.get("manual_x", 50.0)
        man_y = sim_config.get("manual_y", 50.0)

    tel["status"]["navigation_override_status"] = nav_mode
    tel["status"]["engine_power_status"] = engine_status
    tel["status"]["last_manual_command"] = last_cmd
    tel["status"]["manual_x"] = man_x
    tel["status"]["manual_y"] = man_y

    if mode == "USER_CONTROL":
        if nav_mode == "MANUAL":
            tel["status"]["position"]["x"] = round(man_x, 1)
            tel["status"]["position"]["y"] = round(man_y, 1)

    if engine_status == "OFFLINE":
        tel["status"]["position"]["x"] = 0.0
        tel["status"]["position"]["y"] = 0.0
        tel["status"]["mode"] = "System Offline // UGV Powered Down"
        tel["sensors"]["ultrasonic"]["distance"] = 0.0
        tel["sensors"]["gas"]["mq9"] = 0.0
        tel["sensors"]["gas"]["mq135"] = 0.0
        tel["sensors"]["dht22"]["temperature"] = 0.0
        tel["sensors"]["dht22"]["humidity"] = 0.0
        tel["sensors"]["power"]["voltage"] = 0.0

    return tel
