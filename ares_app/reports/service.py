"""
ARES Report Generation Service & ZIP Exporter
"""

import os
import time
import zipfile
import io
from ares_app.config import REPORTS_DIR
from ares_app.database import db_read
from ares_app.reports.html_builder import build_html_report
from ares_app.reports.pdf_builder import build_pdf_report


def generate_reports_deferred(session_id):
    """Background thread function. Reads session data and generates HTML + PDF reports."""
    time.sleep(2.0)
    try:
        sessions = db_read('SELECT * FROM sessions WHERE session_id = ?', (session_id,))
        if not sessions:
            print(f"[Report Generator ERROR] Session {session_id} not found.")
            return
        session_data = sessions[0]

        telemetry_rows = db_read(
            'SELECT * FROM telemetry_logs WHERE session_id = ? ORDER BY timestamp ASC',
            (session_id,)
        )

        report_dir = os.path.join(REPORTS_DIR, session_id)
        os.makedirs(report_dir, exist_ok=True)

        html_path = os.path.join(report_dir, f"{session_id}_report.html")
        pdf_path = os.path.join(report_dir, f"{session_id}_report.pdf")

        build_html_report(session_id, session_data, telemetry_rows, html_path)
        build_pdf_report(session_id, session_data, telemetry_rows, pdf_path)

        print(f"[Report Generator] Reports generated for session {session_id}: HTML + PDF")
    except Exception as e:
        print(f"[Report Generator ERROR] Failed for session {session_id}: {e}")


def create_session_zip_bundle(session_id):
    """Creates a ZIP archive BytesIO buffer containing all files in the session directory."""
    session_dir = os.path.join(REPORTS_DIR, session_id)
    if not os.path.exists(session_dir):
        return None

    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(session_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, session_dir)
                zipf.write(file_path, arcname)

    memory_file.seek(0)
    return memory_file
