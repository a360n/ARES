"""
ARES Planned Routes CRUD & Execution Solver
"""

import json
from datetime import datetime
from ares_app.database import db_enqueue, db_read


def save_route(name, steps):
    if not name or not steps:
        raise ValueError("Name and steps are required")
    steps_json = json.dumps(steps)
    created_at = datetime.now().isoformat()
    db_enqueue('INSERT INTO ugv_routes (name, steps, created_at) VALUES (?, ?, ?)', (name, steps_json, created_at))
    return True


def fetch_all_routes():
    rows = db_read('SELECT * FROM ugv_routes ORDER BY created_at DESC')
    result = []
    for row in rows:
        result.append({
            "id": row["id"],
            "name": row["name"],
            "steps": json.loads(row["steps"]),
            "created_at": row["created_at"]
        })
    return result


def delete_route(route_id):
    db_enqueue('DELETE FROM ugv_routes WHERE id = ?', (route_id,))
    return True


import time
import threading
from ares_app.hardware.esp32_cam import transmit_robot_command_direct, transmit_robot_command_if_new

_route_cancel_flag = False
_active_route_thread = None


def launch_route(sim_config, sim_lock, route_id):
    global _route_cancel_flag, _active_route_thread
    rows = db_read('SELECT * FROM ugv_routes WHERE id = ?', (route_id,))
    if not rows:
        raise KeyError("Route not found")
    route = rows[0]
    steps = json.loads(route["steps"])

    with sim_lock:
        _route_cancel_flag = False
        sim_config["ugv_mode"] = "PLANNED_ROUTE"
        sim_config["navigation_override_status"] = "AUTOPILOT"
        sim_config["dashboard_mode"] = "realtime"
        sim_config["active_route_steps"] = steps
        sim_config["active_route_step_index"] = 0
        sim_config["active_route_step_start_time"] = sim_config.get("current_second", 0.0)
        sim_config["route_launch_timestamp"] = time.time()
        sim_config["route_launch_second"] = sim_config.get("current_second", 0.0)
        sim_config["last_sent_physical_command"] = None
        sim_config["ai_objective"] = None

        if "current_live_telemetry" in sim_config and "status" in sim_config["current_live_telemetry"]:
            sim_config["current_live_telemetry"]["status"]["ugv_mode"] = "PLANNED_ROUTE"
            sim_config["current_live_telemetry"]["status"]["navigation_override_status"] = "AUTOPILOT"

    def _execute_route():
        global _route_cancel_flag
        print(f"[Route Executor Thread] Starting route '{route['name']}' ({len(steps)} steps)...")

        dir_map = {"FORWARD": "w", "BACKWARD": "s", "LEFT": "a", "RIGHT": "d"}

        for idx, step in enumerate(steps):
            with sim_lock:
                if _route_cancel_flag or sim_config.get("ugv_mode") != "PLANNED_ROUTE":
                    print("[Route Executor Thread] Route cancelled.")
                    break
                sim_config["active_route_step_index"] = idx

            direction = step.get("direction", "FORWARD").upper()
            val = float(step.get("distance", 0))
            cmd_letter = dir_map.get(direction, "w")

            if direction in ["FORWARD", "BACKWARD"]:
                duration = max(0.1, val)  # 1 meter = 1 second
                desc = f"Step {idx+1}/{len(steps)}: Driving {direction} {val:.1f}m ({duration:.1f}s)"
            else:
                duration = 0.5  # Turning executes for exactly 0.5s
                desc = f"Step {idx+1}/{len(steps)}: Turning {direction} (0.5s)"

            print(f"[Route Executor Thread] {desc}")
            with sim_lock:
                if "current_live_telemetry" in sim_config and "status" in sim_config["current_live_telemetry"]:
                    sim_config["current_live_telemetry"]["status"]["mode"] = f"Executing Planned Route... [{desc}]"

            # Emulate keypress by sending movement command
            transmit_robot_command_direct(cmd_letter, sim_config, sim_lock)

            # Hold command for duration, polling cancel flag every 50ms
            t_start = time.time()
            while time.time() - t_start < duration:
                if _route_cancel_flag or sim_config.get("ugv_mode") != "PLANNED_ROUTE":
                    break
                time.sleep(0.05)

            # Send explicit STOP ('x') after step and wait 150ms gap
            transmit_robot_command_direct("x", sim_config, sim_lock)
            time.sleep(0.15)

        # Send final STOP ('x') and reset mode to USER_CONTROL
        transmit_robot_command_direct("x", sim_config, sim_lock)
        with sim_lock:
            sim_config["ugv_mode"] = "USER_CONTROL"
            sim_config["navigation_override_status"] = "MANUAL"
            sim_config["active_route_steps"] = []
            if "current_live_telemetry" in sim_config and "status" in sim_config["current_live_telemetry"]:
                sim_config["current_live_telemetry"]["status"]["ugv_mode"] = "USER_CONTROL"
                sim_config["current_live_telemetry"]["status"]["navigation_override_status"] = "MANUAL"
                sim_config["current_live_telemetry"]["status"]["mode"] = "Route Completed // UGV Stopped"

        print(f"[Route Executor Thread] Route '{route['name']}' complete. UGV stopped.")

    _active_route_thread = threading.Thread(target=_execute_route, daemon=True)
    _active_route_thread.start()

    return route["name"]


def cancel_route(sim_config, sim_lock):
    global _route_cancel_flag
    _route_cancel_flag = True

    with sim_lock:
        sim_config["ugv_mode"] = "USER_CONTROL"
        sim_config["navigation_override_status"] = "MANUAL"
        sim_config["active_route_steps"] = []
        sim_config["active_route_step_index"] = 0
        sim_config["last_sent_physical_command"] = "x"
        if "current_live_telemetry" in sim_config and "status" in sim_config["current_live_telemetry"]:
            sim_config["current_live_telemetry"]["status"]["ugv_mode"] = "USER_CONTROL"
            sim_config["current_live_telemetry"]["status"]["navigation_override_status"] = "MANUAL"
            sim_config["current_live_telemetry"]["status"]["mode"] = "Route Cancelled // UGV Stopped"

    transmit_robot_command_direct("x", sim_config, sim_lock)
    return True
