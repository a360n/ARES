"""
ARES Dynamic Offline Local IP Scanner & Monitor
"""

import socket
import time
import threading


def get_current_local_ip():
    """Tries connecting to the robot AP or local interface to find the active IP address."""
    for target in [("192.168.4.1", 80), ("10.255.255.255", 1), ("8.8.8.8", 80)]:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.2)
            s.connect(target)
            ip = s.getsockname()[0]
            s.close()
            if ip and ip != "127.0.0.1":
                return ip
        except Exception:
            pass
    try:
        ip = socket.gethostbyname(socket.gethostname())
        if ip and ip != "127.0.0.1":
            return ip
    except Exception:
        pass
    return "127.0.0.1"


_last_monitored_ip = None


def network_monitor_loop():
    global _last_monitored_ip
    _last_monitored_ip = get_current_local_ip()
    while True:
        time.sleep(2.0)
        new_ip = get_current_local_ip()
        if new_ip != _last_monitored_ip:
            _last_monitored_ip = new_ip
            print(f"[Network Monitor] Interface changed! New Local Network: https://{new_ip}:5001")


def start_network_monitor():
    t = threading.Thread(target=network_monitor_loop, daemon=True)
    t.start()
