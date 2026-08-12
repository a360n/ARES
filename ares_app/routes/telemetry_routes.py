"""
ARES Telemetry Routes Blueprint
"""

from flask import Blueprint, jsonify
from ares_app.telemetry.sse_stream import generate_telemetry_sse

telemetry_bp = Blueprint('telemetry_bp', __name__)
_sim_config = None
_sim_lock = None
_global_telemetry_cache = None


def init_telemetry_bp(state_refs):
    global _sim_config, _sim_lock, _global_telemetry_cache
    _sim_config = state_refs["sim_config"]
    _sim_lock = state_refs["sim_lock"]
    _global_telemetry_cache = state_refs["global_telemetry_cache"]


@telemetry_bp.route('/api/telemetry', methods=['GET'])
def get_telemetry():
    with _sim_lock:
        return jsonify(_sim_config["current_live_telemetry"])


@telemetry_bp.route('/api/telemetry/stream')
def telemetry_stream():
    return generate_telemetry_sse(_sim_config, _sim_lock, _global_telemetry_cache)
