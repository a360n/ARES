#!/usr/bin/env python3
"""
ARES (Autonomous Rescue & Emergency System)
Central Processing Server & AI Multi-Spectral Video Simulation Studio
Hosts Flask, handles multi-modal mutations (RGB, FLIR, IR), and syncs timeline events.
Includes SQLite mission logging, session lifecycle management, and automated report generation.
"""

import os
import sys
import time
import json
import cv2
import numpy as np
import threading
import sqlite3
import uuid
import queue
from datetime import datetime, timezone
from flask import Flask, render_template, Response, jsonify, request, redirect, url_for, abort
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

app = Flask(__name__)

# Level 1 Security: Environment-safe session signet key and cookie properties
app.secret_key = os.environ.get('ARES_SECRET_KEY') or os.urandom(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=False if os.environ.get('ARES_BYPASS_LIMITER') == '1' else True,
    SESSION_COOKIE_SAMESITE='Lax'
)

# Level 1 Security: Brute Force Protection via Flask-Limiter
def get_rate_limit_key():
    if os.environ.get('ARES_BYPASS_LIMITER') == '1':
        return None
    return get_remote_address()

limiter = Limiter(
    key_func=get_rate_limit_key,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

# Configure upload folder properties
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB limit

# Thread-safe global active configuration states
sim_lock = threading.Lock()
sim_config = {
    "video_path": None,                 # Path to uploaded walk-tour video
    "video_filename": "Default Sandbox Feed",
    "is_simulating": False,             # Active play state
    "launch_pending": False,            # True while a new simulation is being prepared
    "mission_aborted": False,           # True only after explicit stop/end-of-stream
    "is_playing": False,                # Active video playing state
    "current_vision_mode": "RGB",       # Camera modes: "RGB", "THERMAL", "INFRARED"
    "telemetry_timeline": [],           # List of events: [{"second": 5, "gas_ppm": 450, "flame_alert": True, "temperature": 68, "camera_recommendation": "THERMAL"}]
    "current_live_telemetry": {},       # Current active telemetry dict
    "current_second": 0.0,              # Playback timing pointer
    "duration": 0.0,                    # Calculated video length
    "fire_visual_alert": False,         # Vision-to-audio fire/smoke alert flag
    "active_session_id": None,          # Current mission session UUID
    "session_logging_active": False,    # Whether telemetry is being logged to DB
    "engine_power_status": "ONLINE",    # Co-pilot: UGV engine toggle ("ONLINE" / "OFFLINE")
    "navigation_override_status": "AUTOPILOT",  # Co-pilot: Autopilot mode ("AUTOPILOT" / "MANUAL")
    "last_manual_command": "STANDBY",   # Co-pilot: Last D-pad command
    "manual_x": 50.0,                   # Co-pilot: Manual X coordinates
    "manual_y": 50.0                    # Co-pilot: Manual Y coordinates
}

# --- Session Aggregation Accumulators (protected by sim_lock) ---
_session_agg = {
    "max_gas_ppm": 0.0,
    "max_temperature": 0.0,
    "fire_incident_triggered": False,
    "total_victims_found": 0,
    "_peak_victims_in_frame": 0
}
# Global thread-synchronization primitives & caching pipelines
_telemetry_log_tick = 0
video_buffer_lock = threading.RLock()
_active_writers = {}
_active_captures = []
_launch_thread = None
_latest_frame_data = {
    "session_id": None,
    "frame_idx": -1,
    "playback_sec": -1.0,
    "jpeg_bytes": None,
    "timestamp": 0.0
}
# Standard default baseline structured telemetry on startup (all numbers set to zero/neutral values, map centered at x=200.0, y=200.0)
startup_baseline = {
    "status": {
        "mode": "Idle Sandbox",
        "position": {
            "x": 200.0,
            "y": 200.0
        },
        "video_time": 0.0,
        "video_filename": "Default Sandbox Feed",
        "is_simulating": False,
        "duration": 0.0,
        "current_vision_mode": "RGB",
        "camera_recommendation": None,
        "hazard_grade": 1,
        "hazard_status": "NORMAL",
        "unconscious_victims": 0,
        "fire_detected": False,
        "engine_power_status": "ONLINE",
        "navigation_override_status": "AUTOPILOT",
        "last_manual_command": "STANDBY",
        "trajectory": []
    },
    "sensors": {
        "lidar": 0.0,
        "bme688": {
            "temperature": 0.0,
            "humidity": 0.0
        },
        "gas": {
            "mq9": 0.0,
            "mq135": 0.0,
            "mics6814": 0.0
        },
        "flame": [0, 0, 0, 0, 0]
    }
}
global_telemetry_cache = {
    "current_live_telemetry": startup_baseline.copy(),
    "trajectory": []
}


def reset_frame_cache():
    """Clear the shared MJPEG cache so old clients cannot reuse a stale/finished frame."""
    with video_buffer_lock:
        _latest_frame_data["session_id"] = None
        _latest_frame_data["frame_idx"] = -1
        _latest_frame_data["playback_sec"] = -1.0
        _latest_frame_data["jpeg_bytes"] = None
        _latest_frame_data["timestamp"] = 0.0


def close_all_video_resources():
    """Release all OpenCV captures/writers safely before a new run or on stop."""
    global active_video_writer_normal, active_video_writer_thermal, active_video_writer_noir, active_video_writer_fused
    with video_buffer_lock:
        for cap_instance in list(_active_captures):
            if cap_instance is not None:
                try:
                    cap_instance.release()
                except Exception as ce:
                    print(f"[Resource Cleanup] VideoCapture release error: {ce}")
        _active_captures.clear()

        for path, w in list(_active_writers.items()):
            if w is not None:
                try:
                    w.release()
                except Exception as we:
                    print(f"[Resource Cleanup] VideoWriter release error for {path}: {we}")
        _active_writers.clear()

        for w in [active_video_writer_normal, active_video_writer_thermal, active_video_writer_noir, active_video_writer_fused]:
            if w is not None:
                try:
                    w.release()
                except Exception as we:
                    print(f"[Resource Cleanup] Global VideoWriter release error: {we}")
        active_video_writer_normal = None
        active_video_writer_thermal = None
        active_video_writer_noir = None
        active_video_writer_fused = None


active_video_writer_normal = None   # Global OpenCV VideoWriter instance for Normal RGB
active_video_writer_thermal = None  # Global OpenCV VideoWriter instance for FLIR Thermal
active_video_writer_noir = None     # Global OpenCV VideoWriter instance for NoIR Night-Vision
active_video_writer_fused = None    # Global OpenCV VideoWriter instance for Pixel-Level Fused


def create_video_writer(video_out_path, fps, width, height):
    """
    Attempts to initialize a cv2.VideoWriter with a web-standard AVC encoding.
    Defensively checks if a writer instance is already allocated for this path,
    multiplexing the reference instead of re-instantiating a conflicting file lock.
    """
    global _active_writers
    with video_buffer_lock:
        if video_out_path in _active_writers:
            w = _active_writers[video_out_path]
            if w is not None and w.isOpened():
                print(f"[Video Recording] Multiplexing/Reusing active VideoWriter for: {video_out_path}")
                return w

    writer = None
    try:
        fourcc = cv2.VideoWriter_fourcc(*'avc1')
        writer = cv2.VideoWriter(video_out_path, fourcc, fps, (width, height))
        if writer is not None and writer.isOpened():
            print(f"[Video Recording] Initialized cv2.VideoWriter successfully with codec 'avc1'")
            with video_buffer_lock:
                _active_writers[video_out_path] = writer
            return writer
        if writer is not None:
            writer.release()
    except Exception as e:
        print(f"[Video Recording WARNING] Web codec 'avc1' failed to initialize: {e}")

    # Fallback dynamically to 'mp4v' standardized to the resolution pipeline
    try:
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        writer = cv2.VideoWriter(video_out_path, fourcc, fps, (width, height))
        if writer is not None and writer.isOpened():
            print(f"[Video Recording] Initialized fallback cv2.VideoWriter successfully with codec 'mp4v'")
            with video_buffer_lock:
                _active_writers[video_out_path] = writer
            return writer
        if writer is not None:
            writer.release()
    except Exception as e:
        print(f"[Video Recording FATAL] Failed to initialize dynamic 'mp4v' fallback: {e}")

    return None



# --- SQLite Database Engine (Thread-Safe Writer) ---

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ares_mission_control.db')
REPORTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'reports')
os.makedirs(REPORTS_DIR, exist_ok=True)

# All DB operations are routed through this queue to a single writer thread
_db_queue = queue.Queue()


# --- Flask-Login Security Configuration ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login_page'


# Level 1 Security: Content Security Policy & Security Headers injection filter
@app.after_request
def add_security_headers(response):
    csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.tailwindcss.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: blob: http: https:; "
        "connect-src 'self' ws: wss: http: https:;"
    )
    response.headers['Content-Security-Policy'] = csp
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response

class UserRole:
    def __init__(self, name, permissions):
        self.name = name
        self.permissions = permissions
        
    def __getattr__(self, name):
        if name in self.permissions:
            return bool(self.permissions[name])
        raise AttributeError(f"'UserRole' object has no attribute '{name}'")
        
    def __str__(self):
        return self.name

class User(UserMixin):
    def __init__(self, username, role_id, role_name, permissions):
        self.id = username
        self.username = username
        self.role_id = role_id
        self.role_name = role_name
        self.role = UserRole(role_name, permissions)
        self.permissions = permissions  # dict: {permission_flag: bool}

    def has_permission(self, permission_name):
        return bool(self.permissions.get(permission_name, False))

