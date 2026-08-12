"""
ARES AI Autonomous Search Objectives Engine
"""

import time
import threading
from ares_app.hardware.esp32_cam import transmit_robot_command_direct, transmit_realtime_servo

VALID_AI_OBJECTIVES = ["FIND_HUMAN", "FIND_FIRE", "FIND_GAS", "FIND_TEMP"]

_ai_cancel_flag = False
_active_ai_thread = None


def launch_ai_search_objective(sim_config, sim_lock, objective, target_x=None, target_y=None):
    global _ai_cancel_flag, _active_ai_thread
    if objective not in VALID_AI_OBJECTIVES:
        raise ValueError(f"Invalid AI objective: {objective}")

    with sim_lock:
        _ai_cancel_flag = False
        sim_config["ugv_mode"] = "AI_AUTONOMOUS"
        sim_config["navigation_override_status"] = "AUTOPILOT"
        sim_config["dashboard_mode"] = "realtime"
        sim_config["ai_objective"] = objective
        sim_config["active_route_steps"] = []

        if "current_live_telemetry" in sim_config and "status" in sim_config["current_live_telemetry"]:
            sim_config["current_live_telemetry"]["status"]["ugv_mode"] = "AI_AUTONOMOUS"
            sim_config["current_live_telemetry"]["status"]["navigation_override_status"] = "AUTOPILOT"

    def _execute_search():
        global _ai_cancel_flag
        print(f"[AI Search Thread] Launched autonomous objective search: '{objective}'")

        def check_target_found():
            with sim_lock:
                detections = sim_config.get("latest_ai_detections", [])
                tel = sim_config.get("current_live_telemetry", {})
                sensors = tel.get("sensors", {})

            det_classes = [d.get("class", "").lower() for d in detections]

            if objective == "FIND_HUMAN":
                if any("person" in c or "human" in c for c in det_classes):
                    return True, "HUMAN TARGET LOCATED"
            elif objective == "FIND_FIRE":
                if any("fire" in c or "smoke" in c for c in det_classes):
                    return True, "FIRE ANOMALY DETECTED"
            elif objective == "FIND_GAS":
                gas_mq9 = float(sensors.get("gas", {}).get("mq9", 0))
                gas_mq135 = float(sensors.get("gas", {}).get("mq135", 0))
                if gas_mq9 > 30.0 or gas_mq135 > 300.0:
                    return True, f"TOXIC GAS PLUME LOCATED ({max(gas_mq9, gas_mq135):.1f} PPM)"
            elif objective == "FIND_TEMP":
                temp = float(sensors.get("dht22", {}).get("temperature", 0))
                if temp >= 50.0:
                    return True, f"HIGH TEMPERATURE HOTSPOT LOCATED ({temp:.1f}°C)"

            return False, None

        def on_target_found(reason):
            print(f"[AI Search Thread] SUCCESS: {reason}")
            transmit_robot_command_direct("x", sim_config, sim_lock)
            transmit_realtime_servo(90, 30)
            with sim_lock:
                sim_config["ugv_mode"] = "USER_CONTROL"
                sim_config["navigation_override_status"] = "MANUAL"
                if "current_live_telemetry" in sim_config and "status" in sim_config["current_live_telemetry"]:
                    sim_config["current_live_telemetry"]["status"]["ugv_mode"] = "USER_CONTROL"
                    sim_config["current_live_telemetry"]["status"]["navigation_override_status"] = "MANUAL"
                    sim_config["current_live_telemetry"]["status"]["mode"] = f"TARGET FOUND: {reason} // UGV Stopped"

        def run_action(cmd, duration, desc):
            with sim_lock:
                if "current_live_telemetry" in sim_config and "status" in sim_config["current_live_telemetry"]:
                    sim_config["current_live_telemetry"]["status"]["mode"] = f"AI Search [{objective}]: {desc}"

            transmit_robot_command_direct(cmd, sim_config, sim_lock)
            t0 = time.time()
            while time.time() - t0 < duration:
                with sim_lock:
                    if _ai_cancel_flag or sim_config.get("ugv_mode") != "AI_AUTONOMOUS":
                        transmit_robot_command_direct("x", sim_config, sim_lock)
                        return False, None
                found, reason = check_target_found()
                if found:
                    return True, reason
                time.sleep(0.05)

            transmit_robot_command_direct("x", sim_config, sim_lock)
            time.sleep(0.15)
            return True, None

        def run_camera_scan():
            with sim_lock:
                if "current_live_telemetry" in sim_config and "status" in sim_config["current_live_telemetry"]:
                    sim_config["current_live_telemetry"]["status"]["mode"] = f"AI Search [{objective}]: Scanning Camera (Left 2s & Right 2s)"

            transmit_robot_command_direct("x", sim_config, sim_lock)

            # Pan Left (135°) - Hold 2.0 seconds while checking target
            transmit_realtime_servo(135, 30)
            t0 = time.time()
            while time.time() - t0 < 2.0:
                with sim_lock:
                    if _ai_cancel_flag or sim_config.get("ugv_mode") != "AI_AUTONOMOUS":
                        transmit_realtime_servo(90, 30)
                        return False, None
                found, reason = check_target_found()
                if found:
                    transmit_realtime_servo(90, 30)
                    return True, reason
                time.sleep(0.05)

            # Pan Right (45°) - Hold 2.0 seconds while checking target
            transmit_realtime_servo(45, 30)
            t0 = time.time()
            while time.time() - t0 < 2.0:
                with sim_lock:
                    if _ai_cancel_flag or sim_config.get("ugv_mode") != "AI_AUTONOMOUS":
                        transmit_realtime_servo(90, 30)
                        return False, None
                found, reason = check_target_found()
                if found:
                    transmit_realtime_servo(90, 30)
                    return True, reason
                time.sleep(0.05)

            # Center Camera (90°)
            transmit_realtime_servo(90, 30)
            time.sleep(0.2)
            return True, None

        step_count = 0
        while True:
            with sim_lock:
                if _ai_cancel_flag or sim_config.get("ugv_mode") != "AI_AUTONOMOUS":
                    break

            found, reason = check_target_found()
            if found:
                on_target_found(reason)
                break

            step_count += 1

            # 1. Drive FORWARD 1s ('w')
            ok, target_reason = run_action("w", 1.0, f"Step #{step_count}: Driving Forward 1s")
            if not ok or _ai_cancel_flag: break
            if target_reason:
                on_target_found(target_reason)
                break

            # 2. Camera Scan Left (2s) & Right (2s)
            ok, target_reason = run_camera_scan()
            if not ok or _ai_cancel_flag: break
            if target_reason:
                on_target_found(target_reason)
                break

            # 3. Turn RIGHT 0.5s ('d')
            ok, target_reason = run_action("d", 0.5, f"Step #{step_count}: Turning Right 0.5s")
            if not ok or _ai_cancel_flag: break
            if target_reason:
                on_target_found(target_reason)
                break

            # 4. Stop & Hold 3s at turn position
            ok, target_reason = run_action("x", 3.0, f"Step #{step_count}: Stopped 3s After Turn")
            if not ok or _ai_cancel_flag: break
            if target_reason:
                on_target_found(target_reason)
                break

            # 5. Camera Scan Left (2s) & Right (2s)
            ok, target_reason = run_camera_scan()
            if not ok or _ai_cancel_flag: break
            if target_reason:
                on_target_found(target_reason)
                break

        # Final Stop and Reset Camera
        transmit_robot_command_direct("x", sim_config, sim_lock)
        transmit_realtime_servo(90, 30)

    _active_ai_thread = threading.Thread(target=_execute_search, daemon=True)
    _active_ai_thread.start()

    return objective


def cancel_ai_search(sim_config, sim_lock):
    global _ai_cancel_flag
    _ai_cancel_flag = True

    with sim_lock:
        sim_config["ugv_mode"] = "USER_CONTROL"
        sim_config["navigation_override_status"] = "MANUAL"
        sim_config["ai_objective"] = None
        sim_config["last_sent_physical_command"] = "x"
        if "current_live_telemetry" in sim_config and "status" in sim_config["current_live_telemetry"]:
            sim_config["current_live_telemetry"]["status"]["ugv_mode"] = "USER_CONTROL"
            sim_config["current_live_telemetry"]["status"]["navigation_override_status"] = "MANUAL"
            sim_config["current_live_telemetry"]["status"]["mode"] = "AI Search Cancelled // UGV Stopped"

    transmit_robot_command_direct("x", sim_config, sim_lock)
    transmit_realtime_servo(90, 30)
    return True
