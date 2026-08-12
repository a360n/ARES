"""
ARES Simulation & Video Stream Routes Blueprint
"""

import os
import json
import uuid
import threading
import cv2
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request, Response, abort
from werkzeug.utils import secure_filename
from flask_login import login_required, current_user

from ares_app.config import UPLOAD_FOLDER, REPORTS_DIR
from ares_app.database import db_enqueue
from ares_app.security.auth import permission_required
from ares_app.security.audit import log_security_event
from ares_app.telemetry.engine import startup_baseline
from ares_app.vision.generator import (
    generate_video_frames, reset_frame_cache, close_all_video_resources, create_video_writer
)
from ares_app.reports.service import generate_reports_deferred

simulation_bp = Blueprint('simulation_bp', __name__)
_sim_config = None
_sim_lock = None
_global_telemetry_cache = None
_launch_thread = None


def init_simulation_bp(state_refs):
    global _sim_config, _sim_lock, _global_telemetry_cache
    _sim_config = state_refs["sim_config"]
    _sim_lock = state_refs["sim_lock"]
    _global_telemetry_cache = state_refs["global_telemetry_cache"]


def finalize_active_session_manually():
    session_id = _sim_config.get("active_session_id")
    if not session_id or not _sim_config.get("session_logging_active"):
        return

    _sim_config["session_logging_active"] = False
    duration = _sim_config.get("current_second", 0.0)

    db_enqueue(
        '''UPDATE sessions SET end_time=?, duration_seconds=? WHERE session_id=?''',
        (datetime.now(timezone.utc).isoformat(), round(duration, 1), session_id)
    )
    close_all_video_resources()
    threading.Thread(target=generate_reports_deferred, args=(session_id,), daemon=True).start()
    _sim_config["active_session_id"] = None


