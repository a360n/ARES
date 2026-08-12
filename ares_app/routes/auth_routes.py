"""
ARES Authentication Routes Blueprint
"""

from flask import Blueprint, render_template, jsonify, request, redirect, url_for
from werkzeug.security import check_password_hash
from flask_login import login_user, logout_user, login_required, current_user
from ares_app.database import db_read
from ares_app.security.auth import load_user
from ares_app.security.audit import log_security_event

auth_bp = Blueprint('auth_bp', __name__)


@auth_bp.route('/login', methods=['GET'])
def login_page():
    return render_template('login.html')


@auth_bp.route('/api/login', methods=['POST'])
def api_login():
    username = request.form.get('username')
    password = request.form.get('password')

    if not username or not password:
        return jsonify({"error": "Missing username or password"}), 400

    try:
        rows = db_read("SELECT username, password_hash FROM users WHERE username = ?", (username,))
        if rows and check_password_hash(rows[0]['password_hash'], password):
            user = load_user(rows[0]['username'])
            if user:
                login_user(user)
                log_security_event(username, "USER_LOGIN", "SUCCESS", f"Role: {user.role_name}")
                return jsonify({"status": "authenticated", "redirect": "/"})

        log_security_event(username if username else "UNKNOWN", "USER_LOGIN", "FAILURE", "Invalid credentials")
        return jsonify({"error": "Invalid username or password"}), 401
    except Exception as e:
        print(f"[Login Auth ERROR] {e}")
        return jsonify({"error": "An internal server error occurred"}), 500


@auth_bp.route('/logout')
@login_required
def logout():
    username = current_user.username
    logout_user()
    log_security_event(username, "USER_LOGOUT", "SUCCESS", "User session terminated.")
    response = redirect(url_for('auth_bp.login_page'))
    response.delete_cookie('session')
    return response
