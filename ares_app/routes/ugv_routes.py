"""
ARES UGV Mode, Route & AI Objective Routes Blueprint
"""

from flask import Blueprint, jsonify, request
from flask_login import login_required
from ares_app.ugv.navigation import set_ugv_navigation_mode
from ares_app.ugv.route_planner import save_route, fetch_all_routes, delete_route, launch_route, cancel_route
from ares_app.ugv.ai_search import launch_ai_search_objective, cancel_ai_search

ugv_bp = Blueprint('ugv_bp', __name__)
_sim_config = None
_sim_lock = None


def init_ugv_bp(state_refs):
    global _sim_config, _sim_lock
    _sim_config = state_refs["sim_config"]
    _sim_lock = state_refs["sim_lock"]


@ugv_bp.route('/api/ugv/routes/cancel', methods=['POST'])
@login_required
def cancel_ugv_route():
    try:
        cancel_route(_sim_config, _sim_lock)
        return jsonify({"status": "success", "message": "Route cancelled and UGV stopped successfully"})
    except Exception as e:
        return jsonify({"error": f"Failed to cancel route: {e}"}), 500


@ugv_bp.route('/api/ugv/mode', methods=['POST'])
@login_required
def set_ugv_mode():
    data = request.get_json() or {}
    mode = data.get("mode", "USER_CONTROL")
    try:
        updated_mode = set_ugv_navigation_mode(_sim_config, _sim_lock, mode)
        return jsonify({"status": "success", "ugv_mode": updated_mode})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@ugv_bp.route('/api/ugv/routes', methods=['POST'])
@login_required
def save_ugv_route():
    data = request.get_json() or {}
    try:
        save_route(data.get("name"), data.get("steps"))
        return jsonify({"status": "success", "message": "Route saved successfully"})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Failed to save route: {e}"}), 500


@ugv_bp.route('/api/ugv/routes', methods=['GET'])
@login_required
def get_ugv_routes():
    try:
        routes = fetch_all_routes()
        return jsonify(routes)
    except Exception as e:
        return jsonify({"error": f"Failed to fetch routes: {e}"}), 500


@ugv_bp.route('/api/ugv/routes/<int:route_id>', methods=['DELETE'])
@login_required
def delete_ugv_route(route_id):
    try:
        delete_route(route_id)
        return jsonify({"status": "success", "message": "Route deleted successfully"})
    except Exception as e:
        return jsonify({"error": f"Failed to delete route: {e}"}), 500


@ugv_bp.route('/api/ugv/routes/launch', methods=['POST'])
@login_required
def launch_ugv_route():
    data = request.get_json() or {}
    route_id = data.get("route_id")
    if not route_id:
        return jsonify({"error": "Route ID is required"}), 400
    try:
        route_name = launch_route(_sim_config, _sim_lock, route_id)
        return jsonify({"status": "success", "message": f"Route '{route_name}' launched"})
    except KeyError as e:
        return jsonify({"error": str(e)}), 404


@ugv_bp.route('/api/ugv/ai/launch', methods=['POST'])
@login_required
def launch_ai_objective():
    data = request.get_json() or {}
    try:
        obj_name = launch_ai_search_objective(
            _sim_config, _sim_lock,
            data.get("objective"),
            data.get("target_x"),
            data.get("target_y")
        )
        return jsonify({"status": "success", "message": f"AI Objective '{obj_name}' launched"})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@ugv_bp.route('/api/ugv/ai/cancel', methods=['POST'])
@login_required
def cancel_ai_objective():
    try:
        cancel_ai_search(_sim_config, _sim_lock)
        return jsonify({"status": "success", "message": "AI Search cancelled and UGV stopped successfully"})
    except Exception as e:
        return jsonify({"error": f"Failed to cancel AI search: {e}"}), 500
