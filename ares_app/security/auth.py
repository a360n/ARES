"""
ARES Authentication, RBAC & Security Middleware
"""

from functools import wraps
from flask import request, abort
from flask_login import LoginManager, current_user
from ares_app.database import db_read
from ares_app.security.models import User
from ares_app.security.audit import log_security_event
from ares_app.config import SECURITY_HEADERS

login_manager = LoginManager()


def init_security(app):
    """Configures Flask-Login, Limiter key, and Security Headers."""
    login_manager.init_app(app)
    login_manager.login_view = 'auth_bp.login_page'

    @app.after_request
    def add_security_headers(response):
        for header, value in SECURITY_HEADERS.items():
            response.headers[header] = value
        return response


@login_manager.user_loader
def load_user(username):
    try:
        rows = db_read("""
            SELECT u.username, u.role_id, r.name as role_name,
                   r.delete_logs, r.export_reports, r.run_simulations,
                   r.view_live_telemetry, r.power_toggle_robot,
                   r.toggle_navigation_mode, r.manual_robot_control
            FROM users u
            JOIN roles r ON u.role_id = r.id
            WHERE u.username = ?
        """, (username,))
        if rows:
            row = rows[0]
            permissions = {
                'delete_logs': bool(row['delete_logs']),
                'export_reports': bool(row['export_reports']),
                'run_simulations': bool(row['run_simulations']),
                'view_live_telemetry': bool(row['view_live_telemetry']),
                'power_toggle_robot': bool(row['power_toggle_robot']),
                'toggle_navigation_mode': bool(row['toggle_navigation_mode']),
                'manual_robot_control': bool(row['manual_robot_control'])
            }
            return User(row['username'], row['role_id'], row['role_name'], permissions)
    except Exception as e:
        print(f"[Login Manager ERROR] Failed to load user: {e}")
    return None


def permission_required(permission_name):
    """Enforces fine-grained permission-based authorization. Blocked requests are forensically logged."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return abort(401)
            if not current_user.has_permission(permission_name):
                log_security_event(
                    username=current_user.username,
                    action=f"ACCESS_DENIED:{request.method} {request.path}",
                    status="FAILURE",
                    details=f"Required permission: {permission_name} | Actual role: {current_user.role_name}"
                )
                return abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator
