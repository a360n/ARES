#!/usr/bin/env python3
"""
ARES Database Module
Provides thread-safe SQLite operations using single-writer WAL queue architecture.
"""

import sqlite3
import queue
import threading
from werkzeug.security import generate_password_hash
from ares_app.config import DB_PATH, REPORTS_DIR

_db_queue = queue.Queue()
_db_writer_thread = None


def init_database():
    """Creates SQLite database tables if they do not exist and seeds initial roles and users."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    # Check for legacy users table
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
            gas_mq135             REAL,
            temperature           REAL,
            flame_state           INTEGER,
            lidar_distance        REAL,
            gps_latitude          REAL,
            gps_longitude         REAL,
            voltage               REAL,
            ai_detections_summary TEXT,
            unconscious_victims   INTEGER DEFAULT 0,
            FOREIGN KEY (session_id) REFERENCES sessions(session_id)
        )
    ''')

    # Migration check for newer columns
    cursor.execute("PRAGMA table_info(telemetry_logs)")
    existing_cols = [col[1] for col in cursor.fetchall()]
    new_cols = {
        "gas_mq135": "REAL",
        "gps_latitude": "REAL",
        "gps_longitude": "REAL",
        "voltage": "REAL"
    }
    for col_name, col_type in new_cols.items():
        if col_name not in existing_cols:
            cursor.execute(f"ALTER TABLE telemetry_logs ADD COLUMN {col_name} {col_type}")
            print(f"[DB MIGRATION] Added column {col_name} to telemetry_logs table.")

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
        CREATE TABLE IF NOT EXISTS ugv_routes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            steps TEXT NOT NULL,
            created_at TEXT NOT NULL
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

    # Seed roles
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

    # Seed users
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

    # Ensure root admin points to role_id=1
    cursor.execute("SELECT role_id FROM users WHERE username = 'admin'")
    admin_row = cursor.fetchone()
    if admin_row and admin_row[0] != 1:
        print("[Database Guard Warning] Correcting admin role alignment...")
        cursor.execute("UPDATE users SET role_id = 1 WHERE username = 'admin'")
        conn.commit()

    conn.commit()
    conn.close()
    print(f"[DB] SQLite database initialized successfully // {DB_PATH}")


def _db_writer_loop():
    """Single writer thread loop draining _db_queue."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    while True:
        try:
            op = _db_queue.get(timeout=2.0)
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
    """Enqueues a write query to the dedicated SQLite thread queue."""
    _db_queue.put((sql, params))


def db_read(sql, params=()):
    """Executes a thread-safe read query and returns a list of dictionaries."""
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def start_db_service():
    """Initializes DB and starts the writer thread."""
    global _db_writer_thread
    init_database()
    if _db_writer_thread is None or not _db_writer_thread.is_alive():
        _db_writer_thread = threading.Thread(target=_db_writer_loop, daemon=True)
        _db_writer_thread.start()