def simulation_pipeline_loop(saved_path, filename, formatted_timeline, username):
    try:
        cap = cv2.VideoCapture(saved_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0: fps = 30.0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        duration = total_frames / fps
        cap.release()

        with _sim_lock:
            _sim_config["video_path"] = saved_path
            _sim_config["video_filename"] = filename
            _sim_config["telemetry_timeline"] = formatted_timeline
            _sim_config["is_simulating"] = True
            _sim_config["launch_pending"] = False
            _sim_config["mission_aborted"] = False
            _sim_config["duration"] = duration
            _sim_config["current_second"] = 0.0
            _sim_config["current_vision_mode"] = "RGB"
            _sim_config["fps"] = fps
            _sim_config["width"] = width
            _sim_config["height"] = height

            new_session_id = str(uuid.uuid4())[:8]
            _sim_config["active_session_id"] = new_session_id
            _sim_config["session_logging_active"] = True
            _global_telemetry_cache["current_live_telemetry"] = startup_baseline.copy()
            _global_telemetry_cache["trajectory"] = []
            _sim_config["current_live_telemetry"] = startup_baseline.copy()
            if new_session_id:
                _global_telemetry_cache[new_session_id] = startup_baseline.copy()

            session_dir = os.path.join(REPORTS_DIR, new_session_id)
            os.makedirs(session_dir, exist_ok=True)
            close_all_video_resources()

            import ares_app.vision.generator as vis_gen
            target_size = (640, 480)
            vis_gen.active_video_writer_normal = create_video_writer(os.path.join(session_dir, "cam_normal.mp4"), fps, target_size[0], target_size[1])
            vis_gen.active_video_writer_thermal = create_video_writer(os.path.join(session_dir, "cam_thermal.mp4"), fps, target_size[0], target_size[1])
            vis_gen.active_video_writer_noir = create_video_writer(os.path.join(session_dir, "cam_noir.mp4"), fps, target_size[0], target_size[1])
            vis_gen.active_video_writer_fused = create_video_writer(os.path.join(session_dir, "fused_mission.mp4"), fps, target_size[0], target_size[1])

        db_enqueue(
            'INSERT INTO sessions (session_id, start_time, mode, video_filename, duration_seconds) VALUES (?, ?, ?, ?, ?)',
            (new_session_id, datetime.now(timezone.utc).isoformat(), 'Autonomous', filename, round(duration, 1))
        )
        log_security_event(username, f"LAUNCH_SIMULATION:{filename}", "SUCCESS", f"Session: {new_session_id}")

    except Exception as e:
        with _sim_lock:
            _sim_config["launch_pending"] = False
            _sim_config["is_simulating"] = False
            _sim_config["mission_aborted"] = True
        reset_frame_cache()
        close_all_video_resources()
        print(f"[Background Launch Error] {e}")


@simulation_bp.route('/api/studio/launch', methods=['POST'])
@login_required
@permission_required('run_simulations')
def launch_simulation():
    global _launch_thread
    if 'video' not in request.files:
        return jsonify({"error": "Missing video file payload"}), 400

    file = request.files['video']
    timeline_str = request.form.get('timeline', '[]')

    if file.filename == '' or not file.filename.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
        return jsonify({"error": "Invalid video file"}), 400

    try:
        filename = secure_filename(file.filename)
        saved_path = os.path.join(UPLOAD_FOLDER, filename)

        with _sim_lock:
            _sim_config["is_simulating"] = False
            _sim_config["launch_pending"] = True
            _sim_config["mission_aborted"] = False
            should_finalize = bool(_sim_config.get("session_logging_active") and _sim_config.get("active_session_id"))

        if should_finalize:
            finalize_active_session_manually()

        reset_frame_cache()
        close_all_video_resources()

        file.save(saved_path)

        with _sim_lock:
            _global_telemetry_cache["current_live_telemetry"] = startup_baseline.copy()
            _global_telemetry_cache["trajectory"] = []
            _sim_config["current_live_telemetry"] = startup_baseline.copy()

        timeline_list = json.loads(timeline_str)
        formatted_timeline = []
        for item in timeline_list:
            formatted_timeline.append({
                "second": float(item.get("second", 0.0)),
                "gas_ppm": float(item.get("gas_ppm")) if item.get("gas_ppm") else None,
                "gas_mq9": float(item.get("gas_mq9")) if item.get("gas_mq9") is not None else None,
                "gas_mq135": float(item.get("gas_mq135")) if item.get("gas_mq135") is not None else None,
                "lidar_distance": float(item.get("lidar_distance")) if item.get("lidar_distance") is not None else None,
                "flame_alert": bool(item.get("flame_alert", False)),
                "temperature": float(item.get("temperature")) if item.get("temperature") else None,
                "camera_recommendation": item.get("camera_recommendation")
            })
        formatted_timeline = sorted(formatted_timeline, key=lambda x: x["second"])

        _launch_thread = threading.Thread(
            target=simulation_pipeline_loop,
            args=(saved_path, filename, formatted_timeline, current_user.username),
            daemon=True
        )
        _launch_thread.start()

        return jsonify({"status": "launched", "redirect": "/dashboard"})
    except Exception as e:
        return jsonify({"error": f"Failed: {str(e)}"}), 500


@simulation_bp.route('/api/set_vision_mode', methods=['POST'])
def set_vision_mode():
    if not request.is_json:
        return jsonify({"error": "JSON payload required"}), 400

    mode = request.get_json().get("mode", "RGB").upper()
    if mode not in ["RGB", "THERMAL", "INFRARED", "FUSION"]:
        return jsonify({"error": "Invalid vision mode"}), 400

    with _sim_lock:
        _sim_config["current_vision_mode"] = mode
        _sim_config["current_live_telemetry"]["status"]["current_vision_mode"] = mode

    return jsonify({"status": "vision_updated", "current_vision_mode": mode})


@simulation_bp.route('/api/simulation/stop', methods=['POST'])
@login_required
@permission_required('run_simulations')
def stop_simulation():
    with _sim_lock:
        _sim_config["is_simulating"] = False
        _sim_config["launch_pending"] = False
        _sim_config["mission_aborted"] = True
        should_finalize = bool(_sim_config.get("session_logging_active") and _sim_config.get("active_session_id"))

    if should_finalize:
        finalize_active_session_manually()
    else:
        close_all_video_resources()

    reset_frame_cache()
    log_security_event(current_user.username, "STOP_SIMULATION", "SUCCESS", "Simulation stopped.")
    return jsonify({"status": "stopped"})


@simulation_bp.route('/video_feed')
def video_feed():
    is_local = request.remote_addr in ['127.0.0.1', '::1']
    if not is_local:
        if not (current_user and current_user.is_authenticated):
            return abort(401)
        if not current_user.has_permission('view_live_telemetry'):
            return abort(403)
    username = current_user.username if (current_user and current_user.is_authenticated) else "admin"
    return Response(generate_video_frames(_sim_config, _sim_lock, _global_telemetry_cache, username=username, on_session_eos_fn=finalize_active_session_manually),
                    mimetype='multipart/x-mixed-replace; boundary=frame')
