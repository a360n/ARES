"""
ARES Forensic Security Audit Logger
"""

import os
from datetime import datetime, timezone
from ares_app.config import STATIC_DIR


def log_security_event(username, action, status="SUCCESS", details=""):
    """Logs critical administrative actions securely to static/security_audit.log with standard timestamping."""
    log_path = os.path.join(STATIC_DIR, 'security_audit.log')
    timestamp = datetime.now(timezone.utc).isoformat()
    log_line = f"[{timestamp}] USER={username} | ACTION={action} | STATUS={status} | DETAILS={details}\n"
    try:
        with open(log_path, 'a') as lf:
            lf.write(log_line)
    except Exception as e:
        print(f"[Forensic Log Error] Failed to write security event: {e}")
