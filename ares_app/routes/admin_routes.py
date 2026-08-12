"""
ARES Admin IAM Management Routes Blueprint
"""

from flask import Blueprint, jsonify, request, abort
from werkzeug.security import generate_password_hash
from flask_login import login_required, current_user
from ares_app.database import db_read, db_enqueue
from ares_app.security.audit import log_security_event

admin_bp = Blueprint('admin_bp', __name__)


@admin_bp.route('/api/admin/roles', methods=['GET'])
@login_required
def admin_get_roles():
    if current_user.username != 'admin':
        log_security_event(current_user.username, "ACCESS_DENIED:GET /api/admin/roles", "FAILURE", "Non-admin attempted to read roles.")
        return abort(403)
    try:
        roles = db_read("SELECT * FROM roles ORDER BY id ASC")
        return jsonify(roles)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route('/api/admin/users', methods=['GET'])
@login_required
def admin_get_users():
    if current_user.username != 'admin':
        log_security_event(current_user.username, "ACCESS_DENIED:GET /api/admin/users", "FAILURE", "Non-admin attempted to read users.")
        return abort(403)
    try:
        users = db_read("""
            SELECT u.username, u.role_id, r.name as role_name 
            FROM users u
            JOIN roles r ON u.role_id = r.id
            ORDER BY u.username ASC
        """)
        return jsonify(users)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route('/api/admin/roles/create', methods=['POST'])
@login_required
def admin_create_role():
    if current_user.username != 'admin':
        log_security_event(current_user.username, "ACCESS_DENIED:POST /api/admin/roles/create", "FAILURE", "Non-admin attempted to create role.")
        return abort(403)

    if not request.is_json:
        return jsonify({"error": "JSON payload required"}), 400

    data = request.get_json()
    name = data.get("name", "").strip().lower()
    if not name:
        return jsonify({"error": "Role name is required"}), 400

    delete_logs = 1 if bool(data.get("delete_logs")) else 0
    export_reports = 1 if bool(data.get("export_reports")) else 0
    run_simulations = 1 if bool(data.get("run_simulations")) else 0
    view_live_telemetry = 1 if bool(data.get("view_live_telemetry")) else 0
    power_toggle_robot = 1 if bool(data.get("power_toggle_robot")) else 0
    toggle_navigation_mode = 1 if bool(data.get("toggle_navigation_mode")) else 0
    manual_robot_control = 1 if bool(data.get("manual_robot_control")) else 0

    existing = db_read("SELECT id FROM roles WHERE name = ?", (name,))
    if existing:
        return jsonify({"error": f"Role '{name}' already exists"}), 400

    db_enqueue("""
        INSERT INTO roles (name, delete_logs, export_reports, run_simulations, view_live_telemetry, power_toggle_robot, toggle_navigation_mode, manual_robot_control)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (name, delete_logs, export_reports, run_simulations, view_live_telemetry, power_toggle_robot, toggle_navigation_mode, manual_robot_control))

    log_security_event(current_user.username, f"CREATE_ROLE:{name}", "SUCCESS", f"Permissions: del={delete_logs}, exp={export_reports}, sim={run_simulations}")
    return jsonify({"status": "role_created", "role_name": name})


@admin_bp.route('/api/admin/users/create', methods=['POST'])
@login_required
def admin_create_user():
    if current_user.username != 'admin':
        log_security_event(current_user.username, "ACCESS_DENIED:POST /api/admin/users/create", "FAILURE", "Non-admin attempted to create user.")
        return abort(403)

    if not request.is_json:
        return jsonify({"error": "JSON payload required"}), 400

    data = request.get_json()
    username = data.get("username", "").strip()
    password = data.get("password", "")
    role_id = data.get("role_id")

    if not username or not password or role_id is None:
        return jsonify({"error": "Username, password, and role_id required"}), 400

    try: role_id = int(role_id)
    except ValueError: return jsonify({"error": "role_id must be integer"}), 400

    if role_id == 1:
        log_security_event(current_user.username, "VIOLATION:CREATE_USER_ROOT_ADMIN", "FAILURE", f"User: {username}")
        return jsonify({"error": "Assigning users to root admin role (id=1) is forbidden"}), 403

    role_exists = db_read("SELECT id, name FROM roles WHERE id = ?", (role_id,))
    if not role_exists:
        return jsonify({"error": f"Role ID {role_id} does not exist"}), 400

    existing = db_read("SELECT username FROM users WHERE username = ?", (username,))
    if existing:
        return jsonify({"error": f"Username '{username}' already exists"}), 400

    password_hash = generate_password_hash(password, method='pbkdf2:sha256')
    db_enqueue("INSERT INTO users (username, password_hash, role_id) VALUES (?, ?, ?)", (username, password_hash, role_id))

    role_name = role_exists[0]["name"]
    log_security_event(current_user.username, f"CREATE_USER:{username}", "SUCCESS", f"Role: {role_name}")
    return jsonify({"status": "user_created", "username": username, "role_name": role_name})


@admin_bp.route('/api/admin/users/modify_rank', methods=['PUT'])
@login_required
def admin_modify_rank():
    if current_user.username != 'admin':
        log_security_event(current_user.username, "ACCESS_DENIED:PUT /api/admin/users/modify_rank", "FAILURE", "Non-admin attempted modify rank.")
        return abort(403)

    if not request.is_json:
        return jsonify({"error": "JSON payload required"}), 400

    data = request.get_json()
    username = data.get("username", "").strip()
    role_id = data.get("role_id")

    if not username or role_id is None:
        return jsonify({"error": "Username and role_id required"}), 400

    try: role_id = int(role_id)
    except ValueError: return jsonify({"error": "role_id must be integer"}), 400

    if role_id == 1 and username != 'admin':
        return jsonify({"error": "Elevating users to root admin role (id=1) is forbidden"}), 403

    if username == 'admin':
        return jsonify({"error": "Root user 'admin' role cannot be modified"}), 400

    role_exists = db_read("SELECT id, name FROM roles WHERE id = ?", (role_id,))
    if not role_exists:
        return jsonify({"error": f"Role ID {role_id} does not exist"}), 400

    user_exists = db_read("SELECT username FROM users WHERE username = ?", (username,))
    if not user_exists:
        return jsonify({"error": f"User '{username}' not found"}), 404

    db_enqueue("UPDATE users SET role_id = ? WHERE username = ?", (role_id, username))
    role_name = role_exists[0]["name"]
    log_security_event(current_user.username, f"MODIFY_USER_RANK:{username}", "SUCCESS", f"New role: {role_name}")
    return jsonify({"status": "rank_modified", "username": username, "role_name": role_name})
