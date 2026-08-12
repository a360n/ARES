"""
ARES Mission Sessions & Reports Routes Blueprint
"""

import os
import shutil
from flask import Blueprint, jsonify, send_from_directory, send_file, abort
from werkzeug.utils import secure_filename
from flask_login import login_required, current_user

from ares_app.config import REPORTS_DIR
from ares_app.database import db_read, db_enqueue
from ares_app.security.auth import permission_required
from ares_app.security.audit import log_security_event
from ares_app.reports.service import create_session_zip_bundle

reports_bp = Blueprint('reports_bp', __name__)
_sim_config = None
_sim_lock = None


def init_reports_bp(state_refs):
    global _sim_config, _sim_lock
    _sim_config = state_refs["sim_config"]
    _sim_lock = state_refs["sim_lock"]


@reports_bp.route('/api/sessions', methods=['GET'])
@login_required
@permission_required('view_live_telemetry')
def get_sessions():
    try:
        sessions = db_read('SELECT * FROM sessions ORDER BY start_time DESC')
        result = []
        for s in sessions:
            sid = s["session_id"]
            report_dir = os.path.join(REPORTS_DIR, sid)
            html_file = os.path.join(report_dir, f"{sid}_report.html")
            pdf_file = os.path.join(report_dir, f"{sid}_report.pdf")

            entry = dict(s)
            entry["html_report_url"] = f"/api/session/report/{sid}/{sid}_report.html" if os.path.exists(html_file) else None
            entry["pdf_report_url"] = f"/api/session/report/{sid}/{sid}_report.pdf" if os.path.exists(pdf_file) else None
            result.append(entry)

        return jsonify(result)
    except Exception as e:
        print(f"[API Sessions ERROR] {e}")
        return jsonify([])


@reports_bp.route('/api/session/report/<session_id>/<filename>', methods=['GET'])
@login_required
@permission_required('export_reports')
def view_report_file(session_id, filename):
    filename = secure_filename(filename)
    session_dir = os.path.join(REPORTS_DIR, session_id)
    if not os.path.exists(session_dir):
        return abort(404)
    file_path = os.path.join(session_dir, filename)
    if not os.path.exists(file_path):
        return abort(404)
    return send_from_directory(session_dir, filename)


@reports_bp.route('/api/session/download_pack/<session_id>', methods=['GET'])
@login_required
@permission_required('export_reports')
def download_pack(session_id):
    memory_file = create_session_zip_bundle(session_id)
    if memory_file is None:
        return jsonify({"error": f"Session directory not found for ID: {session_id}"}), 404

    return send_file(
        memory_file,
        mimetype='application/zip',
        as_attachment=True,
        download_name=f"ARES_Session_{session_id}_Bundle.zip"
    )


@reports_bp.route('/api/sessions/delete/<session_id>', methods=['DELETE'])
@login_required
@permission_required('delete_logs')
def delete_session(session_id):
    db_enqueue('DELETE FROM telemetry_logs WHERE session_id = ?', (session_id,))
    db_enqueue('DELETE FROM sessions WHERE session_id = ?', (session_id,))

    session_dir = os.path.join(REPORTS_DIR, session_id)
    if os.path.exists(session_dir):
        try:
            shutil.rmtree(session_dir)
            print(f"[Cleanup] Purged session folder: {session_dir}")
        except Exception as e:
            print(f"[Cleanup ERROR] Failed to purge {session_dir}: {e}")

    log_security_event(current_user.username, f"DELETE_SESSION:{session_id}", "SUCCESS", "Purged from disk.")
    return jsonify({"status": "deleted", "session_id": session_id})


@reports_bp.route('/api/sessions/clear_all', methods=['DELETE'])
@login_required
@permission_required('delete_logs')
def clear_all_sessions():
    db_enqueue('DELETE FROM telemetry_logs')
    db_enqueue('DELETE FROM sessions')

    for item in os.listdir(REPORTS_DIR):
        item_path = os.path.join(REPORTS_DIR, item)
        if os.path.isdir(item_path):
            try: shutil.rmtree(item_path)
            except Exception: pass
        elif os.path.isfile(item_path) and item != '.DS_Store':
            try: os.remove(item_path)
            except Exception: pass

    log_security_event(current_user.username, "WIPE_ALL_LOGS", "SUCCESS", "Database history and reports cleared.")
    return jsonify({"status": "cleared"})
