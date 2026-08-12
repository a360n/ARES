"""
ARES Non-Blocking Hardware Command Queue
Processes commands sent to ESP32-CAM sequentially to prevent socket congestion.
"""

import time
import queue
import threading
import urllib.request

hardware_command_queue = queue.Queue(maxsize=10)
_worker_thread = None


def hardware_command_worker():
    """Background worker thread processing hardware commands from hardware_command_queue."""
    while True:
        try:
            target_url = hardware_command_queue.get(block=True)
            try:
                req = urllib.request.Request(target_url, headers={'User-Agent': 'ARES-Mission-Control-Forwarder'})
                with urllib.request.urlopen(req, timeout=1.5) as response:
                    response.read()
            except Exception:
                pass
            hardware_command_queue.task_done()
        except Exception:
            time.sleep(0.01)


def enqueue_hardware_command(target_url):
    """Safely enqueues a command URL, dropping stale entries if full."""
    try:
        if hardware_command_queue.full():
            try:
                hardware_command_queue.get_nowait()
                hardware_command_queue.task_done()
            except queue.Empty:
                pass
        hardware_command_queue.put_nowait(target_url)
    except Exception:
        pass


def start_command_worker():
    global _worker_thread
    if _worker_thread is None or not _worker_thread.is_alive():
        _worker_thread = threading.Thread(target=hardware_command_worker, daemon=True)
        _worker_thread.start()