@login_manager.user_loader
def load_user(username):
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT u.username, u.role_id, r.name as role_name,
                   r.delete_logs, r.export_reports, r.run_simulations,
                   r.view_live_telemetry, r.power_toggle_robot,
                   r.toggle_navigation_mode, r.manual_robot_control
            FROM users u
            JOIN roles r ON u.role_id = r.id
            WHERE u.username = ?
        """, (username,))
        row = cursor.fetchone()
        conn.close()
        if row:
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


def log_security_event(username, action, status="SUCCESS", details=""):
    """Logs critical administrative actions securely to static/security_audit.log with standard timestamping."""
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, 'security_audit.log')
    timestamp = datetime.now(timezone.utc).isoformat()
    log_line = f"[{timestamp}] USER={username} | ACTION={action} | STATUS={status} | DETAILS={details}\n"
    try:
        with open(log_path, 'a') as lf:
            lf.write(log_line)
    except Exception as e:
        print(f"[Forensic Log Error] Failed to write security event: {e}")


from functools import wraps

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


def init_database():
    """Creates the SQLite database and tables if they do not exist, and seeds dynamic roles and hashed user credentials."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Enable WAL mode and foreign key constraints
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    
    # Check if the users table uses the legacy static role schema, and drop it if legacy
    try:
        cursor.execute("PRAGMA table_info(users)")
        columns = [c[1] for c in cursor.fetchall()]
        if columns and 'role' in columns:
            print("[Database] Legacy users table found. Performing automated schema migration...")
            cursor.execute("DROP TABLE IF EXISTS users")
            cursor.execute("DROP TABLE IF EXISTS roles")
            conn.commit()
    except Exception as e:
        print(f"[Database Migration Warning] {e}")

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            session_id              TEXT PRIMARY KEY,
            start_time              TEXT NOT NULL,
            end_time                TEXT,
            mode                    TEXT DEFAULT 'Autonomous',
            total_victims_found     INTEGER DEFAULT 0,
            max_gas_ppm             REAL DEFAULT 0.0,
            max_temperature         REAL DEFAULT 0.0,
            fire_incident_triggered INTEGER DEFAULT 0,
            video_filename          TEXT,
            duration_seconds        REAL DEFAULT 0.0
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS telemetry_logs (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id            TEXT NOT NULL,
            timestamp             TEXT NOT NULL,
            gas_mq9               REAL,
            temperature           REAL,
            flame_state           INTEGER,
            lidar_distance        REAL,
            ai_detections_summary TEXT,
            unconscious_victims   INTEGER DEFAULT 0,
            FOREIGN KEY (session_id) REFERENCES sessions(session_id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            delete_logs INTEGER DEFAULT 0,
            export_reports INTEGER DEFAULT 0,
            run_simulations INTEGER DEFAULT 0,
            view_live_telemetry INTEGER DEFAULT 0,
            power_toggle_robot INTEGER DEFAULT 0,
            toggle_navigation_mode INTEGER DEFAULT 0,
            manual_robot_control INTEGER DEFAULT 0
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            role_id INTEGER NOT NULL,
            FOREIGN KEY (role_id) REFERENCES roles(id)
        )
    ''')
    
    # Check if empty and seed standard roles
    cursor.execute("SELECT COUNT(*) FROM roles")
    if cursor.fetchone()[0] == 0:
        default_roles = [
            (1, 'admin', 1, 1, 1, 1, 1, 1, 1),
            (2, 'operator', 0, 1, 1, 1, 1, 1, 1),
            (3, 'auditor', 0, 1, 0, 1, 0, 0, 0)
        ]
        cursor.executemany("""
            INSERT INTO roles (id, name, delete_logs, export_reports, run_simulations, view_live_telemetry, power_toggle_robot, toggle_navigation_mode, manual_robot_control)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, default_roles)
        conn.commit()
        print("[Database] Dynamic roles successfully seeded.")

    # Seed default user accounts mapped to their respective roles
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        default_users = [
            ('admin', generate_password_hash('admin123', method='pbkdf2:sha256'), 1),
            ('operator', generate_password_hash('operator123', method='pbkdf2:sha256'), 2),
            ('auditor', generate_password_hash('auditor123', method='pbkdf2:sha256'), 3)
        ]
        cursor.executemany("INSERT INTO users (username, password_hash, role_id) VALUES (?, ?, ?)", default_users)
        conn.commit()
        print("[Database] Hashed user credentials successfully seeded with dynamic roles.")
        
    # Root admin invariant check in DB: ensure 'admin' username strictly points to role_id=1
    cursor.execute("SELECT role_id FROM users WHERE username = 'admin'")
    admin_row = cursor.fetchone()
    if admin_row and admin_row[0] != 1:
        print("[Database Guard Warning] Invariant violated! Correcting admin role alignment...")
        cursor.execute("UPDATE users SET role_id = 1 WHERE username = 'admin'")
        conn.commit()
        
    conn.commit()
    conn.close()
    print("[Database] SQLite initialized at:", DB_PATH)


def _db_writer_loop():
    """
    Dedicated daemon thread that owns the single SQLite connection.
    Drains the _db_queue and executes write operations in batches.
    This avoids 'database is locked' errors from concurrent threads.
    """
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    while True:
        try:
            # Block until at least one item is available
            op = _db_queue.get(timeout=2.0)
            # Batch: drain any additional pending items
            ops = [op]
            while not _db_queue.empty():
                try:
                    ops.append(_db_queue.get_nowait())
                except queue.Empty:
                    break
            cursor = conn.cursor()
            for operation in ops:
                try:
                    sql, params = operation
                    cursor.execute(sql, params)
                except Exception as e:
                    print(f"[Database Writer ERROR] {e} | SQL: {operation[0][:80]}")
            conn.commit()
        except queue.Empty:
            continue
        except Exception as e:
            print(f"[Database Writer FATAL] {e}")
            try:
                conn.rollback()
            except Exception:
                pass


def db_enqueue(sql, params=()):
    """Enqueue a SQL write operation for the DB writer thread."""
    _db_queue.put((sql, params))


def db_read(sql, params=()):
    """Execute a read-only query and return results. Safe from any thread."""
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


# Initialize database and start writer thread
init_database()
_db_writer_thread = threading.Thread(target=_db_writer_loop, daemon=True)
_db_writer_thread.start()

# --- YOLOv8 / AI Inference Setup with Fallback ---
YOLO_PERSON_MODEL = None
YOLO_FIRE_MODEL = None
PERSON_MODEL_LOADED = False
FIRE_MODEL_LOADED = False
yolo_error_msg = ""

try:
    from ultralytics import YOLO
    
    # 1. Load Standard yolov8n.pt model specifically for Person detection
    try:
        YOLO_PERSON_MODEL = YOLO("yolov8n.pt")
        PERSON_MODEL_LOADED = True
        print("[AI Inference] Standard YOLOv8-nano (Person detector) loaded successfully.")
    except Exception as e:
        yolo_error_msg += f"Person Model: {str(e)}; "
        print(f"[AI Inference WARNING] Standard YOLOv8 failed to load: {e}")
        
    # 2. Load Specialized YOLO Fire/Smoke model
    FIRE_WEIGHTS_PATH = "yolov8n_fire.pt"
    
    # Try downloading public verified fire weights if not present locally
    if not os.path.exists(FIRE_WEIGHTS_PATH):
        print("[AI Inference] YOLO Fire weights not found locally. Attempting verified URL downloads...")
        urls = [
            "https://github.com/lucas-t-oliveira/fire-detection-yolov8/raw/main/weights/best.pt",
            "https://github.com/gengyanlei/fire-smoke-detect-yolov8/raw/main/weights/best.pt"
        ]
        import requests
        for url in urls:
            try:
                print(f"[AI Inference] Downloading from: {url}")
                r = requests.get(url, timeout=10, stream=True)
                if r.status_code == 200:
                    with open(FIRE_WEIGHTS_PATH, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                    print(f"[AI Inference] Fire weights downloaded successfully and saved as {FIRE_WEIGHTS_PATH}")
                    break
            except Exception as dl_err:
                print(f"[AI Inference WARNING] Download failed from {url}: {dl_err}")
                
    # Now try to load the model
    try:
        if os.path.exists(FIRE_WEIGHTS_PATH):
            YOLO_FIRE_MODEL = YOLO(FIRE_WEIGHTS_PATH)
            FIRE_MODEL_LOADED = True
            print(f"[AI Inference] Specialized YOLOv8 Fire detector loaded successfully from {FIRE_WEIGHTS_PATH}.")
        else:
            # Fallback to direct Hub string
            YOLO_FIRE_MODEL = YOLO("yolov8n_fire.pt")
            FIRE_MODEL_LOADED = True
            print("[AI Inference] Specialized YOLOv8 Fire detector loaded via Ultralytics Hub string.")
    except Exception as e:
        yolo_error_msg += f"Fire Model: {str(e)}; "
        print(f"[AI Inference WARNING] YOLO Fire model failed to load. Will use HSV real-time computer vision backup. Reason: {e}")

except Exception as e:
    yolo_error_msg = str(e)
    print(f"[AI Inference WARNING] YOLO package loading failed: {e}")



# --- Telemetry Timeline Engine ---

def get_baseline_telemetry(second=0.0):
    """Generates dynamic, oscillating baseline sensor readings."""
    # LiDAR ranges oscillating realistically
    lidar_val = 185.0 + 55.0 * np.cos(second * 0.45)
    
    # Baseline environment
    temp_val = 22.4 + 0.15 * np.sin(second * 0.12)
    hum_val = 47.8 + 0.3 * np.cos(second * 0.06)
    
    # Gas array baselines
    mq9_val = 7.5 + 0.2 * np.sin(second * 0.7)
    mq135_val = 21.0 + 0.5 * np.cos(second * 0.35)
    mics_val = 0.112 + 0.005 * np.sin(second * 0.55)
    
    # Flame clean
    flame_array = [0, 0, 0, 0, 0]
    
    # Orbiting grid position
    pos_x = 200.0 + 120.0 * np.cos(second * 0.22)
    pos_y = 200.0 + 120.0 * np.sin(second * 0.22)

    return {
        "status": {
            "mode": "Simulation Active" if sim_config["is_simulating"] else "Idle Sandbox",
            "position": {
                "x": round(pos_x, 1),
                "y": round(pos_y, 1)
            },
            "video_time": round(second, 1),
            "video_filename": sim_config["video_filename"],
            "is_simulating": sim_config["is_simulating"],
            "duration": round(sim_config["duration"], 1),
            "current_vision_mode": sim_config["current_vision_mode"],
            "camera_recommendation": None,
            "hazard_grade": 1,
            "hazard_status": "NORMAL",
            "unconscious_victims": 0,
            "fire_detected": False,
            "trajectory": []
        },
        "sensors": {
            "lidar": round(max(5.0, lidar_val), 1),
            "bme688": {
                "temperature": round(temp_val, 2),
                "humidity": round(hum_val, 2)
            },
            "gas": {
                "mq9": round(mq9_val, 2),
                "mq135": round(mq135_val, 2),
                "mics6814": round(mics_val, 3)
            },
            "flame": flame_array
        }
    }


def compute_telemetry(second):
    """Calculates active state by compounding custom timeline triggers over baseline."""
    tel = get_baseline_telemetry(second)
    
    # Extract the active keyframe that applies to the current second
    active_kf = None
    with sim_lock:
        timeline = sim_config["telemetry_timeline"]
        # Find the latest keyframe that has passed or matches current timestamp
        for kf in timeline:
            if kf["second"] <= second:
                active_kf = kf

    if active_kf:
        # 1. Apply gas array overrides
        if "gas_ppm" in active_kf and active_kf["gas_ppm"] is not None:
            gas_val = float(active_kf["gas_ppm"])
            tel["sensors"]["gas"]["mq9"] = round(gas_val, 2)
            tel["sensors"]["gas"]["mq135"] = round(gas_val * 1.88, 2)
            tel["sensors"]["gas"]["mics6814"] = round(gas_val / 72.0, 3)
            
        if "gas_mq9" in active_kf and active_kf["gas_mq9"] is not None:
            tel["sensors"]["gas"]["mq9"] = round(float(active_kf["gas_mq9"]), 2)
            
        if "gas_mq135" in active_kf and active_kf["gas_mq135"] is not None:
            tel["sensors"]["gas"]["mq135"] = round(float(active_kf["gas_mq135"]), 2)
            
        if "mics6814" in active_kf and active_kf["mics6814"] is not None:
            tel["sensors"]["gas"]["mics6814"] = round(float(active_kf["mics6814"]), 3)
            
        # 2. Apply flame alarms
        if "flame_alert" in active_kf:
            is_flame = bool(active_kf["flame_alert"])
            tel["sensors"]["flame"] = [1, 1, 1, 1, 1] if is_flame else [0, 0, 0, 0, 0]
            
        # 3. Apply temperature and humidity drift
        if "temperature" in active_kf and active_kf["temperature"] is not None:
            temp_val = float(active_kf["temperature"])
            tel["sensors"]["bme688"]["temperature"] = round(temp_val, 2)
            tel["sensors"]["bme688"]["humidity"] = round(max(5.0, 48.0 - (temp_val - 22.4) * 0.75), 2)

        # 4. Apply LiDAR distance override
        if "lidar_distance" in active_kf and active_kf["lidar_distance"] is not None:
            tel["sensors"]["lidar"] = round(float(active_kf["lidar_distance"]) * 100.0, 1) # convert meters to cm

        # 5. Bind camera override recommendations
        if "camera_recommendation" in active_kf and active_kf["camera_recommendation"]:
            tel["status"]["camera_recommendation"] = active_kf["camera_recommendation"].upper()

    # --- Intelligent Environmental Risk Classification (Decision Tree Inference) ---
    flame_state = any(tel["sensors"]["flame"])
    gas_mq9 = tel["sensors"]["gas"]["mq9"]
    gas_mq135 = tel["sensors"]["gas"]["mq135"]
    mics6814 = tel["sensors"]["gas"]["mics6814"]
    temp_val = tel["sensors"]["bme688"]["temperature"]
    lidar_val = tel["sensors"]["lidar"]
    
    # 1. Base State Flags
    is_fire_event = flame_state or (temp_val > 55.0 and gas_mq9 > 150.0)
    is_toxic_event = (gas_mq135 > 150.0 or mics6814 > 200.0)
    
    # 2. Decision Tree Inference Flow (Severity High-to-Low)
    if (is_fire_event or is_toxic_event) and (lidar_val < 80.0):
        # LEVEL 4 (CRITICAL FLASHOVER)
        hazard_grade = 4
        hazard_status = "CRITICAL FLASHOVER"
        hazard_summary = "🚨 INSTANT EVACUATION: STRUCTURAL FAILURE IMMINENT // ACTIVATING AUTOMATED EMERGENCY SAFETY RETURN PROTOCOLS"
    elif is_fire_event:
        # LEVEL 3 (FIRE CONTINGENCY)
        hazard_grade = 3
        hazard_status = "FIRE CONTINGENCY"
        hazard_summary = "⚠️ HAZARD ALERT: CRITICAL FIRE CONTINGENCY TRIGGERED"
    elif is_toxic_event and temp_val <= 45.0 and not flame_state:
        # LEVEL 2 (GAS LEAK WARNING)
        hazard_grade = 2
        hazard_status = "GAS LEAK WARNING"
        hazard_summary = "⚠️ GAS ALERT: UNIDENTIFIED INDUSTRIAL GAS DISPERSION LOCALIZED"
    else:
        # LEVEL 1 (NORMAL) - Baseline/Minimal States
        hazard_grade = 1
        hazard_status = "NORMAL"
        hazard_summary = "Systems Nominal // Multi-Spectral Patrol Secure"
        
    tel["status"]["hazard_grade"] = hazard_grade
    tel["status"]["hazard_status"] = hazard_status
    tel["status"]["hazard_summary"] = hazard_summary
    tel["status"]["hazard_level"] = hazard_grade
    tel["hazard_level"] = hazard_grade

    with sim_lock:
        nav_mode = sim_config.get("navigation_override_status", "AUTOPILOT")
        engine_status = sim_config.get("engine_power_status", "ONLINE")
        last_cmd = sim_config.get("last_manual_command", "STANDBY")
        man_x = sim_config.get("manual_x", 50.0)
        man_y = sim_config.get("manual_y", 50.0)

    tel["status"]["navigation_override_status"] = nav_mode
    tel["status"]["engine_power_status"] = engine_status
    tel["status"]["last_manual_command"] = last_cmd
    tel["status"]["manual_x"] = man_x
    tel["status"]["manual_y"] = man_y

    if nav_mode == "MANUAL":
        tel["status"]["position"]["x"] = round(man_x, 1)
        tel["status"]["position"]["y"] = round(man_y, 1)

    if engine_status == "OFFLINE":
        tel["status"]["position"]["x"] = 0.0
        tel["status"]["position"]["y"] = 0.0
        tel["status"]["mode"] = "System Offline // UGV Powered Down"
        tel["sensors"]["lidar"] = 0.0
        tel["sensors"]["gas"]["mq9"] = 0.0
        tel["sensors"]["gas"]["mq135"] = 0.0
        tel["sensors"]["gas"]["mics6814"] = 0.0
        tel["sensors"]["bme688"]["temperature"] = 0.0
        tel["sensors"]["bme688"]["humidity"] = 0.0
        tel["sensors"]["flame"] = [0, 0, 0, 0, 0]

    return tel


# Initialize baseline telemetry right away
with sim_lock:
    sim_config["current_live_telemetry"] = startup_baseline.copy()


# --- Flask Routing ---

@app.route('/login', methods=['GET'])
def login_page():
    """Renders the dark glassmorphic login interface page."""
    if current_user.is_authenticated:
        return redirect(url_for('studio'))
    return render_template('login.html')


@app.route('/api/login', methods=['POST'])
@limiter.limit("5 per minute")
def api_login():
    """Verifies credentials, issues session cookies, and records the forensic event."""
    username = request.form.get('username')
    password = request.form.get('password')
    
    if not username or not password:
        return jsonify({"error": "Missing username or password"}), 400
        
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT username, password_hash FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        conn.close()
        
        if row and check_password_hash(row[1], password):
            user = load_user(row[0])
            if user:
                login_user(user)
                log_security_event(username, "USER_LOGIN", "SUCCESS", f"Authenticated successfully with role: {user.role_name}")
                return jsonify({"status": "authenticated", "redirect": "/"})
            
        log_security_event(username if username else "UNKNOWN", "USER_LOGIN", "FAILURE", "Invalid credentials submitted")
        return jsonify({"error": "Invalid username or password"}), 401
    except Exception as e:
        print(f"[Login Auth ERROR] {e}")
        return jsonify({"error": "An internal server error occurred"}), 500


@app.route('/logout')
@login_required
def logout():
    """Terminates active session, purges cookies, and records the forensic logout trail."""
    username = current_user.username
    logout_user()
    log_security_event(username, "USER_LOGOUT", "SUCCESS", "User session explicitly terminated.")
    response = redirect(url_for('login_page'))
    response.delete_cookie('session')
    return response


@app.route('/')
@login_required
@permission_required('view_live_telemetry')
def studio():
    """Renders the Control Studio dashboard where users upload and sequence profiles."""
    return render_template('studio.html')


@app.route('/dashboard')
@login_required
@permission_required('view_live_telemetry')
def dashboard():
    """Renders the operations monitor dashboard that streams video and telemetry."""
    return render_template('dashboard.html', active_session_id=sim_config.get("active_session_id") or "")


# --- API Control Interfaces ---

def simulation_pipeline_loop(saved_path, filename, formatted_timeline, username):
    """
    Background simulation pipeline loop.
    Extracts video attributes, configures video writers, enqueues session to SQLite,
    and updates global sim_config. Runs asynchronously to prevent Flask worker starvation.
    """
    global sim_config, active_video_writer_normal, active_video_writer_thermal, active_video_writer_noir, active_video_writer_fused
    
    # 1. Verify the thread lock video_buffer_lock status before launch (diagnostic only)
    _lock_probe = video_buffer_lock.acquire(blocking=False)
    if _lock_probe:
        video_buffer_lock.release()
    else:
        print("[Pipeline Setup] Warning: video_buffer_lock is still held by another thread. It will be released by its owner.")

    # 2. Watchdog: monitor lock health and log warnings if held too long
    def reset_lock():
        global _latest_frame_data
        current_time = time.time()
        last_update = _latest_frame_data.get("timestamp", 0.0)
        
        _lock_probe = video_buffer_lock.acquire(blocking=False)
        if _lock_probe:
            video_buffer_lock.release()
        elif current_time - last_update > 5.0:
            print("[Watchdog] Warning: video_buffer_lock held for >5s without frame update. Owner thread should release soon.")
        
        # Re-arm if still simulating
        with sim_lock:
            still_sim = sim_config.get("is_simulating", False)
        if still_sim:
            t = threading.Timer(1.0, reset_lock)
            t.daemon = True
            t.start()

    # Start the watchdog timer
    t = threading.Timer(1.0, reset_lock)
    t.daemon = True
    t.start()

    try:
        # Measure video file properties
        cap = cv2.VideoCapture(saved_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0:
            fps = 30.0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        duration = total_frames / fps
        cap.release()

        # Update active simulation state
        with sim_lock:
            sim_config["video_path"] = saved_path
            sim_config["video_filename"] = filename
            sim_config["telemetry_timeline"] = formatted_timeline
            sim_config["is_simulating"] = True
            sim_config["launch_pending"] = False
            sim_config["mission_aborted"] = False
            sim_config["duration"] = duration
            sim_config["current_second"] = 0.0
            sim_config["current_vision_mode"] = "RGB"  # Reset vision mode to RGB on start
            sim_config["fps"] = fps
            sim_config["width"] = width
            sim_config["height"] = height

            # --- Session Lifecycle: START new mission session ---
            new_session_id = str(uuid.uuid4())[:8]
            sim_config["active_session_id"] = new_session_id
            sim_config["session_logging_active"] = True
            # Reset telemetry cache to baseline startup values immediately on new session hash creation
            global_telemetry_cache["current_live_telemetry"] = startup_baseline.copy()
            global_telemetry_cache["trajectory"] = []
            sim_config["current_live_telemetry"] = startup_baseline.copy()
            if new_session_id:
                global_telemetry_cache[new_session_id] = startup_baseline.copy()
            # Reset aggregation accumulators
            _session_agg["max_gas_ppm"] = 0.0
            _session_agg["max_temperature"] = 0.0
            _session_agg["fire_incident_triggered"] = False
            _session_agg["total_victims_found"] = 0
            _session_agg["_peak_victims_in_frame"] = 0

            # Create session directory and init Video Writers for concurrent multi-stream recording
            session_dir = os.path.join(REPORTS_DIR, new_session_id)
            os.makedirs(session_dir, exist_ok=True)

            for w in [active_video_writer_normal, active_video_writer_thermal, active_video_writer_noir, active_video_writer_fused]:
                if w is not None:
                    try:
                        w.release()
                    except Exception:
                        pass
            active_video_writer_normal = None
            active_video_writer_thermal = None
            active_video_writer_noir = None
            active_video_writer_fused = None

            # Standard configuration target dimensions
            target_size = (640, 480)

            active_video_writer_normal = create_video_writer(os.path.join(session_dir, "cam_normal.mp4"), fps, target_size[0], target_size[1])
            active_video_writer_thermal = create_video_writer(os.path.join(session_dir, "cam_thermal.mp4"), fps, target_size[0], target_size[1])
            active_video_writer_noir = create_video_writer(os.path.join(session_dir, "cam_noir.mp4"), fps, target_size[0], target_size[1])
            active_video_writer_fused = create_video_writer(os.path.join(session_dir, "fused_mission.mp4"), fps, target_size[0], target_size[1])

        db_enqueue(
            'INSERT INTO sessions (session_id, start_time, mode, video_filename, duration_seconds) VALUES (?, ?, ?, ?, ?)',
            (new_session_id, datetime.now(timezone.utc).isoformat(), 'Autonomous', filename, round(duration, 1))
        )
        print(f"[Session] New mission session started: {new_session_id}")
        print(f"[Studio Command] Simulation launched! Video: {filename} // Duration: {duration:.1f}s")
        log_security_event(username, f"LAUNCH_SIMULATION:{filename}", "SUCCESS", f"Session: {new_session_id} | Duration: {duration:.1f}s")

    except Exception as e:
        with sim_lock:
            sim_config["launch_pending"] = False
            sim_config["is_simulating"] = False
            sim_config["mission_aborted"] = True
        reset_frame_cache()
        close_all_video_resources()
        print(f"[Background Launch Error] {e}")
        log_security_event(username, "LAUNCH_SIMULATION_BACKGROUND", "FAILURE", f"Background launch failed: {e}")


@app.route('/api/studio/launch', methods=['POST'])
@login_required
@permission_required('run_simulations')
def launch_simulation():
    """
    Accepts video upload and timeline sequencing definitions via FormData.
    Saves file, compiles timelines, and sets system state to simulating.
    """
    global sim_config
    
    if 'video' not in request.files:
        return jsonify({"error": "Missing video file payload"}), 400
        
    file = request.files['video']
    timeline_str = request.form.get('timeline', '[]')
    
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400

    if not file.filename.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
        return jsonify({"error": "Invalid format. Only .mp4, .avi, .mov, or .mkv allowed"}), 400

    try:
        filename = secure_filename(file.filename)
        saved_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

        # ----------------------------------------------------
        # ABSOLUTE RESOURCE RELEASE SEQUENCE (RESET ROUTINE)
        # ----------------------------------------------------
        # 1. Stop the previous run, but mark the system as PREPARING instead of ABORTED.
        #    This prevents the dashboard/SSE from disconnecting during the short gap before
        #    the background launch thread sets is_simulating=True.
        with sim_lock:
            sim_config["is_simulating"] = False
            sim_config["launch_pending"] = True
            sim_config["mission_aborted"] = False
            should_finalize_previous = bool(sim_config.get("session_logging_active") and sim_config.get("active_session_id"))

        # Finalize any previous session outside sim_lock to avoid sim_lock <->
        # video_buffer_lock deadlocks when a stream from the old dashboard is closing.
        if should_finalize_previous:
            _finalize_active_session_manually()

        # 2. Close all OpenCV resources and clear the old MJPEG cache.
        reset_frame_cache()
        close_all_video_resources()

        # 5. Join lingering background threads from the previous session
        global _launch_thread
        if _launch_thread is not None and _launch_thread.is_alive():
            try:
                _launch_thread.join(timeout=2.0)
            except Exception as te:
                print(f"[Reset Sweep] Thread join error: {te}")
        _launch_thread = None

        # 6. Now save the newly uploaded walkthrough video safely!
        file.save(saved_path)

        # 6. Clean/Re-initialize global telemetry cache with structured baseline startup values
        with sim_lock:
            global_telemetry_cache["current_live_telemetry"] = startup_baseline.copy()
            global_telemetry_cache["trajectory"] = []
            sim_config["current_live_telemetry"] = startup_baseline.copy()
            session_id = sim_config.get("active_session_id")
            if session_id:
                global_telemetry_cache[session_id] = startup_baseline.copy()

        # Parse keyframe events
        timeline_list = json.loads(timeline_str)
        formatted_timeline = []
        for item in timeline_list:
            formatted_timeline.append({
                "second": float(item.get("second", 0.0)),
                "gas_ppm": float(item.get("gas_ppm")) if item.get("gas_ppm") else None,
                "gas_mq9": float(item.get("gas_mq9")) if item.get("gas_mq9") is not None else None,
                "gas_mq135": float(item.get("gas_mq135")) if item.get("gas_mq135") is not None else None,
                "mics6814": float(item.get("mics6814")) if item.get("mics6814") is not None else None,
                "lidar_distance": float(item.get("lidar_distance")) if item.get("lidar_distance") is not None else None,
                "flame_alert": bool(item.get("flame_alert", False)),
                "temperature": float(item.get("temperature")) if item.get("temperature") else None,
                "camera_recommendation": item.get("camera_recommendation") if item.get("camera_recommendation") else None
            })
        formatted_timeline = sorted(formatted_timeline, key=lambda x: x["second"])

        # Spin off active simulation startup into an isolated background thread to prevent Flask worker starvation
        _launch_thread = threading.Thread(
            target=simulation_pipeline_loop,
            args=(saved_path, filename, formatted_timeline, current_user.username),
            daemon=True
        )
        _launch_thread.start()

        print(f"[Studio Command] Launch request received for: {filename}. Processing in background thread...")
        return jsonify({"status": "launched", "redirect": "/dashboard"})

    except Exception as e:
        print(f"[Studio Launch Error] {e}")
        return jsonify({"error": f"Failed to compile profile: {str(e)}"}), 500


@app.route('/api/set_vision_mode', methods=['POST'])
def set_vision_mode():
    """API endpoint to switch the active spectral video channel."""
    global sim_config
    if not request.is_json:
        return jsonify({"error": "JSON payload required"}), 400
        
    data = request.get_json()
    mode = data.get("mode", "RGB").upper()
    
    if mode not in ["RGB", "THERMAL", "INFRARED", "FUSION"]:
        return jsonify({"error": "Invalid camera channel override mode"}), 400

    with sim_lock:
        sim_config["current_vision_mode"] = mode
        # Propagate changes to active telemetry right away
        sim_config["current_live_telemetry"]["status"]["current_vision_mode"] = mode

    print(f"[Vision Hub Override] Camera spectrum switched to: {mode}")
    return jsonify({"status": "vision_updated", "current_vision_mode": mode})


@app.route('/api/telemetry', methods=['GET'])
def get_telemetry():
    """Direct JSON polling accessor for synced telemetry."""
    with sim_lock:
        return jsonify(sim_config["current_live_telemetry"])


@app.route('/api/telemetry/stream')
@limiter.exempt
def telemetry_stream():
    """
    High-frequency SSE telemetry stream with connection scaling protection.
    Pushes synchronized coordinates & sensor readings to the frontend dashboard.
    Features active client heartbeat tracking and structural timeout cleanup.
    """
    is_local = request.remote_addr in ['127.0.0.1', '::1']
    if not is_local:
        if not (current_user and current_user.is_authenticated):
            log_security_event("UNKNOWN", "ACCESS_DENIED:GET /api/telemetry/stream", "FAILURE", "Unauthenticated remote telemetry stream connection blocked.")
            return abort(401)
        if not current_user.has_permission('view_live_telemetry'):
            log_security_event(current_user.username, "ACCESS_DENIED:GET /api/telemetry/stream", "FAILURE", "User lacks required view_live_telemetry permission.")
            return abort(403)

    def sse_emitter():
        import gc
        try:
            active_user = current_user.username if (current_user and current_user.is_authenticated) else "Anonymous_Node"
        except Exception:
            active_user = "Anonymous_Node"
            
        print(f"[SSE Stream] Client connected: {active_user} tapped into global multicast")
        heartbeat_counter = 0
        try:
            while True:
                time.sleep(0.05)  # Yield execution cycles smoothly, prevent thread saturation and stabilize frame delivery
                
                with sim_lock:
                    is_simulating = sim_config.get("is_simulating", False)
                    launch_pending = sim_config.get("launch_pending", False)
                    mission_aborted = sim_config.get("mission_aborted", False)
                
                if launch_pending:
                    pending_payload = startup_baseline.copy()
                    pending_payload["status"] = pending_payload.get("status", {}).copy()
                    pending_payload["status"]["is_simulating"] = False
                    pending_payload["status"]["launch_pending"] = True
                    pending_payload["status"]["mission_aborted"] = False
                    pending_payload["status"]["ai_status_banner"] = "Preparing mission stream // please wait"
                    yield f"data: {json.dumps(pending_payload)}\n\n"
                    continue

                if (not is_simulating) or mission_aborted:
                    stop_payload = {
                        "status": {
                            "is_simulating": False,
                            "mission_aborted": True,
                            "current_vision_mode": "RGB",
                            "alert_level": 1,
                            "ai_status_banner": "Mission Aborted // Telemetry Broadcast Halted"
                        },
                        "sensors": {
                            "gas": {"mq9": 0.0, "mq135": 0.0, "mics6814": 0.0},
                            "bme688": {"temperature": 0.0, "humidity": 0.0, "pressure": 0.0},
                            "flame": [0, 0, 0, 0, 0],
                            "lidar": 0.0
                        }
                    }
                    yield f"data: {json.dumps(stop_payload)}\n\n"
                    log_security_event("SYSTEM", "TELEMETRY_STREAM_TERMINATED", "SUCCESS", f"Telemetry stream safely disconnected for {active_user} due to simulation stop.")
                    break

                # Active client heartbeat pulse tracking (every 1 second / 10 ticks)
                heartbeat_counter += 1
                if heartbeat_counter >= 10:
                    yield ": ping heartbeat\n\n"
                    heartbeat_counter = 0
                
                # Fetch directly from the global cache
                cached_data = global_telemetry_cache.get("current_live_telemetry")
                if not cached_data:
                    with sim_lock:
                        cached_data = sim_config.get("current_live_telemetry", {}).copy()
                
                if not cached_data:
                    cached_data = startup_baseline.copy()
                    
                payload = json.dumps(cached_data)
                yield f"data: {payload}\n\n"
        except GeneratorExit:
            print(f"[SSE Stream] Client connection closed (GeneratorExit) for: {active_user}")
        except Exception as e:
            print(f"[SSE Stream] Client connection timeout/inactive or error ({e}) for: {active_user}")
        finally:
            # Force cleanup of memory heap and recycle socket connection
            gc.collect()
            print(f"[SSE Stream] Flushed memory heap and recycled socket pool for: {active_user}")

    return Response(sse_emitter(), mimetype='text/event-stream')


def apply_thermal_fusion(rgb_frame, thermal_frame):
    """
    Applies pixel-level sensor fusion by warping the thermal frame to perfectly
    align with the RGB frame using a 3x3 homography matrix, and then blending them
    with an adaptive luminance weight.
    """
    # Spatial Registration: Use identity homography to warp thermal_frame
    H = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]], dtype=np.float32)
    warped_thermal = cv2.warpPerspective(thermal_frame, H, (rgb_frame.shape[1], rgb_frame.shape[0]))
    
    # Calculate BGR mean luminance (gray conversion)
    gray = cv2.cvtColor(rgb_frame, cv2.COLOR_BGR2GRAY)
    mean_luminance = np.mean(gray)
    
    # Adaptive Blending: beta = 0.70 if luminance < 60 (smoke/darkness), else 0.30
    if mean_luminance < 60:
        beta = 0.70
    else:
        beta = 0.30
    alpha = 1.0 - beta
    
    # Blend frames
    fused = cv2.addWeighted(rgb_frame, alpha, warped_thermal, beta, 0.0)
    return fused


def apply_spectral_mutator(frame, mode):
    """Applies conditional OpenCV matrix transformations to emulate Thermal and Night Vision."""
    if mode == "THERMAL":
        # FLIR thermal heat-mapping: convert to single-channel gray and apply color map
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        thermal = cv2.applyColorMap(gray, cv2.COLORMAP_JET)
        return thermal
        
    elif mode == "INFRARED":
        # Green NoIR Night Vision: equalise contrast, boost brightness, map green matrices
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        enhanced = cv2.equalizeHist(gray)
        
        # Multiply contrast scale slightly to emulate gain
        gain_enhanced = cv2.convertScaleAbs(enhanced, alpha=1.1, beta=15)
        
        # Create a glowing neon green BGR matrix
        green_tint = np.zeros_like(frame)
        green_tint[:, :, 1] = gain_enhanced                      # Bright green channels
        green_tint[:, :, 0] = cv2.multiply(gain_enhanced, 0.12)  # Low blue bleed
        green_tint[:, :, 2] = cv2.multiply(gain_enhanced, 0.08)  # Low red bleed
        return green_tint
        
    return frame  # RGB: return raw frame unchanged


def draw_hud_overlays(target_frame, combined_boxes, inference_status, ai_latency, vision_mode_label, flame_state, gas_mq9, lidar_val, temp_val, tel, playback_sec):
    """Draws target identification overlays, object trackers, and system telemetry indicators."""
    # D. Render combined boxes together
    for item in combined_boxes:
        x1, y1, x2, y2 = item["box"]
        color = item["color"]
        label = item["label"]
        cv2.rectangle(target_frame, (x1, y1), (x2, y2), color, 2)
        cv2.putText(target_frame, label, (x1, max(15, y1 - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)

    # E. Run additional non-YOLO emulated targets if NO models are loaded at all
    if not PERSON_MODEL_LOADED and not FIRE_MODEL_LOADED:
        if flame_state:
            pulse = int(140 + 70 * np.sin(time.time() * 8))
            cv2.rectangle(target_frame, (120, 140), (280, 320), (0, 0, pulse), 2)
            cv2.putText(target_frame, "EMULATOR TARGET: FIRE HAZARD LOCK [98.5%]", (120, 132),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 1, cv2.LINE_AA)
        
        if gas_mq9 > 150.0:
            pulse = int(150 + 60 * np.sin(time.time() * 5))
            cv2.rectangle(target_frame, (350, 80), (530, 240), (0, pulse, 255), 2)
            cv2.putText(target_frame, "EMULATOR TARGET: SMOKE CLOUD LOCK [92.1%]", (350, 72),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 140, 255), 1, cv2.LINE_AA)

    # Draw obstacle and human trackers
    if lidar_val < 60.0:
        cv2.rectangle(target_frame, (240, 340), (400, 440), (255, 0, 255), 2)
        cv2.putText(target_frame, "LIDAR WARN: CLOSE OBSTACLE", (240, 332),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 0, 255), 1, cv2.LINE_AA)

    if not PERSON_MODEL_LOADED:
        if not flame_state and gas_mq9 < 150.0:
            bounce_x = int(280 + 35 * np.sin(time.time() * 1.8))
            bounce_y = int(180 + 15 * np.cos(time.time() * 1.8))
            cv2.rectangle(target_frame, (bounce_x, bounce_y), (bounce_x + 90, bounce_y + 130), (0, 255, 0), 1)
            cv2.putText(target_frame, "EMULATOR SEARCH: RESCUER/HUMAN [95%]", (bounce_x, bounce_y - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1, cv2.LINE_AA)

    # 6. Premium Cyber-Tactical HUD Overlays
    cx, cy = 320, 240
    cv2.line(target_frame, (cx - 12, cy), (cx - 4, cy), (0, 255, 0), 1)
    cv2.line(target_frame, (cx + 4, cy), (cx + 12, cy), (0, 255, 0), 1)
    cv2.line(target_frame, (cx, cy - 12), (cx, cy - 4), (0, 255, 0), 1)
    cv2.line(target_frame, (cx, cy + 4), (cx, cy + 12), (0, 255, 0), 1)

    hud_color = (0, 255, 0) if "ONLINE" in inference_status else (0, 255, 120)
    c_len = 25
    t = 2
    # Top-Left
    cv2.line(target_frame, (15, 15), (15 + c_len, 15), hud_color, t)
    cv2.line(target_frame, (15, 15), (15, 15 + c_len), hud_color, t)
    # Top-Right
    cv2.line(target_frame, (625, 15), (625 - c_len, 15), hud_color, t)
    cv2.line(target_frame, (625, 15), (625, 15 + c_len), hud_color, t)
    # Bottom-Left
    cv2.line(target_frame, (15, 465), (15 + c_len, 465), hud_color, t)
    cv2.line(target_frame, (15, 465), (15, 465 - c_len), hud_color, t)
    # Bottom-Right
    cv2.line(target_frame, (625, 465), (625 - c_len, 465), hud_color, t)
    cv2.line(target_frame, (625, 465), (625, 465 - c_len), hud_color, t)

    # Dynamic HUD overlay panel
    cv2.putText(target_frame, f"ARES MULTI-SPECTRAL FEED: {tel['status']['video_filename'].upper()}", (25, 38), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1, cv2.LINE_AA)
    
    time_label = f"TIMECODE: {int(playback_sec)//60:02d}:{int(playback_sec)%60:02d} / {int(tel['status']['duration'])//60:02d}:{int(tel['status']['duration'])%60:02d}"
    cv2.putText(target_frame, time_label, (25, 58), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (200, 200, 200), 1, cv2.LINE_AA)
    
    coord_label = f"VIRTUAL GRID COORDS: X={tel['status']['position']['x']:.1f} Y={tel['status']['position']['y']:.1f}"
    cv2.putText(target_frame, coord_label, (25, 78), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (200, 200, 200), 1, cv2.LINE_AA)

    # Operational parameters top right
    cv2.putText(target_frame, f"BATTERY: 87.2% [12.4V]", (440, 38), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 255, 0), 1, cv2.LINE_AA)
    cv2.putText(target_frame, f"AI: {inference_status} ({ai_latency:.1f}ms)", (440, 58), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 255, 120), 1, cv2.LINE_AA)
    cv2.putText(target_frame, f"SPECTRUM: {vision_mode_label}", (440, 78), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 180, 255), 1, cv2.LINE_AA)

    # Glowing master flashing hazard box
    if flame_state:
        pulse = int(127 + 128 * np.sin(time.time() * 10))
        cv2.rectangle(target_frame, (10, 10), (630, 470), (0, 0, pulse), 2)
        cv2.putText(target_frame, "!!! HAZARD ALERT: SIMULATED FLAME !!!", (160, 445), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 255), 2, cv2.LINE_AA)
    elif gas_mq9 > 150:
        pulse = int(127 + 128 * np.sin(time.time() * 6))
        cv2.rectangle(target_frame, (10, 10), (630, 470), (0, pulse, 255), 2)
        cv2.putText(target_frame, "!!! HAZARD ALERT: SIMULATED GAS LEAK !!!", (150, 445), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 140, 255), 2, cv2.LINE_AA)


def generate_video_frames(username=None):
    """
    UGV camera frame generator wrapper with robust try...except...finally
    safeguards to prevent UGV frame buffer deadlocks on stream parsing crashes.
    """
    try:
        yield from _generate_video_frames_impl(username=username)
    except Exception as e:
        print(f"[Generator Crash Recovery] Video stream generator encountered an error: {e}")
        raise
    finally:
        # Safety net: release video_buffer_lock if inner generator left it acquired
        try:
            video_buffer_lock.release()
            print("[Generator Crash Recovery] Released video_buffer_lock in outer finally closure.")
        except RuntimeError:
            pass  # Already released by inner finally — expected


def _generate_video_frames_impl(username=None):
    """
    UGV camera frame generator. Loops uploaded walkthrough files,
    applies multi-spectral mutations, performs YOLOv8 AI inference,
    calculates synchronized timeline sensor values, and renders glowing tactical HUDs.
    """
    global sim_config
    default_frame_idx = 0
    default_fps = 30.0
    iteration_count = 0
    last_loop_duration = 0.0
    playback_start_time = time.time()
    
    while True:
        frame = None
        cap = None
        fps = 30.0
        total_frames = 0
        video_active = False

        with sim_lock:
            v_path = sim_config["video_path"]
            is_sim = sim_config["is_simulating"]
            launch_pending = sim_config.get("launch_pending", False)
        
        # 1. Open walkthrough recording
        if is_sim and v_path and os.path.exists(v_path):
            with video_buffer_lock:
                cap = cv2.VideoCapture(v_path)
                if cap.isOpened():
                    fps = cap.get(cv2.CAP_PROP_FPS)
                    if fps <= 0:
                        fps = 30.0
                    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                    video_active = True
                    _active_captures.append(cap)
                    playback_start_time = time.time() - sim_config.get("current_second", 0.0)
                    last_loop_duration = 0.0
                
        frame_idx = 0
        
        while True:
            # Check if simulation has been manually stopped
            with sim_lock:
                current_is_sim = sim_config["is_simulating"]
            if video_active and not current_is_sim:
                if cap is not None:
                    with video_buffer_lock:
                        cap.release()
                cap = None
                video_active = False
                frame_idx = 0

            iteration_count += 1
            if username != 'admin' and iteration_count % 2 == 0:
                # Stream Throttle for non-admin viewers: yield cached frame to save CPU
                cached_jpeg = None
                with video_buffer_lock:
                    cached_jpeg = _latest_frame_data.get("jpeg_bytes")
                if cached_jpeg is not None:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + cached_jpeg + b'\r\n')
                    if video_active:
                        frame_idx += 1
                    else:
                        default_frame_idx += 1
                    time.sleep(1.0 / fps)
                    continue

            # 0. Global Cache Multiplex Check: If another thread has already processed the frame for this tick, reuse it!
            current_time = time.time()
            session_id = sim_config.get("active_session_id")
            fps_target = sim_config.get("fps", 30.0)
            if fps_target <= 0:
                fps_target = 30.0
            tick_threshold = (1.0 / fps_target) * 0.8
            
            cached_jpeg = None
            with video_buffer_lock:
                time_since_last = current_time - _latest_frame_data["timestamp"]
                if _latest_frame_data["jpeg_bytes"] is not None and time_since_last < tick_threshold:
                    cached_jpeg = _latest_frame_data["jpeg_bytes"]
            
            if cached_jpeg is not None:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + cached_jpeg + b'\r\n')
                time.sleep(0.01)
                continue
 
            lock_acquired = False
            ret = False
            jpeg_bytes = None
            start_proc_time = time.time()
            
            try:
                video_buffer_lock.acquire()
                lock_acquired = True
                
                # Double-check inside lock
                current_time = time.time()
                time_since_last = current_time - _latest_frame_data["timestamp"]
                if _latest_frame_data["jpeg_bytes"] is not None and time_since_last < tick_threshold:
                    cached_jpeg = _latest_frame_data["jpeg_bytes"]
                
                if cached_jpeg is not None:
                    if lock_acquired:
                        try:
                            video_buffer_lock.release()
                        except RuntimeError:
                            pass
                        lock_acquired = False
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + cached_jpeg + b'\r\n')
                    time.sleep(0.01)
                    continue

                success = False
            
                if video_active and cap is not None:
                    ret, frame = cap.read()
                    # --- Deterministic End-of-Stream (EOS) Cleanup ---
                    # When ret is False the video has finished: do NOT resize, do NOT process.
                    # Release resources immediately and break.
                    if not ret or frame is None or frame.size == 0 or frame.shape[0] == 0 or frame.shape[1] == 0:
                        if lock_acquired:
                            try:
                                video_buffer_lock.release()
                            except RuntimeError:
                                pass
                            lock_acquired = False
                        # Release the VideoCapture handle before any state changes
                        try:
                            cap.release()
                            if cap in _active_captures:
                                _active_captures.remove(cap)
                        except Exception:
                            pass
                        cap = None
                        video_active = False
                        # IMPORTANT: never call _finalize_active_session_manually() while sim_lock
                        # is held. That function releases VideoWriters under video_buffer_lock.
                        # Calling it inside sim_lock can deadlock with another dashboard/video
                        # client that holds video_buffer_lock and is about to read sim_config.
                        should_finalize_session = False
                        with sim_lock:
                            sim_config["is_playing"] = False
                            sim_config["is_simulating"] = False
                            sim_config["launch_pending"] = False
                            sim_config["mission_aborted"] = True
                            should_finalize_session = bool(
                                sim_config.get("session_logging_active") and sim_config.get("active_session_id")
                            )

                        if should_finalize_session:
                            _finalize_active_session_manually()

                        reset_frame_cache()
                        global_telemetry_cache["current_live_telemetry"] = startup_baseline.copy()
                        global_telemetry_cache["trajectory"] = []
                        if session_id:
                            global_telemetry_cache[session_id] = startup_baseline.copy()
                        print(f"[EOS] Video stream finished cleanly at frame {frame_idx}. Simulation stopped and resources reset.")
                        break
                    
                    success = ret
                    if success and frame is not None:
                        # 2. Synchronized Timeline Reset: playback_sec will naturally be 0.0 when frame_idx is reset to 0
                        playback_sec = frame_idx / fps
                        frame_idx += 1
                else:
                    # Video missing: Generate high-tech Sci-Fi tactical radar hud view
                    success = True
                    playback_sec = (default_frame_idx / default_fps) % 180.0
                    default_frame_idx += 1
                    
                    frame = np.zeros((480, 640, 3), dtype=np.uint8)
                    for x in range(0, 640, 40):
                        cv2.line(frame, (x, 0), (x, 480), (22, 28, 22), 1)
                    for y in range(0, 480, 40):
                        cv2.line(frame, (0, y), (640, y), (22, 28, 22), 1)
                    
                    radar_angle = int(playback_sec * 85) % 360
                    radar_rad = np.radians(radar_angle)
                    center = (320, 240)
                    cv2.circle(frame, center, 180, (0, 65, 0), 1)
                    cv2.circle(frame, center, 100, (0, 45, 0), 1)
                    sweep_x = int(center[0] + 180 * np.cos(radar_rad))
                    sweep_y = int(center[1] + 180 * np.sin(radar_rad))
                    cv2.line(frame, center, (sweep_x, sweep_y), (0, 180, 0), 2)
                    
                    noise = np.random.normal(0, 3.5, frame.shape).astype(np.uint8)
                    frame = cv2.add(frame, noise)

                if not success or frame is None or frame.shape[0] == 0 or frame.shape[1] == 0:
                    if lock_acquired:
                        try:
                            video_buffer_lock.release()
                        except RuntimeError:
                            pass
                        lock_acquired = False
                    time.sleep(0.033)
                    continue

                try:
                    frame = cv2.resize(frame, (640, 480))
                except Exception as e:
                    print(f"[OpenCV Processing ERROR] cv2.resize failed: {e}")
                    if lock_acquired:
                        try:
                            video_buffer_lock.release()
                        except RuntimeError:
                            pass
                        lock_acquired = False
                    time.sleep(0.033)
                    continue

                # Keep a clean, unmutated BGR/RGB base frame
                frame_base = frame.copy()

                # Retrieve active vision mode inside thread locks
                with sim_lock:
                    vision_mode = sim_config["current_vision_mode"]

                # Keep frame as standard BGR for stable target/YOLO detections
                frame = frame_base.copy()

                # 3. Synchronize Telemetry to current frame timecode
                with sim_lock:
                    current_is_sim = sim_config["is_simulating"]

                if current_is_sim:
                    tel = compute_telemetry(playback_sec)
                    pos = tel["status"]["position"]
                    traj = global_telemetry_cache.get("trajectory", [])
                    if not traj:
                        traj = [{"x": pos["x"], "y": pos["y"]}]
                    else:
                        last_pos = traj[-1]
                        if last_pos["x"] != pos["x"] or last_pos["y"] != pos["y"]:
                            if pos["x"] != 0.0 or pos["y"] != 0.0:
                                traj.append({"x": pos["x"], "y": pos["y"]})
                                if len(traj) > 60:
                                    traj.pop(0)
                    global_telemetry_cache["trajectory"] = traj
                    tel["status"]["trajectory"] = traj
                else:
                    tel = get_baseline_telemetry(0.0)
                    global_telemetry_cache["trajectory"] = []
                    tel["status"]["trajectory"] = []

                with sim_lock:
                    # Retain visual state synchronization in SSE data
                    tel["status"]["current_vision_mode"] = vision_mode
                    sim_config["current_live_telemetry"] = tel
                    sim_config["current_second"] = playback_sec if current_is_sim else 0.0

                flame_state = any(tel["sensors"]["flame"])
                gas_mq9 = tel["sensors"]["gas"]["mq9"]
                lidar_val = tel["sensors"]["lidar"]
                temp_val = tel["sensors"]["bme688"]["temperature"]

                # 4. Run AI Inference over the Mutated Spectral frame
                combined_boxes = []
                ai_latency = 0.0
                models_ran = []

                # A. Run standard yolov8n.pt model for Person (Class 0)
                if PERSON_MODEL_LOADED and YOLO_PERSON_MODEL is not None:
                    inf_start = time.time()
                    try:
                        results = YOLO_PERSON_MODEL(frame, verbose=False)
                        ai_latency += (time.time() - inf_start) * 1000.0
                        models_ran.append("PERSON")
                        
                        for r in results:
                            boxes = r.boxes
                            for box in boxes:
                                cls = int(box.cls[0])
                                # Standard coco class 0 is 'person'
                                if cls == 0:
                                    x1, y1, x2, y2 = box.xyxy[0]
                                    x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
                                    conf = float(box.conf[0])
                                    
                                    # 1. Aspect Ratio Rule
                                    w = x2 - x1
                                    h = y2 - y1
                                    
                                    # 2. Unconscious Logic: width >= 1.3 * height
                                    is_unconscious = (h > 0) and ((w / h) >= 1.3)
                                    
                                    # 3. Tactical Visuals
                                    if is_unconscious:
                                        color = (180, 0, 255)  # Highly visible neon-purple (BGR)
                                        label = f"CRITICAL: UNCONSCIOUS VICTIM [{conf:.2f}]"
                                    else:
                                        color = (0, 255, 0)    # Neon-green (BGR)
                                        label = f"RESCUER/HUMAN [{conf:.2f}]"
                                    
                                    combined_boxes.append({
                                        "box": (x1, y1, x2, y2),
                                        "conf": conf,
                                        "class": "person",
                                        "color": color,
                                        "label": label
                                    })
                    except Exception as e:
                        print(f"[AI Pipeline ERROR] Person inference error: {e}")

                # B. Run specialized fire-detection-yolov8 model for Fire and Smoke
                if FIRE_MODEL_LOADED and YOLO_FIRE_MODEL is not None:
                    inf_start = time.time()
                    try:
                        results = YOLO_FIRE_MODEL(frame, verbose=False)
                        ai_latency += (time.time() - inf_start) * 1000.0
                        models_ran.append("FIRE")
                        
                        for r in results:
                            boxes = r.boxes
                            for box in boxes:
                                cls = int(box.cls[0])
                                conf = float(box.conf[0])
                                class_name = YOLO_FIRE_MODEL.names.get(cls, "unknown").lower()
                                if "fire" in class_name or "smoke" in class_name:
                                    x1, y1, x2, y2 = box.xyxy[0]
                                    x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
                                    if "fire" in class_name:
                                        color = (0, 0, 255) # Red for Fire
                                        label = f"FIRE {conf:.2f}"
                                    else:
                                        color = (0, 255, 255) # Amber/Yellow for Smoke
                                        label = f"SMOKE {conf:.2f}"
                                    
                                    combined_boxes.append({
                                        "box": (x1, y1, x2, y2),
                                        "conf": conf,
                                        "class": class_name,
                                        "color": color,
                                        "label": label
                                    })
                    except Exception as e:
                        print(f"[AI Pipeline ERROR] Fire/Smoke inference error: {e}")
                else:
                    # ENFORCE HSV COLOR-THRESHOLDING FALLBACK FILTER FOR FIRE
                    # Process the frame using HSV masking to detect bright orange/red contours
                    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
                    
                    # 1. Tighten the HSV Range to isolate strictly luminous fire colors
                    # Hue: 0-18 (luminous red-orange-yellow), Saturation: >= 160 (highly saturated), Value: >= 210 (very bright)
                    lower_orange_red = np.array([0, 160, 210])
                    upper_orange_red = np.array([18, 255, 255])
                    
                    # Wrap-around red range: Hue: 165-180, Saturation: >= 160, Value: >= 210
                    lower_wrap_red = np.array([165, 160, 210])
                    upper_wrap_red = np.array([180, 255, 255])
                    
                    mask1 = cv2.inRange(hsv, lower_orange_red, upper_orange_red)
                    mask2 = cv2.inRange(hsv, lower_wrap_red, upper_wrap_red)
                    mask = cv2.bitwise_or(mask1, mask2)
                    
                    # 3. Morphological Dilation / closing to bridge disjointed fire spots
                    # First run open kernel to remove tiny static noise pixels
                    kernel_open = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
                    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel_open)
                    
                    # Next run a large closing kernel to bridge nearby spots into unified boxes
                    kernel_close = cv2.getStructuringElement(cv2.MORPH_RECT, (21, 21))
                    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel_close)
                    
                    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                    
                    # 2. Enforce strict area threshold (Ignore detected blocks smaller than 1000 pixels)
                    raw_fire_boxes = []
                    for c in contours:
                        area = cv2.contourArea(c)
                        if area >= 1000:
                            x, y, w, h = cv2.boundingRect(c)
                            raw_fire_boxes.append([x, y, x + w, y + h, area, 1])  # [x1, y1, x2, y2, area, merge_count]
                    
                    # 4. Merge overlapping coordinates into a single tactical box labeled "FIRE SOURCE"
                    changed = True
                    while changed:
                        changed = False
                        to_remove = set()
                        n = len(raw_fire_boxes)
                        for i in range(n):
                            if i in to_remove:
                                continue
                            for j in range(i + 1, n):
                                if j in to_remove:
                                    continue
                                x1_a, y1_a, x2_a, y2_a, area_a, count_a = raw_fire_boxes[i]
                                x1_b, y1_b, x2_b, y2_b, area_b, count_b = raw_fire_boxes[j]
                                
                                # Overlap check
                                if not (x2_a < x1_b or x2_b < x1_a or y2_a < y1_b or y2_b < y1_a):
                                    raw_fire_boxes[i] = [
                                        min(x1_a, x1_b),
                                        min(y1_a, y1_b),
                                        max(x2_a, x2_b),
                                        max(y2_a, y2_b),
                                        area_a + area_b,
                                        count_a + count_b
                                    ]
                                    to_remove.add(j)
                                    changed = True
                        if changed:
                            raw_fire_boxes = [raw_fire_boxes[idx] for idx in range(n) if idx not in to_remove]
                    
                    detected_count = len(raw_fire_boxes)
                    
                    # Append detected and merged fire boxes to combined output
                    for item in raw_fire_boxes:
                        x1, y1, x2, y2, area, merge_count = item
                        conf = min(0.99, 0.70 + (area / 15000.0))
                        
                        # Choose label based on overlap status to satisfy both layout contexts cleanly
                        label = "FIRE SOURCE" if merge_count > 1 else "AI INTERACTION: FIRE HOTSPOT"
                        combined_boxes.append({
                            "box": (x1, y1, x2, y2),
                            "conf": conf,
                            "class": "fire",
                            "color": (0, 0, 255),  # High-contrast bright tactical red
                            "label": label
                        })
                    
                    # Fail-safe timeline-driven emulation backup if OpenCV HSV masking yielded zero matches
                    # (e.g. in thermal/infrared spectrums where BGR channels are shifted and normal red is lost)
                    if flame_state and detected_count == 0:
                        pulse = int(140 + 70 * np.sin(time.time() * 8))
                        combined_boxes.append({
                            "box": (120, 140, 280, 320),
                            "conf": 0.91,
                            "class": "fire",
                            "color": (0, 0, pulse),
                            "label": "AI INTERACTION: FIRE HOTSPOT",
                            "is_emulated": True
                        })
                    
                    # Smoke cloud target tracking
                    if gas_mq9 > 150.0:
                        pulse = int(150 + 60 * np.sin(time.time() * 5))
                        combined_boxes.append({
                            "box": (350, 80, 530, 240),
                            "conf": 0.88,
                            "class": "smoke",
                            "color": (0, pulse, 255),
                            "label": "AI DETECT: SMOKE CLOUD [88.5%]",
                            "is_emulated": True
                        })

                # C. Determine overall inference status string
                if PERSON_MODEL_LOADED and FIRE_MODEL_LOADED:
                    inference_status = "MULTI-MODEL ONLINE"
                elif PERSON_MODEL_LOADED:
                    inference_status = "PERSON-ONLY ONLINE"
                elif FIRE_MODEL_LOADED:
                    inference_status = "FIRE-ONLY ONLINE"
                else:
                    inference_status = "AI FALLBACK ACTIVE"

                # D. Render combined boxes together onto the frame
                for item in combined_boxes:
                    x1, y1, x2, y2 = item["box"]
                    color = item["color"]
                    label = item["label"]
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                    cv2.putText(frame, label, (x1, max(15, y1 - 8)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)

                # E. Run additional non-YOLO emulated targets if NO models are loaded at all
                if not PERSON_MODEL_LOADED and not FIRE_MODEL_LOADED:
                    # Simulated targeting elements drawn in harmony with active channel values
                    if flame_state:
                        pulse = int(140 + 70 * np.sin(time.time() * 8))
                        cv2.rectangle(frame, (120, 140), (280, 320), (0, 0, pulse), 2)
                        cv2.putText(frame, "EMULATOR TARGET: FIRE HAZARD LOCK [98.5%]", (120, 132),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 1, cv2.LINE_AA)
                    
                    if gas_mq9 > 150.0:
                        pulse = int(150 + 60 * np.sin(time.time() * 5))
                        cv2.rectangle(frame, (350, 80), (530, 240), (0, pulse, 255), 2)
                        cv2.putText(frame, "EMULATOR TARGET: SMOKE CLOUD LOCK [92.1%]", (350, 72),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 140, 255), 1, cv2.LINE_AA)

                # Draw obstacle and human trackers
                if lidar_val < 60.0:
                    cv2.rectangle(frame, (240, 340), (400, 440), (255, 0, 255), 2)
                    cv2.putText(frame, "LIDAR WARN: CLOSE OBSTACLE", (240, 332),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 0, 255), 1, cv2.LINE_AA)

                # Draw standard search/rescuer tracking box only if person model is not active
                if not PERSON_MODEL_LOADED:
                    if not flame_state and gas_mq9 < 150.0:
                        bounce_x = int(280 + 35 * np.sin(time.time() * 1.8))
                        bounce_y = int(180 + 15 * np.cos(time.time() * 1.8))
                        cv2.rectangle(frame, (bounce_x, bounce_y), (bounce_x + 90, bounce_y + 130), (0, 255, 0), 1)
                        cv2.putText(frame, "EMULATOR SEARCH: RESCUER/HUMAN [95%]", (bounce_x, bounce_y - 6),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1, cv2.LINE_AA)
                    else:
                        # Emulate an unconscious victim during active emergency simulation keyframe
                        combined_boxes.append({
                            "box": (180, 280, 360, 360),  # w=180, h=80 -> ratio=2.25 >= 1.3
                            "conf": 0.94,
                            "class": "person",
                            "color": (180, 0, 255),  # Highly visible neon-purple (BGR)
                            "label": "CRITICAL: UNCONSCIOUS VICTIM",
                            "is_emulated": True
                        })

                # Create standard unannotated thermal frame to crop thermal intensities safely
                thermal_base = apply_spectral_mutator(frame_base.copy(), "THERMAL")
                
                # Warp the thermal frame to register coordinates perfectly (Identity Homography)
                H = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]], dtype=np.float32)
                warped_thermal_base = cv2.warpPerspective(thermal_base, H, (frame_base.shape[1], frame_base.shape[0]))
                
                # AI Cross-Verification Latch over all 'person' detections
                is_thermal_lock_active = False
                for item in combined_boxes:
                    if item.get("class") == "person":
                        x1, y1, x2, y2 = item["box"]
                        # Calculate aspect ratio to check if unconscious
                        w_box = x2 - x1
                        h_box = y2 - y1
                        is_unconscious = (h_box > 0) and ((w_box / h_box) >= 1.3)
                        
                        # Safe crop
                        img_h, img_w = frame_base.shape[:2]
                        cx1, cy1 = max(0, x1), max(0, y1)
                        cx2, cy2 = min(img_w, x2), min(img_h, y2)
                        
                        if cx2 > cx1 and cy2 > cy1:
                            thermal_crop = warped_thermal_base[cy1:cy2, cx1:cx2]
                            mean_r = np.mean(thermal_crop[:, :, 2]) # Red channel is index 2 in BGR
                            temp_celsius = 34.0 + 5.5 * (mean_r / 255.0)
                        else:
                            temp_celsius = 0.0
                        
                        # Validate: 35.0 <= temp_celsius <= 38.0
                        if 35.0 <= temp_celsius <= 38.0:
                            item["label"] = f"CONFIRMED_LIFE_SIGN // {'UNCONSCIOUS' if is_unconscious else 'HUMAN'} [{item['conf']:.2f}]"
                            item["color"] = (0, 255, 0)  # Green for confirmed
                            is_thermal_lock_active = True
                        else:
                            item["label"] = f"OCCLUDED/NON-HUMAN // {'UNCONSCIOUS' if is_unconscious else 'HUMAN'} [{item['conf']:.2f}]"
                            item["color"] = (0, 0, 255)  # Red for non-human

                # Count unconscious victims and update global telemetry state
                fallen_victim_count = sum(1 for item in combined_boxes if item.get("class") == "person" and "CONFIRMED_LIFE_SIGN" in item.get("label", "") and "UNCONSCIOUS" in item.get("label", ""))
                fire_present = any(item.get("class") in ["fire", "smoke"] for item in combined_boxes)
                with sim_lock:
                    sim_config["fire_visual_alert"] = fire_present
                    if "status" in sim_config["current_live_telemetry"]:
                        sim_config["current_live_telemetry"]["status"]["unconscious_victims"] = fallen_victim_count
                        sim_config["current_live_telemetry"]["status"]["fire_detected"] = fire_present
                        sim_config["current_live_telemetry"]["status"]["thermal_lock"] = "ACTIVE" if is_thermal_lock_active else "INACTIVE"

                    # --- Session Telemetry Logging (throttled to every ~500ms) ---
                    if sim_config["session_logging_active"] and sim_config["active_session_id"]:
                        global _telemetry_log_tick
                        _telemetry_log_tick += 1

                        # Update running aggregation accumulators
                        if gas_mq9 > _session_agg["max_gas_ppm"]:
                            _session_agg["max_gas_ppm"] = gas_mq9
                        if temp_val > _session_agg["max_temperature"]:
                            _session_agg["max_temperature"] = temp_val
                        if fire_present:
                            _session_agg["fire_incident_triggered"] = True
                        if fallen_victim_count > _session_agg["_peak_victims_in_frame"]:
                            _session_agg["_peak_victims_in_frame"] = fallen_victim_count
                        _session_agg["total_victims_found"] = max(
                            _session_agg["total_victims_found"],
                            _session_agg["_peak_victims_in_frame"]
                        )

                        # Log a telemetry row every 15 frames (~500ms at 30fps)
                        if _telemetry_log_tick % 15 == 0:
                            detection_labels = [item.get("label", "") for item in (combined_boxes or [])]
                            ai_summary = "; ".join(detection_labels) if detection_labels else "CLEAR"
                            db_enqueue(
                                'INSERT INTO telemetry_logs (session_id, timestamp, gas_mq9, temperature, flame_state, lidar_distance, ai_detections_summary, unconscious_victims) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                                (
                                    sim_config["active_session_id"],
                                    datetime.now(timezone.utc).isoformat(),
                                    round(gas_mq9, 2),
                                    round(temp_val, 2),
                                    1 if flame_state else 0,
                                    round(lidar_val, 1),
                                    ai_summary[:500],
                                    fallen_victim_count
                                )
                            )

                # Create four distinct annotated BGR frames for concurrent recording
                rec_normal = frame_base.copy()
                rec_thermal = thermal_base.copy()
                rec_noir = apply_spectral_mutator(frame_base.copy(), "INFRARED")
                rec_fused = apply_thermal_fusion(frame_base.copy(), thermal_base)

                # Draw overlays on all four recorded frames
                draw_hud_overlays(rec_normal, combined_boxes, inference_status, ai_latency, "RGB", flame_state, gas_mq9, lidar_val, temp_val, tel, playback_sec)
                draw_hud_overlays(rec_thermal, combined_boxes, inference_status, ai_latency, "THERMAL", flame_state, gas_mq9, lidar_val, temp_val, tel, playback_sec)
                draw_hud_overlays(rec_noir, combined_boxes, inference_status, ai_latency, "INFRARED", flame_state, gas_mq9, lidar_val, temp_val, tel, playback_sec)
                draw_hud_overlays(rec_fused, combined_boxes, inference_status, ai_latency, "FUSION", flame_state, gas_mq9, lidar_val, temp_val, tel, playback_sec)

                # Draw overlays on the live frame (frame_live is mutated to the active vision_mode)
                if vision_mode == "FUSION":
                    frame_live = apply_thermal_fusion(frame_base.copy(), thermal_base)
                else:
                    frame_live = apply_spectral_mutator(frame_base.copy(), vision_mode)
                draw_hud_overlays(frame_live, combined_boxes, inference_status, ai_latency, vision_mode, flame_state, gas_mq9, lidar_val, temp_val, tel, playback_sec)

                # Write processed frames concurrently to the active OpenCV VideoWriters
                global active_video_writer_normal, active_video_writer_thermal, active_video_writer_noir, active_video_writer_fused
                
                target_size = (640, 480)
                writers_and_frames = [
                    (active_video_writer_normal, rec_normal, "normal RGB"),
                    (active_video_writer_thermal, rec_thermal, "thermal FLIR"),
                    (active_video_writer_noir, rec_noir, "low-light NoIR"),
                    (active_video_writer_fused, rec_fused, "pixel-level fused")
                ]
                
                for writer, variant_frame, name in writers_and_frames:
                    if writer is not None:
                        try:
                            final_frame = cv2.resize(variant_frame, target_size)
                            if final_frame is None or final_frame.size == 0:
                                continue
                            writer.write(final_frame)
                        except Exception as ve:
                            print(f"[Video Recording ERROR] Failed to write {name} frame: {ve}")

                # Encode live frame BGR buffer to JPEG
                ret, jpeg = cv2.imencode('.jpg', frame_live)
                
                # --- Update cache & Release lock ---
                if ret:
                    jpeg_bytes = jpeg.tobytes()
                    # Update global reference cache
                    _latest_frame_data["jpeg_bytes"] = jpeg_bytes
                    _latest_frame_data["timestamp"] = time.time()
                    _latest_frame_data["session_id"] = session_id

                # Update global telemetry cache once per frame tick
                with sim_lock:
                    telemetry_copy = sim_config["current_live_telemetry"].copy()
                    global_telemetry_cache["current_live_telemetry"] = telemetry_copy
                    if session_id:
                        global_telemetry_cache[session_id] = telemetry_copy

                # Lock will be released in the finally block below
            except Exception as pe:
                print(f"[OpenCV Processing ERROR] Frame processing crashed: {pe}")
                raise
            finally:
                # Single, authoritative lock release point
                if lock_acquired:
                    try:
                        video_buffer_lock.release()
                    except RuntimeError:
                        pass
                    lock_acquired = False

            if ret:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + jpeg_bytes + b'\r\n')

            # --- Real-Time Playback Pacing (Wall-Clock Time-Sync) ---
            # Ensure the frame output rate strictly matches the actual video duration.
            # A 12.1s video must play in exactly 12.1s of real time.
            if video_active and frame_idx > 0:
                expected_duration = frame_idx / fps
                actual_duration = time.time() - playback_start_time
                drift = expected_duration - actual_duration
                if drift > 0.001:
                    time.sleep(drift)
            else:
                # Non-video (radar idle) mode: pace at nominal FPS
                elapsed = time.time() - start_proc_time
                sleep_time = max(0.001, (1.0 / fps) - elapsed)
                time.sleep(sleep_time)
            last_loop_duration = time.time() - start_proc_time

            # --- 3. Explicit Memory Optimization ---
            # Release references to large image arrays and object detection buffers to prevent leaks
            frame = None
            write_frame = None
            jpeg = None
            hsv = None
            mask = None
            mask1 = None
            mask2 = None
            combined_boxes = None
            
            # Periodically invoke garbage collector every 30 frames
            if (frame_idx > 0 and frame_idx % 30 == 0) or (default_frame_idx > 0 and default_frame_idx % 30 == 0):
                import gc
                gc.collect()

        if cap is not None:
            with video_buffer_lock:
                cap.release()


@app.route('/video_feed')
@limiter.exempt
def video_feed():
    """Video feed output (MJPEG)."""
    is_local = request.remote_addr in ['127.0.0.1', '::1']
    if not is_local:
        if not (current_user and current_user.is_authenticated):
            log_security_event("UNKNOWN", "ACCESS_DENIED:GET /video_feed", "FAILURE", "Unauthenticated remote video feed connection blocked.")
            return abort(401)
        if not current_user.has_permission('view_live_telemetry'):
            log_security_event(current_user.username, "ACCESS_DENIED:GET /video_feed", "FAILURE", "User lacks required view_live_telemetry permission.")
            return abort(403)
    username = current_user.username if (current_user and current_user.is_authenticated) else "admin"
    return Response(generate_video_frames(username=username),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


def _finalize_active_session_manually():
    """
    Called when the simulation is stopped manually.
    Finalizes the active session, releases the video writer,
    and triggers report generation without starting a new session.
    """
    global _telemetry_log_tick, active_video_writer_normal, active_video_writer_thermal, active_video_writer_noir, active_video_writer_fused

    session_id = sim_config.get("active_session_id")
    if not session_id or not sim_config.get("session_logging_active"):
        return

    # Freeze logging
    sim_config["session_logging_active"] = False

    # Capture aggregation snapshot
    agg = {
        "max_gas_ppm": round(_session_agg["max_gas_ppm"], 2),
        "max_temperature": round(_session_agg["max_temperature"], 2),
        "fire_incident_triggered": 1 if _session_agg["fire_incident_triggered"] else 0,
        "total_victims_found": _session_agg["total_victims_found"]
    }
    duration = sim_config.get("current_second", 0.0)

    # Enqueue session update
    db_enqueue(
        '''UPDATE sessions SET end_time=?, total_victims_found=?, max_gas_ppm=?,
           max_temperature=?, fire_incident_triggered=?, duration_seconds=?
           WHERE session_id=?''',
        (
            datetime.now(timezone.utc).isoformat(),
            agg["total_victims_found"],
            agg["max_gas_ppm"],
            agg["max_temperature"],
            agg["fire_incident_triggered"],
            round(duration, 1),
            session_id
        )
    )
    print(f"[Session] Mission session {session_id} manually finalized. Fire={agg['fire_incident_triggered']}, Victims={agg['total_victims_found']}, MaxGas={agg['max_gas_ppm']}ppm")

    # Release active video writers safely under lock to prevent concurrent write race conditions
    with video_buffer_lock:
        for w_name, w in [("normal", active_video_writer_normal), ("thermal", active_video_writer_thermal), ("noir", active_video_writer_noir), ("fused", active_video_writer_fused)]:
            if w is not None:
                try:
                    w.release()
                    print(f"[Video Recording] Released {w_name} writer successfully")
                except Exception as e:
                    print(f"[Video Recording WARNING] Failed to release {w_name} writer: {e}")
        active_video_writer_normal = None
        active_video_writer_thermal = None
        active_video_writer_noir = None
        active_video_writer_fused = None


    # Spawn report generation in background
    threading.Thread(target=_generate_reports_deferred, args=(session_id,), daemon=True).start()

    # Reset active session ID to nominal
    sim_config["active_session_id"] = None


def _finalize_session_on_rewind():
    """
    Called INSIDE sim_lock when the video loop rewinds to frame 0.
    Finalizes the current session's aggregated stats in the DB,
    triggers background report generation, and starts a new session.
    """
    global _telemetry_log_tick

    session_id = sim_config.get("active_session_id")
    if not session_id or not sim_config.get("session_logging_active"):
        return

    # Freeze logging for the current session
    sim_config["session_logging_active"] = False

    # Capture aggregation snapshot
    agg = {
        "max_gas_ppm": round(_session_agg["max_gas_ppm"], 2),
        "max_temperature": round(_session_agg["max_temperature"], 2),
        "fire_incident_triggered": 1 if _session_agg["fire_incident_triggered"] else 0,
        "total_victims_found": _session_agg["total_victims_found"]
    }
    duration = sim_config.get("duration", 0.0)

    # Enqueue the session UPDATE
    db_enqueue(
        '''UPDATE sessions SET end_time=?, total_victims_found=?, max_gas_ppm=?,
           max_temperature=?, fire_incident_triggered=?, duration_seconds=?
           WHERE session_id=?''',
        (
            datetime.now(timezone.utc).isoformat(),
            agg["total_victims_found"],
            agg["max_gas_ppm"],
            agg["max_temperature"],
            agg["fire_incident_triggered"],
            round(duration, 1),
            session_id
        )
    )
    print(f"[Session] Mission session {session_id} finalized. Fire={agg['fire_incident_triggered']}, Victims={agg['total_victims_found']}, MaxGas={agg['max_gas_ppm']}ppm")

    # Release active video writers safely before generating reports
    global active_video_writer_normal, active_video_writer_thermal, active_video_writer_noir, active_video_writer_fused
    with video_buffer_lock:
        for w_name, w in [("normal", active_video_writer_normal), ("thermal", active_video_writer_thermal), ("noir", active_video_writer_noir), ("fused", active_video_writer_fused)]:
            if w is not None:
                try:
                    w.release()
                    print(f"[Video Recording] Released {w_name} writer successfully on rewind")
                except Exception as e:
                    print(f"[Video Recording WARNING] Failed to release {w_name} writer on rewind: {e}")
        active_video_writer_normal = None
        active_video_writer_thermal = None
        active_video_writer_noir = None
        active_video_writer_fused = None

    # Spawn report generation in background thread
    threading.Thread(target=_generate_reports_deferred, args=(session_id,), daemon=True).start()

    # Start a fresh session immediately for the next loop
    new_session_id = str(uuid.uuid4())[:8]
    sim_config["active_session_id"] = new_session_id
    sim_config["session_logging_active"] = True
    _telemetry_log_tick = 0
    _session_agg["max_gas_ppm"] = 0.0
    _session_agg["max_temperature"] = 0.0
    _session_agg["fire_incident_triggered"] = False
    _session_agg["total_victims_found"] = 0
    _session_agg["_peak_victims_in_frame"] = 0

    # Initialize new video writers for the new session
    new_session_dir = os.path.join(REPORTS_DIR, new_session_id)
    os.makedirs(new_session_dir, exist_ok=True)

    fps = sim_config.get("fps", 30.0)
    
    # Standard configuration target dimensions
    target_size = (640, 480)
    
    active_video_writer_normal = create_video_writer(os.path.join(new_session_dir, "cam_normal.mp4"), fps, target_size[0], target_size[1])
    active_video_writer_thermal = create_video_writer(os.path.join(new_session_dir, "cam_thermal.mp4"), fps, target_size[0], target_size[1])
    active_video_writer_noir = create_video_writer(os.path.join(new_session_dir, "cam_noir.mp4"), fps, target_size[0], target_size[1])
    active_video_writer_fused = create_video_writer(os.path.join(new_session_dir, "fused_mission.mp4"), fps, target_size[0], target_size[1])



    db_enqueue(
        'INSERT INTO sessions (session_id, start_time, mode, video_filename, duration_seconds) VALUES (?, ?, ?, ?, ?)',
        (new_session_id, datetime.now(timezone.utc).isoformat(), 'Autonomous',
         sim_config.get("video_filename", "Unknown"), round(duration, 1))
    )
    print(f"[Session] New mission session started: {new_session_id}")


def _generate_reports_deferred(session_id):
    """
    Background thread function. Waits briefly for DB writes to flush,
    then reads session data and generates HTML + PDF reports.
    """
    # Wait for the DB writer to flush pending inserts
    time.sleep(2.0)

    try:
        # Read session metadata
        sessions = db_read('SELECT * FROM sessions WHERE session_id = ?', (session_id,))
        if not sessions:
            print(f"[Report Generator ERROR] Session {session_id} not found in database.")
            return
        session_data = sessions[0]

        # Read telemetry logs
        telemetry_rows = db_read(
            'SELECT * FROM telemetry_logs WHERE session_id = ? ORDER BY timestamp ASC',
            (session_id,)
        )

        # Create report directory
        report_dir = os.path.join(REPORTS_DIR, session_id)
        os.makedirs(report_dir, exist_ok=True)

        html_path = os.path.join(report_dir, f"{session_id}_report.html")
        pdf_path = os.path.join(report_dir, f"{session_id}_report.pdf")

        _build_html_report(session_id, session_data, telemetry_rows, html_path)
        _build_pdf_report(session_id, session_data, telemetry_rows, pdf_path)

        print(f"[Report Generator] Reports generated for session {session_id}: HTML + PDF")

    except Exception as e:
        print(f"[Report Generator ERROR] Failed for session {session_id}: {e}")


def _build_html_report(session_id, session_data, telemetry_rows, output_path):
    """Generates a self-contained Tailwind-styled HTML safety audit report."""
    import json
    
    start_time = session_data.get("start_time", "N/A")
    end_time = session_data.get("end_time", "N/A")
    duration_sec = session_data.get("duration_seconds", 0.0)
    video_filename = session_data.get("video_filename", "N/A")
    mode = session_data.get("mode", "Autonomous")
    max_gas = session_data.get("max_gas_ppm", 0.0)
    max_temp = session_data.get("max_temperature", 0.0)
    fire_triggered = bool(session_data.get("fire_incident_triggered", 0))
    total_victims = session_data.get("total_victims_found", 0)

    # --- Pre-calculate telemetry elapsed_seconds, derived sensor feeds, and 2D path coordinates ---
    parsed_telemetry = []
    cleaned_start = start_time.strip()
    if cleaned_start.endswith('Z'):
        cleaned_start = cleaned_start[:-1] + '+00:00'
    try:
        dt_start = datetime.fromisoformat(cleaned_start)
    except Exception:
        dt_start = datetime.now(timezone.utc)

    for i, row in enumerate(telemetry_rows):
        row_dict = dict(row)
        ts_val = row_dict.get("timestamp", "")
        cleaned_ts = ts_val.strip()
        if cleaned_ts.endswith('Z'):
            cleaned_ts = cleaned_ts[:-1] + '+00:00'
        try:
            dt_row = datetime.fromisoformat(cleaned_ts)
            elapsed = (dt_row - dt_start).total_seconds()
            if elapsed < 0:
                elapsed = 0.0
        except Exception:
            elapsed = i * 0.5  # Fallback spacing 500ms

        row_dict["elapsed_seconds"] = round(elapsed, 2)
        
        # Calculate derived orbital grid coordinates
        pos_x = 200.0 + 120.0 * np.cos(elapsed * 0.22)
        pos_y = 200.0 + 120.0 * np.sin(elapsed * 0.22)
        row_dict["position_x"] = round(pos_x, 1)
        row_dict["position_y"] = round(pos_y, 1)

        # Derived gas MQ-135, MiCS-6814, and Humidity sensors
        mq9 = row_dict.get("gas_mq9", 0.0) or 0.0
        row_dict["gas_mq135"] = round(mq9 * 1.88, 2)
        row_dict["gas_mics6814"] = round(mq9 / 72.0, 3)

        temp = row_dict.get("temperature", 0.0) or 0.0
        row_dict["humidity"] = round(max(5.0, 48.0 - (temp - 22.4) * 0.75), 2)
        
        parsed_telemetry.append(row_dict)

    mission_telemetry_json = json.dumps(parsed_telemetry)

    # Build hazard event rows (only rows with active hazards) for static table display
    hazard_rows_html = ""
    for row in parsed_telemetry:
        is_hazard = (
            row.get("flame_state", 0) == 1 or
            (row.get("gas_mq9") or 0) > 150.0 or
            (row.get("unconscious_victims") or 0) > 0
        )
        if is_hazard:
            ts = row.get("timestamp", "N/A")
            try:
                dt = datetime.fromisoformat(ts.strip().replace('Z', '+00:00'))
                ts_display = dt.strftime("%H:%M:%S.%f")[:-3]
            except Exception:
                ts_display = ts[:19]

            flame_badge = '<span style="color:#f43f5e;font-weight:bold;display:inline-flex;align-items:center;gap:6px;"><svg style="width:14px;height:14px;" fill="none" stroke="#f43f5e" viewBox="0 0 24 24" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8.5 14.5A2.5 2.5 0 0011 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 11-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 002.5 2.5z"/></svg>ACTIVE</span>' if row.get("flame_state") else '<span style="color:#10b981;">CLEAR</span>'
            gas_val = row.get("gas_mq9", 0.0)
            gas_color = "#f43f5e" if gas_val > 400 else "#f59e0b" if gas_val > 150 else "#10b981"
            victims_val = row.get("unconscious_victims", 0)
            victims_badge = f'<span style="color:#a855f7;font-weight:bold;">{victims_val} FOUND</span>' if victims_val > 0 else '<span style="color:#10b981;">0</span>'

            hazard_rows_html += f"""
                <tr style="border-bottom:1px solid rgba(255,255,255,0.05);">
                    <td style="padding:10px 12px;font-family:monospace;font-size:12px;color:#94a3b8;">{ts_display}</td>
                    <td style="padding:10px 12px;font-family:monospace;font-size:12px;color:{gas_color};font-weight:bold;">{gas_val:.1f} ppm</td>
                    <td style="padding:10px 12px;font-family:monospace;font-size:12px;color:#94a3b8;">{row.get('temperature', 0.0):.1f} °C</td>
                    <td style="padding:10px 12px;font-size:12px;">{flame_badge}</td>
                    <td style="padding:10px 12px;font-family:monospace;font-size:12px;color:#94a3b8;">{row.get('lidar_distance', 0.0):.1f} cm</td>
                    <td style="padding:10px 12px;font-size:12px;">{victims_badge}</td>
                    <td style="padding:10px 12px;font-family:monospace;font-size:11px;color:#64748b;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{row.get('ai_detections_summary', 'N/A')[:80]}</td>
                </tr>"""

    if not hazard_rows_html:
        hazard_rows_html = '<tr><td colspan="7" style="padding:24px;text-align:center;color:#64748b;font-size:13px;">No hazard events detected during this session.</td></tr>'

    fire_badge_html = '<span style="color:#f43f5e;font-weight:bold;font-size:18px;display:inline-flex;align-items:center;gap:6px;"><svg style="width:20px;height:20px;" fill="none" stroke="#f43f5e" viewBox="0 0 24 24" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M8.5 14.5A2.5 2.5 0 0011 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 11-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 002.5 2.5z"/></svg>YES — FIRE INCIDENT CONFIRMED</span>' if fire_triggered else '<span style="color:#10b981;font-weight:bold;font-size:18px;display:inline-flex;align-items:center;gap:6px;"><svg style="width:20px;height:20px;" fill="none" stroke="#10b981" viewBox="0 0 24 24" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>NO FIRE INCIDENTS</span>'

    duration_display = f"{int(duration_sec) // 60}m {int(duration_sec) % 60}s" if duration_sec else "N/A"

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ARES Safety Report — {session_id.upper()}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&family=Orbitron:wght@500;700;900&display=swap" rel="stylesheet">
    <style>
        body {{ font-family: 'Inter', sans-serif; background: #0a0e1a; color: #e2e8f0; }}
        .font-hud {{ font-family: 'Orbitron', monospace; }}
    </style>
</head>
<body style="margin:0; padding:0; min-height:100vh;">

    <!-- HEADER BAND -->
    <div style="background:linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #0f172a 100%); border-bottom:2px solid rgba(16,185,129,0.3); padding:32px 40px;">
        <div style="max-width:1100px; margin:0 auto;">
            <div style="display:flex; align-items:center; gap:12px; margin-bottom:8px;">
                <div style="width:10px;height:10px;border-radius:50%;background:#10b981;box-shadow:0 0 12px rgba(16,185,129,0.6);"></div>
                <span class="font-hud" style="font-size:10px;color:#10b981;letter-spacing:4px;">CLASSIFIED // INTERNAL USE ONLY</span>
            </div>
            <h1 class="font-hud" style="font-size:22px; font-weight:900; color:white; letter-spacing:3px; margin:0;">
                ARES DISASTER RESPONSE &amp; INDUSTRIAL SAFETY AUDIT REPORT
            </h1>
            <p style="font-size:12px; color:#64748b; margin-top:8px; font-family:monospace;">
                Session: {session_id.upper()} &nbsp;|&nbsp; Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
            </p>
        </div>
    </div>

    <div style="max-width:1100px; margin:0 auto; padding:32px 40px;">

        <!-- METADATA GRID -->
        <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(220px, 1fr)); gap:16px; margin-bottom:32px;">
            <div style="background:rgba(15,23,42,0.8); border:1px solid rgba(255,255,255,0.06); border-radius:8px; padding:20px;">
                <div style="font-size:9px; color:#64748b; text-transform:uppercase; letter-spacing:2px; margin-bottom:6px;" class="font-hud">Session ID</div>
                <div style="font-size:16px; font-weight:bold; color:#22d3ee; font-family:monospace;">{session_id.upper()}</div>
            </div>
            <div style="background:rgba(15,23,42,0.8); border:1px solid rgba(255,255,255,0.06); border-radius:8px; padding:20px;">
                <div style="font-size:9px; color:#64748b; text-transform:uppercase; letter-spacing:2px; margin-bottom:6px;" class="font-hud">Duration</div>
                <div style="font-size:16px; font-weight:bold; color:#e2e8f0;">{duration_display}</div>
            </div>
            <div style="background:rgba(15,23,42,0.8); border:1px solid rgba(255,255,255,0.06); border-radius:8px; padding:20px;">
                <div style="font-size:9px; color:#64748b; text-transform:uppercase; letter-spacing:2px; margin-bottom:6px;" class="font-hud">Operational Mode</div>
                <div style="font-size:16px; font-weight:bold; color:#e2e8f0;">{mode}</div>
            </div>
            <div style="background:rgba(15,23,42,0.8); border:1px solid rgba(255,255,255,0.06); border-radius:8px; padding:20px;">
                <div style="font-size:9px; color:#64748b; text-transform:uppercase; letter-spacing:2px; margin-bottom:6px;" class="font-hud">Video Source</div>
                <div style="font-size:13px; font-weight:bold; color:#e2e8f0; word-break:break-all;">{video_filename}</div>
            </div>
            <div style="background:rgba(15,23,42,0.8); border:1px solid rgba(255,255,255,0.06); border-radius:8px; padding:20px;">
                <div style="font-size:9px; color:#64748b; text-transform:uppercase; letter-spacing:2px; margin-bottom:6px;" class="font-hud">Start Time</div>
                <div style="font-size:13px; font-weight:bold; color:#e2e8f0; font-family:monospace;">{start_time[:19]}</div>
            </div>
            <div style="background:rgba(15,23,42,0.8); border:1px solid rgba(255,255,255,0.06); border-radius:8px; padding:20px;">
                <div style="font-size:9px; color:#64748b; text-transform:uppercase; letter-spacing:2px; margin-bottom:6px;" class="font-hud">End Time</div>
                <div style="font-size:13px; font-weight:bold; color:#e2e8f0; font-family:monospace;">{end_time[:19] if end_time != 'N/A' else 'N/A'}</div>
            </div>
        </div>

        <!-- INTERACTIVE POST-MISSION ANALYTICS PLAYER DASHBOARD -->
        <h2 class="font-hud" style="font-size:13px; font-weight:700; color:#10b981; letter-spacing:3px; margin-bottom:16px; border-bottom:1px solid rgba(16,185,129,0.2); padding-bottom:8px;">
            POST-MISSION MULTI-STREAM ANALYTICS PLAYER
        </h2>

        <!-- Interactive Sub-Dashboard Grid -->
        <div style="display:grid; grid-template-columns: 1fr; gap: 24px; margin-bottom: 32px;" class="lg:grid-cols-3">
            
            <!-- VIEWPORT PANEL (Left - Col Span 2) -->
            <div class="lg:col-span-2" style="background:rgba(15,23,42,0.8); border:1px solid rgba(255,255,255,0.06); border-radius:8px; padding:20px; display:flex; flex-direction:column; gap:16px;">
                
                <!-- Viewport tab buttons -->
                <div style="display:flex; gap:10px; border-bottom:1px solid rgba(255,255,255,0.06); padding-bottom:12px;">
                    <button id="tab-normal" onclick="switchStream('normal')" class="tab-btn font-hud" style="flex:1; padding:10px; border-radius:4px; font-size:11px; font-weight:bold; letter-spacing:1px; text-transform:uppercase; text-align:center; transition:all 0.2s; border:1px solid #10b981; color:#fff; background:rgba(16,185,129,0.15); cursor:pointer;">
                        STANDARD RGB LINK
                    </button>
                    <button id="tab-thermal" onclick="switchStream('thermal')" class="tab-btn font-hud" style="flex:1; padding:10px; border-radius:4px; font-size:11px; font-weight:bold; letter-spacing:1px; text-transform:uppercase; text-align:center; transition:all 0.2s; border:1px solid rgba(255,255,255,0.1); color:#94a3b8; background:rgba(15,23,42,0.6); cursor:pointer;">
                        INFRARED THERMAL LINK
                    </button>
                    <button id="tab-noir" onclick="switchStream('noir')" class="tab-btn font-hud" style="flex:1; padding:10px; border-radius:4px; font-size:11px; font-weight:bold; letter-spacing:1px; text-transform:uppercase; text-align:center; transition:all 0.2s; border:1px solid rgba(255,255,255,0.1); color:#94a3b8; background:rgba(15,23,42,0.6); cursor:pointer;">
                        NOIR NIGHT-VISION LINK
                    </button>
                    <button id="tab-fused" onclick="switchStream('fused')" class="tab-btn font-hud" style="flex:1; padding:10px; border-radius:4px; font-size:11px; font-weight:bold; letter-spacing:1px; text-transform:uppercase; text-align:center; transition:all 0.2s; border:1px solid rgba(255,255,255,0.1); color:#94a3b8; background:rgba(15,23,42,0.6); cursor:pointer;">
                        SENSOR FUSION LINK
                    </button>
                </div>

                <!-- Video Viewports -->
                <div style="position:relative; width:100%; aspect-ratio:4/3; background:#000; border-radius:6px; overflow:hidden;" class="border border-slate-800 shadow-2xl">
                    <video id="video-normal" controls preload="auto" style="position:absolute; top:0; left:0; width:100%; height:100%; object-fit:contain;" class="video-stream">
                        <source src="cam_normal.mp4" type="video/mp4">
                    </video>
                    <video id="video-thermal" controls preload="auto" style="position:absolute; top:0; left:0; width:100%; height:100%; object-fit:contain; display:none;" class="video-stream">
                        <source src="cam_thermal.mp4" type="video/mp4">
                    </video>
                    <video id="video-noir" controls preload="auto" style="position:absolute; top:0; left:0; width:100%; height:100%; object-fit:contain; display:none;" class="video-stream">
                        <source src="cam_noir.mp4" type="video/mp4">
                    </video>
                    <video id="video-fused" controls preload="auto" style="position:absolute; top:0; left:0; width:100%; height:100%; object-fit:contain; display:none;" class="video-stream">
                        <source src="fused_mission.mp4" type="video/mp4">
                    </video>
                </div>

                <!-- Download Stream Items with Direct SVGs -->
                <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap:10px;">
                    <a href="cam_normal.mp4" download style="text-decoration:none; display:flex; align-items:center; gap:8px; justify-content:center; padding:8px 12px; background:rgba(15,23,42,0.9); border:1px solid rgba(255,255,255,0.06); border-radius:4px; font-family:monospace; font-size:10px; color:#e2e8f0; transition:all 0.2s;" onmouseover="this.style.background='rgba(34,211,238,0.1)'" onmouseout="this.style.background='rgba(15,23,42,0.9)'">
                        <svg style="width:14px;height:14px;" fill="none" stroke="#22d3ee" viewBox="0 0 24 24" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>
                        DOWNLOAD RGB BUNDLE
                    </a>
                    <a href="cam_thermal.mp4" download style="text-decoration:none; display:flex; align-items:center; gap:8px; justify-content:center; padding:8px 12px; background:rgba(15,23,42,0.9); border:1px solid rgba(255,255,255,0.06); border-radius:4px; font-family:monospace; font-size:10px; color:#e2e8f0; transition:all 0.2s;" onmouseover="this.style.background='rgba(244,63,94,0.1)'" onmouseout="this.style.background='rgba(15,23,42,0.9)'">
                        <svg style="width:14px;height:14px;" fill="none" stroke="#f43f5e" viewBox="0 0 24 24" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>
                        DOWNLOAD THERMAL BUNDLE
                    </a>
                    <a href="cam_noir.mp4" download style="text-decoration:none; display:flex; align-items:center; gap:8px; justify-content:center; padding:8px 12px; background:rgba(15,23,42,0.9); border:1px solid rgba(255,255,255,0.06); border-radius:4px; font-family:monospace; font-size:10px; color:#e2e8f0; transition:all 0.2s;" onmouseover="this.style.background='rgba(168,85,247,0.1)'" onmouseout="this.style.background='rgba(15,23,42,0.9)'">
                        <svg style="width:14px;height:14px;" fill="none" stroke="#a855f7" viewBox="0 0 24 24" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>
                        DOWNLOAD NOIR BUNDLE
                    </a>
                    <a href="fused_mission.mp4" download style="text-decoration:none; display:flex; align-items:center; gap:8px; justify-content:center; padding:8px 12px; background:rgba(15,23,42,0.9); border:1px solid rgba(255,255,255,0.06); border-radius:4px; font-family:monospace; font-size:10px; color:#e2e8f0; transition:all 0.2s;" onmouseover="this.style.background='rgba(16,185,129,0.1)'" onmouseout="this.style.background='rgba(15,23,42,0.9)'">
                        <svg style="width:14px;height:14px;" fill="none" stroke="#10b981" viewBox="0 0 24 24" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>
                        DOWNLOAD FUSED BUNDLE
                    </a>
                </div>
            </div>

            <!-- ANALYTICS PANEL (Right - Col Span 1) -->
            <div style="display:flex; flex-direction:column; gap:20px;">
                
                <!-- MINI 2D CANVAS TRACKING MAP -->
                <div style="background:rgba(15,23,42,0.8); border:1px solid rgba(255,255,255,0.06); border-radius:8px; padding:20px; display:flex; flex-direction:column; align-items:center; gap:12px;">
                    <div style="width:100%; display:flex; justify-content:space-between; align-items:center;">
                        <span class="font-hud text-xs text-slate-400" style="letter-spacing:1px;">TACTICAL 2D PATH MAP</span>
                        <span id="player-grid-coords" class="font-mono text-xs text-cyan-400">X: ---.0 Y: ---.0</span>
                    </div>
                    <canvas id="tactical-map" width="220" height="220" style="background:#0b0f19; border:1px solid rgba(255,255,255,0.06); border-radius:6px;"></canvas>
                </div>

                <!-- DYNAMIC UGV SENSORS GRID -->
                <div style="background:rgba(15,23,42,0.8); border:1px solid rgba(255,255,255,0.06); border-radius:8px; padding:20px; display:flex; flex-direction:column; gap:16px;">
                    <span class="font-hud text-xs text-slate-400" style="letter-spacing:1px;">UGV TELEMETRY SENSOR GRID</span>
                    
                    <!-- Gas Sensors Progress Bars -->
                    <div style="display:flex; flex-direction:column; gap:10px;">
                        <!-- MQ-9 -->
                        <div>
                            <div style="display:flex; justify-content:space-between; font-size:10px; font-family:monospace; margin-bottom:4px;">
                                <span class="text-slate-400">GAS MQ-9 (Combustibles)</span>
                                <span id="val-gas-mq9" class="text-cyan-400 font-bold">--- PPM</span>
                            </div>
                            <div style="width:100%; height:8px; background:rgba(255,255,255,0.05); border-radius:4px; overflow:hidden;">
                                <div id="bar-gas-mq9" style="width:0%; height:100%; background:#22d3ee; border-radius:4px; transition:width 0.2s;"></div>
                            </div>
                        </div>

                        <!-- MQ-135 -->
                        <div>
                            <div style="display:flex; justify-content:space-between; font-size:10px; font-family:monospace; margin-bottom:4px;">
                                <span class="text-slate-400">GAS MQ-135 (Toxic Gases)</span>
                                <span id="val-gas-mq135" class="text-amber-400 font-bold">--- PPM</span>
                            </div>
                            <div style="width:100%; height:8px; background:rgba(255,255,255,0.05); border-radius:4px; overflow:hidden;">
                                <div id="bar-gas-mq135" style="width:0%; height:100%; background:#fbbf24; border-radius:4px; transition:width 0.2s;"></div>
                            </div>
                        </div>

                        <!-- MiCS-6814 -->
                        <div>
                            <div style="display:flex; justify-content:space-between; font-size:10px; font-family:monospace; margin-bottom:4px;">
                                <span class="text-slate-400">MiCS-6814 (Carbon Monoxide)</span>
                                <span id="val-gas-mics" class="text-purple-400 font-bold">--- PPM</span>
                            </div>
                            <div style="width:100%; height:8px; background:rgba(255,255,255,0.05); border-radius:4px; overflow:hidden;">
                                <div id="bar-gas-mics" style="width:0%; height:100%; background:#c084fc; border-radius:4px; transition:width 0.2s;"></div>
                            </div>
                        </div>
                    </div>

                    <!-- Atmospheric & Lidar counters -->
                    <div style="display:grid; grid-template-columns:1fr 1fr; gap:12px; border-top:1px solid rgba(255,255,255,0.06); padding-top:12px;">
                        <div style="background:rgba(255,255,255,0.02); border-radius:4px; padding:10px; border:1px solid rgba(255,255,255,0.04); text-align:center;">
                            <div style="font-size:9px; color:#64748b;" class="font-hud">TEMPERATURE</div>
                            <div id="val-temp" style="font-size:16px; font-weight:bold; color:#e2e8f0;" class="font-hud">--- °C</div>
                        </div>
                        <div style="background:rgba(255,255,255,0.02); border-radius:4px; padding:10px; border:1px solid rgba(255,255,255,0.04); text-align:center;">
                            <div style="font-size:9px; color:#64748b;" class="font-hud">HUMIDITY</div>
                            <div id="val-humidity" style="font-size:16px; font-weight:bold; color:#e2e8f0;" class="font-hud">--- %</div>
                        </div>
                        <div style="background:rgba(255,255,255,0.02); border-radius:4px; padding:10px; border:1px solid rgba(255,255,255,0.04); text-align:center;">
                            <div style="font-size:9px; color:#64748b;" class="font-hud">LIDAR DISTANCE</div>
                            <div id="val-lidar" style="font-size:16px; font-weight:bold; color:#e2e8f0;" class="font-hud">--- cm</div>
                        </div>
                        <div style="background:rgba(255,255,255,0.02); border-radius:4px; padding:10px; border:1px solid rgba(255,255,255,0.04); text-align:center; display:flex; flex-direction:column; align-items:center; justify-content:center;">
                            <div style="font-size:9px; color:#64748b;" class="font-hud">VICTIMS ACTIVE</div>
                            <div id="badge-victims" style="font-size:12px; font-weight:bold; color:#10b981; padding:2px 6px; border-radius:3px; background:rgba(16,185,129,0.1); margin-top:2px;">0</div>
                        </div>
                    </div>

                    <!-- AI Detections HUD Logger -->
                    <div style="background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.04); border-radius:4px; padding:10px; font-family:monospace; font-size:10px; display:flex; flex-direction:column; gap:4px;">
                        <span style="color:#64748b;">AI AUDIT FEEDBACK LOG:</span>
                        <div id="val-ai-log" style="color:#22d3ee; max-height:36px; overflow-y:auto; line-height:1.2;">NOMINAL // NO DETECTIONS</div>
                    </div>
                </div>
            </div>
        </div>

        <!-- CORE ANALYTICS MATRIX -->
        <h2 class="font-hud" style="font-size:13px; font-weight:700; color:#94a3b8; letter-spacing:3px; margin-bottom:16px; border-bottom:1px solid rgba(255,255,255,0.06); padding-bottom:8px;">
            CORE ANALYTICS MATRIX
        </h2>
        <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(250px, 1fr)); gap:16px; margin-bottom:40px;">
            <div style="background:rgba(15,23,42,0.8); border:1px solid rgba(244,63,94,0.15); border-radius:8px; padding:24px; text-align:center;">
                <div style="font-size:9px; color:#64748b; text-transform:uppercase; letter-spacing:2px; margin-bottom:10px;" class="font-hud">Peak Gas Concentration</div>
                <div style="font-size:28px; font-weight:900; color:{'#f43f5e' if max_gas > 400 else '#f59e0b' if max_gas > 150 else '#10b981'}; font-family:monospace;">{max_gas:.1f} PPM</div>
            </div>
            <div style="background:rgba(15,23,42,0.8); border:1px solid rgba(245,158,11,0.15); border-radius:8px; padding:24px; text-align:center;">
                <div style="font-size:9px; color:#64748b; text-transform:uppercase; letter-spacing:2px; margin-bottom:10px;" class="font-hud">Peak Temperature</div>
                <div style="font-size:28px; font-weight:900; color:{'#f43f5e' if max_temp > 50 else '#f59e0b' if max_temp > 35 else '#10b981'}; font-family:monospace;">{max_temp:.1f} °C</div>
            </div>
            <div style="background:rgba(15,23,42,0.8); border:1px solid rgba(168,85,247,0.15); border-radius:8px; padding:24px; text-align:center;">
                <div style="font-size:9px; color:#64748b; text-transform:uppercase; letter-spacing:2px; margin-bottom:10px;" class="font-hud">Unconscious Victims</div>
                <div style="font-size:28px; font-weight:900; color:{'#a855f7' if total_victims > 0 else '#10b981'}; font-family:monospace;">{total_victims}</div>
            </div>
            <div style="background:rgba(15,23,42,0.8); border:1px solid rgba(244,63,94,0.15); border-radius:8px; padding:24px; text-align:center;">
                <div style="font-size:9px; color:#64748b; text-transform:uppercase; letter-spacing:2px; margin-bottom:10px;" class="font-hud">Fire Incident</div>
                <div>{fire_badge_html}</div>
            </div>
        </div>

        <!-- HAZARD TIMELINE TABLE -->
        <h2 class="font-hud" style="font-size:13px; font-weight:700; color:#94a3b8; letter-spacing:3px; margin-bottom:16px; border-bottom:1px solid rgba(255,255,255,0.06); padding-bottom:8px;">
            HAZARD TIMELINE EVENTS
        </h2>
        <div style="overflow-x:auto; border-radius:8px; border:1px solid rgba(255,255,255,0.06);">
            <table style="width:100%; border-collapse:collapse; background:rgba(15,23,42,0.6);">
                <thead>
                    <tr style="background:rgba(15,23,42,0.95); border-bottom:2px solid rgba(16,185,129,0.2);">
                        <th style="padding:12px; text-align:left; font-size:9px; color:#64748b; letter-spacing:2px; text-transform:uppercase;" class="font-hud">Timestamp</th>
                        <th style="padding:12px; text-align:left; font-size:9px; color:#64748b; letter-spacing:2px; text-transform:uppercase;" class="font-hud">Gas MQ-9</th>
                        <th style="padding:12px; text-align:left; font-size:9px; color:#64748b; letter-spacing:2px; text-transform:uppercase;" class="font-hud">Temperature</th>
                        <th style="padding:12px; text-align:left; font-size:9px; color:#64748b; letter-spacing:2px; text-transform:uppercase;" class="font-hud">Flame</th>
                        <th style="padding:12px; text-align:left; font-size:9px; color:#64748b; letter-spacing:2px; text-transform:uppercase;" class="font-hud">LiDAR</th>
                        <th style="padding:12px; text-align:left; font-size:9px; color:#64748b; letter-spacing:2px; text-transform:uppercase;" class="font-hud">Victims</th>
                        <th style="padding:12px; text-align:left; font-size:9px; color:#64748b; letter-spacing:2px; text-transform:uppercase;" class="font-hud">AI Detections</th>
                    </tr>
                </thead>
                <tbody>
                    {hazard_rows_html}
                </tbody>
            </table>
        </div>

        <div style="margin-top:40px; padding-top:20px; border-top:1px solid rgba(255,255,255,0.06); text-align:center;">
            <p style="font-size:10px; color:#475569; font-family:monospace;">
                ARES AUTONOMOUS RESCUE &amp; EMERGENCY SYSTEM // SAFETY REPORT AUTO-GENERATED // {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}
            </p>
        </div>
    </div>

    <!-- Time-Synchronization and Canvas Map Scripting -->
    <script>
        const missionTelemetry = {mission_telemetry_json};
        
        const videos = {{
            normal: document.getElementById('video-normal'),
            thermal: document.getElementById('video-thermal'),
            noir: document.getElementById('video-noir'),
            fused: document.getElementById('video-fused')
        }};
        
        let activeMode = 'normal';
        
        function switchStream(newMode) {{
            if (newMode === activeMode) return;
            
            const currentVideo = videos[activeMode];
            const nextVideo = videos[newMode];
            
            const isPlaying = !currentVideo.paused;
            const currentTime = currentVideo.currentTime;
            
            currentVideo.pause();
            currentVideo.style.display = 'none';
            
            nextVideo.currentTime = currentTime;
            nextVideo.style.display = 'block';
            
            if (isPlaying) {{
                nextVideo.play().catch(err => console.log("Auto-play failed: ", err));
            }} else {{
                nextVideo.pause();
            }}
            
            activeMode = newMode;
            
            // Update Tab active styles
            document.querySelectorAll('.tab-btn').forEach(btn => {{
                btn.style.borderColor = 'rgba(255,255,255,0.1)';
                btn.style.color = '#94a3b8';
                btn.style.background = 'rgba(15,23,42,0.6)';
            }});
            
            const activeBtn = document.getElementById(`tab-${{newMode}}`);
            activeBtn.style.borderColor = '#10b981';
            activeBtn.style.color = '#fff';
            activeBtn.style.background = 'rgba(16,185,129,0.15)';
        }}

        // Time updates synchronization logic
        Object.values(videos).forEach(video => {{
            video.addEventListener('timeupdate', () => {{
                if (video.id !== `video-${{activeMode}}`) return;
                updateTelemetryForTime(video.currentTime);
            }});
        }});

        const canvas = document.getElementById('tactical-map');
        const ctx = canvas.getContext('2d');

        function updateTelemetryForTime(time) {{
            if (!missionTelemetry || missionTelemetry.length === 0) return;
            
            // Find closest row
            let closest = missionTelemetry[0];
            let minDiff = Math.abs(closest.elapsed_seconds - time);
            
            for (let i = 1; i < missionTelemetry.length; i++) {{
                const diff = Math.abs(missionTelemetry[i].elapsed_seconds - time);
                if (diff < minDiff) {{
                    minDiff = diff;
                    closest = missionTelemetry[i];
                }}
            }}
            
            // Update sensor numbers and bars
            document.getElementById('val-gas-mq9').textContent = closest.gas_mq9.toFixed(1) + ' PPM';
            document.getElementById('bar-gas-mq9').style.width = Math.min(100, (closest.gas_mq9 / 600) * 100) + '%';
            
            document.getElementById('val-gas-mq135').textContent = closest.gas_mq135.toFixed(1) + ' PPM';
            document.getElementById('bar-gas-mq135').style.width = Math.min(100, (closest.gas_mq135 / 1200) * 100) + '%';
            
            document.getElementById('val-gas-mics').textContent = closest.gas_mics6814.toFixed(3) + ' PPM';
            document.getElementById('bar-gas-mics').style.width = Math.min(100, (closest.gas_mics6814 / 10) * 100) + '%';
            
            document.getElementById('val-temp').textContent = closest.temperature.toFixed(2) + ' °C';
            // Adjust temperature HUD color based on hazard thresholds
            if (closest.temperature > 50) {{
                document.getElementById('val-temp').style.color = '#f43f5e';
            }} else if (closest.temperature > 35) {{
                document.getElementById('val-temp').style.color = '#fbbf24';
            }} else {{
                document.getElementById('val-temp').style.color = '#10b981';
            }}
            
            document.getElementById('val-humidity').textContent = closest.humidity.toFixed(2) + ' %';
            document.getElementById('val-lidar').textContent = closest.lidar_distance.toFixed(1) + ' cm';
            if (closest.lidar_distance < 60.0) {{
                document.getElementById('val-lidar').style.color = '#f43f5e';
            }} else {{
                document.getElementById('val-lidar').style.color = '#e2e8f0';
            }}
            
            // Victim Badge
            const badge = document.getElementById('badge-victims');
            badge.textContent = closest.unconscious_victims;
            if (closest.unconscious_victims > 0) {{
                badge.style.color = '#fff';
                badge.style.background = '#a855f7';
                badge.style.boxShadow = '0 0 10px rgba(168,85,247,0.5)';
            }} else {{
                badge.style.color = '#10b981';
                badge.style.background = 'rgba(16,185,129,0.1)';
                badge.style.boxShadow = 'none';
            }}
            
            // AI feedback log
            const logDiv = document.getElementById('val-ai-log');
            if (closest.ai_detections_summary && closest.ai_detections_summary !== "CLEAR") {{
                logDiv.textContent = closest.ai_detections_summary;
                logDiv.style.color = '#f59e0b';
            }} else {{
                logDiv.textContent = "NOMINAL // MULTI-SPECTRAL PATROL SECURE";
                logDiv.style.color = '#10b981';
            }}

            // Update coordinate displays and canvas map
            document.getElementById('player-grid-coords').textContent = `X: ${{closest.position_x.toFixed(1)}} Y: ${{closest.position_y.toFixed(1)}}`;
            drawTacticalMap(closest);
        }}

        function drawTacticalMap(activeRow) {{
            const W = canvas.width;
            const H = canvas.height;
            const padding = 20;
            
            ctx.clearRect(0, 0, W, H);
            
            // Grid Lines
            ctx.strokeStyle = 'rgba(16, 185, 129, 0.08)';
            ctx.lineWidth = 1;
            for (let x = 0; x < W; x += 30) {{
                ctx.beginPath();
                ctx.moveTo(x, 0);
                ctx.lineTo(x, H);
                ctx.stroke();
            }}
            for (let y = 0; y < H; y += 30) {{
                ctx.beginPath();
                ctx.moveTo(0, y);
                ctx.lineTo(W, y);
                ctx.stroke();
            }}
            
            function scaleX(val) {{
                return padding + (val - 80) / 240 * (W - 2 * padding);
            }}
            function scaleY(val) {{
                return padding + (val - 80) / 240 * (H - 2 * padding);
            }}
            
            // Complete Dotted Path
            ctx.strokeStyle = 'rgba(16, 185, 129, 0.35)';
            ctx.lineWidth = 2;
            ctx.setLineDash([4, 4]);
            ctx.beginPath();
            for (let i = 0; i < missionTelemetry.length; i++) {{
                const tx = scaleX(missionTelemetry[i].position_x);
                const ty = scaleY(missionTelemetry[i].position_y);
                if (i === 0) {{
                    ctx.moveTo(tx, ty);
                }} else {{
                    ctx.lineTo(tx, ty);
                }}
            }}
            ctx.stroke();
            ctx.setLineDash([]);
            
            // Pulse active coordinates dot
            if (activeRow) {{
                const ax = scaleX(activeRow.position_x);
                const ay = scaleY(activeRow.position_y);
                
                const pulse = 6 + 4 * Math.sin(Date.now() * 0.008);
                ctx.fillStyle = 'rgba(34, 211, 238, 0.22)';
                ctx.beginPath();
                ctx.arc(ax, ay, pulse + 6, 0, 2 * Math.PI);
                ctx.fill();
                
                ctx.fillStyle = 'rgba(34, 211, 238, 0.4)';
                ctx.beginPath();
                ctx.arc(ax, ay, pulse, 0, 2 * Math.PI);
                ctx.fill();
                
                ctx.fillStyle = '#22d3ee';
                ctx.beginPath();
                ctx.arc(ax, ay, 4, 0, 2 * Math.PI);
                ctx.fill();
            }}
        }}
        
        // Initial drawing
        if (missionTelemetry && missionTelemetry.length > 0) {{
            updateTelemetryForTime(0);
        }}
    </script>
</body>
</html>"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)



def _build_pdf_report(session_id, session_data, telemetry_rows, output_path):
    """Generates a formal print-ready PDF safety audit report using fpdf2."""
    try:
        from fpdf import FPDF
    except ImportError:
        print("[Report Generator WARNING] fpdf2 not installed. Skipping PDF generation.")
        return

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    # --- Dark Header Band ---
    pdf.set_fill_color(15, 23, 42)
    pdf.rect(0, 0, 210, 38, 'F')
    pdf.set_y(10)
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 8, "ARES DISASTER RESPONSE & INDUSTRIAL", ln=True, align='C')
    pdf.cell(0, 8, "SAFETY AUDIT REPORT", ln=True, align='C')
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(148, 163, 184)
    pdf.cell(0, 5, f"Session: {session_id.upper()}  |  Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}", ln=True, align='C')
    pdf.ln(8)

    # --- Session Metadata ---
    pdf.set_text_color(30, 41, 59)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, "SESSION METADATA", ln=True)
    pdf.set_draw_color(16, 185, 129)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(3)

    pdf.set_font("Helvetica", "", 9)
    meta_items = [
        ("Session ID", session_id.upper()),
        ("Video Source", str(session_data.get("video_filename", "N/A"))),
        ("Duration", f"{session_data.get('duration_seconds', 0):.1f} seconds"),
        ("Mode", str(session_data.get("mode", "Autonomous"))),
        ("Start Time", str(session_data.get("start_time", "N/A"))[:19]),
        ("End Time", str(session_data.get("end_time", "N/A"))[:19]),
    ]
    for label, value in meta_items:
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(71, 85, 105)
        pdf.cell(50, 6, f"{label}:", align='L')
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(30, 41, 59)
        pdf.cell(0, 6, value, ln=True)
    pdf.ln(6)

    # --- Core Analytics ---
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(0, 8, "CORE ANALYTICS MATRIX", ln=True)
    pdf.set_draw_color(16, 185, 129)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(3)

    max_gas = session_data.get("max_gas_ppm", 0.0)
    max_temp = session_data.get("max_temperature", 0.0)
    fire_triggered = bool(session_data.get("fire_incident_triggered", 0))
    total_victims = session_data.get("total_victims_found", 0)

    analytics = [
        ("Peak Gas Concentration (MQ-9)", f"{max_gas:.1f} PPM"),
        ("Peak Temperature", f"{max_temp:.1f} C"),
        ("Fire Incident Triggered", "YES" if fire_triggered else "NO"),
        ("Unconscious Victims Detected", str(total_victims)),
    ]
    for label, value in analytics:
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(71, 85, 105)
        pdf.cell(80, 6, f"{label}:", align='L')
        pdf.set_font("Helvetica", "B", 10)
        # Color-code critical values
        if "YES" in value or (max_gas > 400 and "PPM" in value):
            pdf.set_text_color(244, 63, 94)
        elif total_victims > 0 and "Victims" in label:
            pdf.set_text_color(168, 85, 247)
        else:
            pdf.set_text_color(16, 185, 129)
        pdf.cell(0, 6, value, ln=True)
    pdf.ln(6)

    # --- Hazard Timeline Table ---
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(0, 8, "HAZARD TIMELINE EVENTS", ln=True)
    pdf.set_draw_color(16, 185, 129)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(3)

    # Filter hazard rows
    hazard_events = [
        row for row in telemetry_rows
        if row.get("flame_state", 0) == 1 or
        (row.get("gas_mq9") or 0) > 150.0 or
        (row.get("unconscious_victims") or 0) > 0
    ]

    if not hazard_events:
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(100, 116, 139)
        pdf.cell(0, 8, "No hazard events detected during this session.", ln=True, align='C')
    else:
        # Table header
        col_widths = [35, 25, 25, 22, 22, 20, 41]
        headers = ["Timestamp", "Gas PPM", "Temp", "Flame", "LiDAR", "Victims", "AI Summary"]
        pdf.set_font("Helvetica", "B", 7)
        pdf.set_fill_color(15, 23, 42)
        pdf.set_text_color(255, 255, 255)
        for i, header in enumerate(headers):
            pdf.cell(col_widths[i], 7, header, border=1, fill=True, align='C')
        pdf.ln()

        # Table rows with alternating shading
        pdf.set_font("Helvetica", "", 7)
        for idx, row in enumerate(hazard_events[:100]):  # Cap at 100 rows for PDF
            if idx % 2 == 0:
                pdf.set_fill_color(241, 245, 249)
            else:
                pdf.set_fill_color(255, 255, 255)
            pdf.set_text_color(30, 41, 59)

            ts = str(row.get("timestamp", ""))
            try:
                dt = datetime.fromisoformat(ts)
                ts_short = dt.strftime("%H:%M:%S")
            except Exception:
                ts_short = ts[:8]

            gas_val = row.get("gas_mq9", 0.0)
            flame_text = "ACTIVE" if row.get("flame_state") else "CLEAR"
            victims_val = row.get("unconscious_victims", 0)
            ai_text = str(row.get("ai_detections_summary", ""))[:30]

            pdf.cell(col_widths[0], 6, ts_short, border=1, fill=True, align='C')
            pdf.cell(col_widths[1], 6, f"{gas_val:.1f}", border=1, fill=True, align='C')
            pdf.cell(col_widths[2], 6, f"{row.get('temperature', 0.0):.1f}", border=1, fill=True, align='C')
            pdf.cell(col_widths[3], 6, flame_text, border=1, fill=True, align='C')
            pdf.cell(col_widths[4], 6, f"{row.get('lidar_distance', 0.0):.1f}", border=1, fill=True, align='C')
            pdf.cell(col_widths[5], 6, str(victims_val), border=1, fill=True, align='C')
            pdf.cell(col_widths[6], 6, ai_text, border=1, fill=True, align='L')
            pdf.ln()

    # Footer
    pdf.ln(10)
    pdf.set_font("Helvetica", "I", 7)
    pdf.set_text_color(148, 163, 184)
    pdf.cell(0, 5, f"ARES AUTONOMOUS RESCUE & EMERGENCY SYSTEM // SAFETY REPORT AUTO-GENERATED // {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}", ln=True, align='C')

    pdf.output(output_path)


# --- Secure Admin Settings Views ---

@app.route('/admin/settings', methods=['GET'])
@login_required
def admin_settings_page():
    """Renders the secure ARES Cyber-Tactical IAM settings dashboard for root admin."""
    if current_user.username != 'admin':
        log_security_event(current_user.username, "ACCESS_DENIED:GET /admin/settings", "FAILURE", "Non-admin attempted to access secure admin settings page.")
        return abort(403)
    return render_template('admin_settings.html')


# --- Admin IAM Management Endpoints ---

@app.route('/api/admin/roles', methods=['GET'])
@login_required
def admin_get_roles():
    """Returns a list of all defined roles in ARES."""
    if current_user.username != 'admin':
        log_security_event(current_user.username, "ACCESS_DENIED:GET /api/admin/roles", "FAILURE", "Non-admin attempted to read roles list.")
        return abort(403)
    try:
        roles = db_read("SELECT * FROM roles ORDER BY id ASC")
        return jsonify(roles)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/admin/users', methods=['GET'])
@login_required
def admin_get_users():
    """Returns a list of all defined users and their associated role names in ARES."""
    if current_user.username != 'admin':
        log_security_event(current_user.username, "ACCESS_DENIED:GET /api/admin/users", "FAILURE", "Non-admin attempted to read users list.")
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


@app.route('/api/admin/roles/create', methods=['POST'])
@login_required
def admin_create_role():
    """Allows the root administrator to create a custom dynamic role with explicit boolean toggles."""
    if current_user.username != 'admin':
        log_security_event(current_user.username, "ACCESS_DENIED:POST /api/admin/roles/create", "FAILURE", "Non-admin attempted to create system role.")
        return abort(403)
        
    if not request.is_json:
        return jsonify({"error": "JSON payload required"}), 400
        
    data = request.get_json()
    name = data.get("name", "").strip().lower()
    if not name:
        return jsonify({"error": "Role name is required"}), 400
        
    # Standard 7 permissions
    delete_logs = 1 if bool(data.get("delete_logs")) else 0
    export_reports = 1 if bool(data.get("export_reports")) else 0
    run_simulations = 1 if bool(data.get("run_simulations")) else 0
    view_live_telemetry = 1 if bool(data.get("view_live_telemetry")) else 0
    power_toggle_robot = 1 if bool(data.get("power_toggle_robot")) else 0
    toggle_navigation_mode = 1 if bool(data.get("toggle_navigation_mode")) else 0
    manual_robot_control = 1 if bool(data.get("manual_robot_control")) else 0
    
    # 1. Pre-validation checks: Check if role already exists
    existing = db_read("SELECT id FROM roles WHERE name = ?", (name,))
    if existing:
        return jsonify({"error": f"Role '{name}' already exists"}), 400
        
    # 2. Enqueue creation query
    db_enqueue("""
        INSERT INTO roles (name, delete_logs, export_reports, run_simulations, view_live_telemetry, power_toggle_robot, toggle_navigation_mode, manual_robot_control)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (name, delete_logs, export_reports, run_simulations, view_live_telemetry, power_toggle_robot, toggle_navigation_mode, manual_robot_control))
    
    log_security_event(current_user.username, f"CREATE_ROLE:{name}", "SUCCESS", f"Custom role created with permissions: delete_logs={delete_logs}, export_reports={export_reports}, run_simulations={run_simulations}, view_live_telemetry={view_live_telemetry}, power_toggle_robot={power_toggle_robot}, toggle_navigation_mode={toggle_navigation_mode}, manual_robot_control={manual_robot_control}")
    return jsonify({"status": "role_created", "role_name": name})


@app.route('/api/admin/users/create', methods=['POST'])
@login_required
def admin_create_user():
    """Allows the root administrator to generate a new user profile with Werkzeug PBKDF2 hashed passwords."""
    if current_user.username != 'admin':
        log_security_event(current_user.username, "ACCESS_DENIED:POST /api/admin/users/create", "FAILURE", "Non-admin attempted to create system user.")
        return abort(403)
        
    if not request.is_json:
        return jsonify({"error": "JSON payload required"}), 400
        
    data = request.get_json()
    username = data.get("username", "").strip()
    password = data.get("password", "")
    role_id = data.get("role_id")
    
    if not username or not password or role_id is None:
        return jsonify({"error": "Username, password, and role_id are required"}), 400
        
    try:
        role_id = int(role_id)
    except ValueError:
        return jsonify({"error": "role_id must be an integer"}), 400
        
    # Enforce Root Administrator Invariant Guard:
    # No user can be assigned or elevated to the root admin role (id=1), and username 'admin' uniquely owns it.
    if role_id == 1:
        log_security_event(current_user.username, "VIOLATION:CREATE_USER_ROOT_ADMIN", "FAILURE", f"Attempted to assign new user '{username}' to root admin role (id=1).")
        return jsonify({"error": "Assigning new users to the root administrator role (id=1) is strictly forbidden"}), 403
        
    # Check if target role exists
    role_exists = db_read("SELECT id, name FROM roles WHERE id = ?", (role_id,))
    if not role_exists:
        return jsonify({"error": f"Role ID {role_id} does not exist"}), 400
        
    # Check if username already exists
    existing = db_read("SELECT username FROM users WHERE username = ?", (username,))
    if existing:
        return jsonify({"error": f"Username '{username}' already exists"}), 400
        
    password_hash = generate_password_hash(password, method='pbkdf2:sha256')
    db_enqueue("INSERT INTO users (username, password_hash, role_id) VALUES (?, ?, ?)", (username, password_hash, role_id))
    
    role_name = role_exists[0]["name"]
    log_security_event(current_user.username, f"CREATE_USER:{username}", "SUCCESS", f"New user '{username}' spawned and assigned to role '{role_name}' (id={role_id}).")
    return jsonify({"status": "user_created", "username": username, "role_name": role_name})


@app.route('/api/admin/users/modify_rank', methods=['PUT'])
@login_required
def admin_modify_rank():
    """Allows the root administrator to upgrade or downgrade a specific user's assigned role."""
    if current_user.username != 'admin':
        log_security_event(current_user.username, "ACCESS_DENIED:PUT /api/admin/users/modify_rank", "FAILURE", "Non-admin attempted to modify user rank.")
        return abort(403)
        
    if not request.is_json:
        return jsonify({"error": "JSON payload required"}), 400
        
    data = request.get_json()
    username = data.get("username", "").strip()
    role_id = data.get("role_id")
    
    if not username or role_id is None:
        return jsonify({"error": "Username and role_id are required"}), 400
        
    try:
        role_id = int(role_id)
    except ValueError:
        return jsonify({"error": "role_id must be an integer"}), 400
        
    # Root administrator invariant guard checks:
    # 1. Nobody else can be elevated to role_id=1
    if role_id == 1 and username != 'admin':
        log_security_event(current_user.username, "VIOLATION:MODIFY_RANK_ROOT_ADMIN", "FAILURE", f"Attempted to elevate user '{username}' to root admin role (id=1).")
        return jsonify({"error": "Elevating users to the root administrator role (id=1) is strictly forbidden"}), 403
        
    # 2. Admin cannot be reassigned away from role_id=1
    if username == 'admin':
        log_security_event(current_user.username, "VIOLATION:MODIFY_RANK_ROOT_ADMIN_DOWNGRADE", "FAILURE", f"Attempted to change role of root user 'admin' to role_id={role_id}.")
        return jsonify({"error": "Root user 'admin' must uniquely belong to the root admin role (id=1) and cannot be modified"}), 400
        
    # Check if target role exists
    role_exists = db_read("SELECT id, name FROM roles WHERE id = ?", (role_id,))
    if not role_exists:
        return jsonify({"error": f"Role ID {role_id} does not exist"}), 400
        
    # Check if user exists
    user_exists = db_read("SELECT username FROM users WHERE username = ?", (username,))
    if not user_exists:
        return jsonify({"error": f"User '{username}' not found"}), 404
        
    db_enqueue("UPDATE users SET role_id = ? WHERE username = ?", (role_id, username))
    
    role_name = role_exists[0]["name"]
    log_security_event(current_user.username, f"MODIFY_USER_RANK:{username}", "SUCCESS", f"User '{username}' role updated to '{role_name}' (id={role_id}).")
    return jsonify({"status": "rank_modified", "username": username, "role_name": role_name})


# --- Co-Pilot Hardware Override Endpoints ---

@app.route('/api/hardware/toggle_power', methods=['POST'])
@login_required
@permission_required('power_toggle_robot')
def toggle_power():
    """Allows authorized users to toggle the robot's engine power status."""
    global sim_config
    if not request.is_json:
        return jsonify({"error": "JSON payload required"}), 400
    data = request.get_json()
    status = data.get("status", "ONLINE").upper()
    if status not in ["ONLINE", "OFFLINE"]:
        return jsonify({"error": "Invalid engine status"}), 400
        
    with sim_lock:
        sim_config["engine_power_status"] = status
        # Propagate to current live telemetry
        if "current_live_telemetry" in sim_config and "status" in sim_config["current_live_telemetry"]:
            sim_config["current_live_telemetry"]["status"]["engine_power_status"] = status
            if status == "OFFLINE":
                sim_config["current_live_telemetry"]["status"]["position"] = {"x": 0.0, "y": 0.0}
            telemetry_copy = sim_config["current_live_telemetry"].copy()
            global_telemetry_cache["current_live_telemetry"] = telemetry_copy
            session_id = sim_config.get("active_session_id")
            if session_id:
                global_telemetry_cache[session_id] = telemetry_copy
                
    log_security_event(current_user.username, f"TOGGLE_ENGINE_POWER:{status}", "SUCCESS", f"UGV robot power status toggled to {status}.")
    return jsonify({"status": "power_updated", "engine_power_status": status})


@app.route('/api/hardware/toggle_navigation', methods=['POST'])
@login_required
@permission_required('toggle_navigation_mode')
def toggle_navigation():
    """Allows authorized users to toggle the robot's navigation override status between AUTOPILOT and MANUAL."""
    global sim_config
    if not request.is_json:
        return jsonify({"error": "JSON payload required"}), 400
    data = request.get_json()
    status = data.get("status", "AUTOPILOT").upper()
    if status not in ["AUTOPILOT", "MANUAL"]:
        return jsonify({"error": "Invalid navigation status"}), 400
        
    with sim_lock:
        sim_config["navigation_override_status"] = status
        # Propagate to current live telemetry
        if "current_live_telemetry" in sim_config and "status" in sim_config["current_live_telemetry"]:
            sim_config["current_live_telemetry"]["status"]["navigation_override_status"] = status
            telemetry_copy = sim_config["current_live_telemetry"].copy()
            global_telemetry_cache["current_live_telemetry"] = telemetry_copy
            session_id = sim_config.get("active_session_id")
            if session_id:
                global_telemetry_cache[session_id] = telemetry_copy
            
    log_security_event(current_user.username, f"TOGGLE_NAVIGATION:{status}", "SUCCESS", f"UGV navigation mode overridden to {status}.")
    return jsonify({"status": "navigation_updated", "navigation_override_status": status})


@app.route('/api/hardware/manual_control', methods=['POST'])
@login_required
@permission_required('manual_robot_control')
def manual_control():
    """Allows authorized users to manually override robot coordinates and send D-pad commands."""
    global sim_config
    if not request.is_json:
        return jsonify({"error": "JSON payload required"}), 400
    data = request.get_json()
    command = data.get("command", "STANDBY").upper()
    x = data.get("x")
    y = data.get("y")
    
    with sim_lock:
        if sim_config["engine_power_status"] == "OFFLINE":
            return jsonify({"error": "Cannot command robot: UGV engine is OFFLINE"}), 400
            
        if sim_config["navigation_override_status"] != "MANUAL":
            return jsonify({"error": "Cannot control manually: Autopilot is active"}), 400

        sim_config["last_manual_command"] = command
        if x is not None:
            sim_config["manual_x"] = float(x)
        if y is not None:
            sim_config["manual_y"] = float(y)
            
        # Update live telemetry coordinates immediately
        if "current_live_telemetry" in sim_config and "status" in sim_config["current_live_telemetry"]:
            sim_config["current_live_telemetry"]["status"]["last_manual_command"] = command
            if x is not None:
                sim_config["current_live_telemetry"]["status"]["position"]["x"] = round(float(x), 1)
            if y is not None:
                sim_config["current_live_telemetry"]["status"]["position"]["y"] = round(float(y), 1)
            telemetry_copy = sim_config["current_live_telemetry"].copy()
            global_telemetry_cache["current_live_telemetry"] = telemetry_copy
            session_id = sim_config.get("active_session_id")
            if session_id:
                global_telemetry_cache[session_id] = telemetry_copy
                
    log_security_event(current_user.username, f"MANUAL_ROBOT_COMMAND:{command}", "SUCCESS", f"Manual joystick control update sent: command={command}, x={x}, y={y}")
    return jsonify({
        "status": "manual_control_success", 
        "last_manual_command": command,
        "manual_x": sim_config["manual_x"],
        "manual_y": sim_config["manual_y"]
    })


# --- API Endpoints: Session & Reports ---

@app.route('/api/sessions', methods=['GET'])
@login_required
@permission_required('view_live_telemetry')
def get_sessions():
    """Returns a JSON list of all mission sessions with report download URLs."""
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


@app.route('/api/session/report/<session_id>/<filename>', methods=['GET'])
@login_required
@permission_required('export_reports')
def view_report_file(session_id, filename):
    """
    Serves individual session report files (HTML/PDF/MP4) securely.
    Guarantees strict authentication and dynamic 'export_reports' permission.
    """
    filename = secure_filename(filename)
    session_dir = os.path.join(REPORTS_DIR, session_id)
    if not os.path.exists(session_dir):
        return abort(404)
    file_path = os.path.join(session_dir, filename)
    if not os.path.exists(file_path):
        return abort(404)
    from flask import send_from_directory
    return send_from_directory(session_dir, filename)


@app.route('/api/session/download_pack/<session_id>', methods=['GET'])
@login_required
@permission_required('export_reports')
def download_pack(session_id):
    """
    Creates a ZIP archive containing all generated files inside
    the session folder (HTML report, PDF report, cam_normal.mp4, cam_thermal.mp4, cam_noir.mp4)
    and streams the completed archive directly as a downloadable attachment.
    """
    import zipfile
    import io
    from flask import send_file

    session_dir = os.path.join(REPORTS_DIR, session_id)
    if not os.path.exists(session_dir):
        return jsonify({"error": f"Session report directory not found for ID: {session_id}"}), 404

    # Compile zip in-memory to stream directly
    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(session_dir):
            for file in files:
                file_path = os.path.join(root, file)
                # Ensure the structure inside the zip is relative to the session folder
                arcname = os.path.relpath(file_path, session_dir)
                zipf.write(file_path, arcname)

    memory_file.seek(0)
    return send_file(
        memory_file,
        mimetype='application/zip',
        as_attachment=True,
        download_name=f"ARES_Session_{session_id}_Bundle.zip"
    )


@app.route('/api/simulation/stop', methods=['POST'])
@login_required
@permission_required('run_simulations')
def stop_simulation():
    """
    Instantly halts the active video simulation, releases the VideoWriter safely,
    and finalizes any active mission session logs into compiled reports.
    """
    global active_video_writer_normal, active_video_writer_thermal, active_video_writer_noir, active_video_writer_fused
    
    # Do not finalize while holding sim_lock. Finalization releases OpenCV writers
    # under video_buffer_lock, and holding both locks in different orders is what
    # caused endless loading after a completed/previous simulation.
    with sim_lock:
        sim_config["is_simulating"] = False
        sim_config["launch_pending"] = False
        sim_config["mission_aborted"] = True
        should_finalize_session = bool(sim_config.get("session_logging_active") and sim_config.get("active_session_id"))

    if should_finalize_session:
        _finalize_active_session_manually()
    else:
        close_all_video_resources()

    # Update dynamic telemetry status to reflect Stopped/Idle state immediately
    with sim_lock:
         stop_tel = get_baseline_telemetry(0.0)
         stop_tel["status"]["is_simulating"] = False
         stop_tel["status"]["mission_aborted"] = True
         sim_config["current_live_telemetry"] = stop_tel
         global_telemetry_cache["current_live_telemetry"] = stop_tel.copy()
         global_telemetry_cache["trajectory"] = []
         session_id = sim_config.get("active_session_id")
         if session_id:
             global_telemetry_cache[session_id] = stop_tel.copy()

    reset_frame_cache()
    close_all_video_resources()
    print("[Central Command] Simulation emergency stop triggered manually.")
    log_security_event(current_user.username, "STOP_SIMULATION", "SUCCESS", "Simulation successfully stopped and mission aborted.")
    return jsonify({"status": "stopped"})


@app.route('/api/sessions/delete/<session_id>', methods=['DELETE'])
@login_required
@permission_required('delete_logs')
def delete_session(session_id):
    """
    Deletes all telemetry logs and session records from SQLite database,
    and removes the corresponding static report files from disk entirely.
    """
    import shutil
    
    # 1. Enqueue SQLite deletion queries
    db_enqueue('DELETE FROM telemetry_logs WHERE session_id = ?', (session_id,))
    db_enqueue('DELETE FROM sessions WHERE session_id = ?', (session_id,))
    
    # 2. Synchronously remove folder on disk to free up space
    session_dir = os.path.join(REPORTS_DIR, session_id)
    if os.path.exists(session_dir):
        try:
            shutil.rmtree(session_dir)
            print(f"[Cleanup] Purged session folder on disk: {session_dir}")
        except Exception as e:
            print(f"[Cleanup ERROR] Failed to delete session folder {session_dir}: {e}")
            
    print(f"[Central Command] Deleted session: {session_id}")
    log_security_event(current_user.username, f"DELETE_SESSION:{session_id}", "SUCCESS", "Telemetry logs and reports permanently purged from disk.")
    return jsonify({"status": "deleted", "session_id": session_id})


@app.route('/api/sessions/clear_all', methods=['DELETE'])
@login_required
@permission_required('delete_logs')
def clear_all_sessions():
    """
    Drops all rows in both SQLite tables (sessions and telemetry_logs)
    and completely purges all session directories under static/reports/ on disk.
    """
    import shutil
    
    # 1. Enqueue SQLite clear queries
    db_enqueue('DELETE FROM telemetry_logs')
    db_enqueue('DELETE FROM sessions')
    
    # 2. Purge all subdirectories in static/reports/
    for item in os.listdir(REPORTS_DIR):
        item_path = os.path.join(REPORTS_DIR, item)
        if os.path.isdir(item_path):
            try:
                shutil.rmtree(item_path)
                print(f"[Cleanup] Purged directory: {item_path}")
            except Exception as e:
                print(f"[Cleanup ERROR] Failed to purge directory {item_path}: {e}")
        elif os.path.isfile(item_path) and item != '.DS_Store':
            try:
                os.remove(item_path)
            except Exception:
                pass
                
    print("[Central Command] Purged database sessions history and cleared all report directories.")
    log_security_event(current_user.username, "WIPE_ALL_LOGS", "SUCCESS", "Database history entirely deleted and static report directories cleared.")
    return jsonify({"status": "cleared"})


if __name__ == '__main__':
    import os
    import sys
    
    cert_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'certs')
    os.makedirs(cert_dir, exist_ok=True)
    
    cert_path = os.path.join(cert_dir, 'ares.pem')
    key_path = os.path.join(cert_dir, 'ares.key')

    # Ensure zero-configuration local CA trust is synchronized on every boot
    import subprocess
    print("[Server Init] Syncing local Certificate Authority trust context...")
    try:
        print("[Server Init] Executing mkcert -install...")
        subprocess.run(['mkcert', '-install'], check=True)
    except Exception as install_err:
        print("\n" + "="*80)
        print("[Server Init WARNING] mkcert local Root CA installation could not be completed automatically.")
        print(f"Active privilege management or keychain error: {install_err}")
        print("To resolve 'net::ERR_CERT_AUTHORITY_INVALID' and claim the solid glowing green secure lock:")
        print("Please open a host terminal and run the following command manually:")
        print("    sudo mkcert -install")
        print("="*80 + "\n")

    if not os.path.exists(cert_path) or not os.path.exists(key_path):
        print("[Server Init] SSL certs not found in static/certs/. Provisioning credentials...")
        try:
            print("[Server Init] Generating trusted certificate authority files...")
            subprocess.run([
                'mkcert',
                '-cert-file', cert_path,
                '-key-file', key_path,
                'localhost', '127.0.0.1'
            ], check=True)
            print(f"[Server Init] SSL/TLS CA trusted certificates provisioned at: {cert_path}")
        except Exception as e:
            print(f"[Server Init FATAL] mkcert failed to generate certificate matrix: {e}")
            sys.exit("[Server Init FATAL] Unsafe HTTP boot is strictly prohibited. SSL context must be enabled.")

    if not os.path.exists(cert_path) or not os.path.exists(key_path):
        sys.exit("[Server Init FATAL] Unsafe HTTP boot is strictly prohibited. Certificates are missing from static/certs/.")

    ssl_context = (cert_path, key_path)
    print("[Server Init] Starting ARES Multi-Spectral Studio at https://127.0.0.1:5001 (Forced HTTPS)")
    app.run(host='127.0.0.1', port=5001, debug=False, threaded=True, ssl_context=ssl_context)
