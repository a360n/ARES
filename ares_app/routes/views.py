"""
ARES View Routes (HTML Page Rendering)
"""

from flask import Blueprint, render_template, abort
from flask_login import login_required, current_user
from ares_app.security.auth import permission_required
from ares_app.security.audit import log_security_event

views_bp = Blueprint('views_bp', __name__)


@views_bp.route('/')
@login_required
@permission_required('view_live_telemetry')
def studio():
    return render_template('studio.html')


@views_bp.route('/dashboard')
@login_required
@permission_required('view_live_telemetry')
def dashboard():
    return render_template('dashboard.html')


@views_bp.route('/hardware-control')
@login_required
@permission_required('manual_robot_control')
def hardware_control():
    return render_template('hardware_control.html')


@views_bp.route('/planned-routes')
@login_required
def planned_routes():
    return render_template('planned_routes.html')


@views_bp.route('/ai-objectives')
@login_required
def ai_objectives():
    return render_template('ai_objectives.html')


@views_bp.route('/admin/settings', methods=['GET'])
@login_required
def admin_settings_page():
    if current_user.username != 'admin':
        log_security_event(current_user.username, "ACCESS_DENIED:GET /admin/settings", "FAILURE", "Non-admin attempted to access admin settings.")
        return abort(403)
    return render_template('admin_settings.html')
