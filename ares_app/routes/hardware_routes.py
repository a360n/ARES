"""
ARES Co-Pilot Hardware Override Routes Blueprint
"""

from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from ares_app.security.auth import permission_required
from ares_app.security.audit import log_security_event
from ares_app.hardware.command_queue import enqueue_hardware_command

hardware_bp = Blueprint('hardware_bp', __name__)
_sim_config = None
_sim_lock = None
_global_telemetry_cache = None


def init_hardware_bp(state_refs):
    global _sim_config, _sim_lock, _global_telemetry_cache
    _sim_config = state_refs["sim_config"]
    _sim_lock = state_refs["sim_lock"]
    _global_telemetry_cache = state_refs["global_telemetry_cache"]


@hardware_bp.route('/api/hardware/toggle_power', methods=['POST'])
@login_required
@permission_required('power_toggle_robot')
def toggle_power():
    if not request.is_json:
        return jsonify({"error": "JSON payload required"}), 400
    status = request.get_json().get("status", "ONLINE").upper()
    if status not in ["ONLINE", "OFFLINE"]:
        return jsonify({"error": "Invalid engine status"}), 400

    with _sim_lock:
        _sim_config["engine_power_status"] = status
        if "current_live_telemetry" in _sim_config and "status" in _sim_config["current_live_telemetry"]:
            _sim_config["current_live_telemetry"]["status"]["engine_power_status"] = status
            if status == "OFFLINE":
                _sim_config["current_live_telemetry"]["status"]["position"] = {"x": 0.0, "y": 0.0}
            telemetry_copy = _sim_config["current_live_telemetry"].copy()
            _global_telemetry_cache["current_live_telemetry"] = telemetry_copy

    log_security_event(current_user.username, f"TOGGLE_ENGINE_POWER:{status}", "SUCCESS", f"Power status set to {status}.")
    return jsonify({"status": "power_updated", "engine_power_status": status})


@hardware_bp.route('/api/hardware/toggle_navigation', methods=['POST'])
@login_required
@permission_required('toggle_navigation_mode')
def toggle_navigation():
    if not request.is_json:
        return jsonify({"error": "JSON payload required"}), 400
    status = request.get_json().get("status", "AUTOPILOT").upper()
    if status not in ["AUTOPILOT", "MANUAL"]:
        return jsonify({"error": "Invalid navigation status"}), 400

    with _sim_lock:
        _sim_config["navigation_override_status"] = status
        if "current_live_telemetry" in _sim_config and "status" in _sim_config["current_live_telemetry"]:
            _sim_config["current_live_telemetry"]["status"]["navigation_override_status"] = status
            telemetry_copy = _sim_config["current_live_telemetry"].copy()
            _global_telemetry_cache["current_live_telemetry"] = telemetry_copy

    log_security_event(current_user.username, f"TOGGLE_NAVIGATION:{status}", "SUCCESS", f"Navigation set to {status}.")
    return jsonify({"status": "navigation_updated", "navigation_override_status": status})


@hardware_bp.route('/api/hardware/manual_control', methods=['POST'])
@login_required
@permission_required('manual_robot_control')
def manual_control():
    if not request.is_json:
        return jsonify({"error": "JSON payload required"}), 400
    data = request.get_json()
    command = data.get("command", "STANDBY").upper()
    x = data.get("x")
    y = data.get("y")

    with _sim_lock:
        realtime_mode = (_sim_config.get("dashboard_mode") == "realtime")
        if not realtime_mode:
            if _sim_config["engine_power_status"] == "OFFLINE":
                return jsonify({"error": "UGV engine is OFFLINE"}), 400
            if _sim_config["navigation_override_status"] != "MANUAL":
                return jsonify({"error": "Autopilot is active"}), 400

        _sim_config["last_manual_command"] = command
        if x is not None: _sim_config["manual_x"] = float(x)
        if y is not None: _sim_config["manual_y"] = float(y)

        if "current_live_telemetry" in _sim_config and "status" in _sim_config["current_live_telemetry"]:
            _sim_config["current_live_telemetry"]["status"]["last_manual_command"] = command
            if x is not None: _sim_config["current_live_telemetry"]["status"]["position"]["x"] = round(float(x), 1)
            if y is not None: _sim_config["current_live_telemetry"]["status"]["position"]["y"] = round(float(y), 1)
            telemetry_copy = _sim_config["current_live_telemetry"].copy()
            _global_telemetry_cache["current_live_telemetry"] = telemetry_copy

        if realtime_mode:
            intensity = float(data.get("intensity", 1.0))
            if command.startswith("SCAN_"):
                if command == "SCAN_LEFT": _sim_config["pan"] = max(0, _sim_config["pan"] - int(10 * intensity))
                elif command == "SCAN_RIGHT": _sim_config["pan"] = min(180, _sim_config["pan"] + int(10 * intensity))
                elif command == "SCAN_UP": _sim_config["tilt"] = min(90, _sim_config["tilt"] + int(10 * intensity))
                elif command == "SCAN_DOWN": _sim_config["tilt"] = max(0, _sim_config["tilt"] - int(10 * intensity))

    log_security_event(current_user.username, f"MANUAL_COMMAND:{command}", "SUCCESS", f"x={x}, y={y}")
    return jsonify({
        "status": "manual_control_success",
        "last_manual_command": command,
        "manual_x": _sim_config["manual_x"],
        "manual_y": _sim_config["manual_y"]
    })


@hardware_bp.route('/api/hardware/set_dashboard_mode', methods=['POST'])
@login_required
def set_dashboard_mode():
    if not request.is_json:
        return jsonify({"error": "JSON payload required"}), 400
    mode = request.get_json().get("mode", "simulation")
    if mode not in ["simulation", "realtime"]:
        return jsonify({"error": "Invalid mode"}), 400

    with _sim_lock:
        _sim_config["dashboard_mode"] = mode

    return jsonify({"status": "success", "dashboard_mode": mode})


@hardware_bp.route('/api/hardware/status', methods=['GET'])
@login_required
def hardware_status():
    with _sim_lock:
        return jsonify(_sim_config.get("current_live_telemetry", {}).copy())


@hardware_bp.route('/api/hardware/forward_command', methods=['GET', 'POST'])
def forward_hardware_command():
    path = request.args.get('path', '')
    query_params = [f"{k}={v}" for k, v in request.args.items() if k != 'path']
    query_string = "&".join(query_params)

    from ares_app.config import ESP32_CAM_IP
    target_url = f"http://{ESP32_CAM_IP}/{path}"
    if query_string: target_url += f"?{query_string}"

    enqueue_hardware_command(target_url)
    return jsonify({"status": "queued", "url": target_url})
