"""
ARES Server-Sent Events (SSE) Telemetry Streamer
"""

import time
import json
import gc
from flask import Response, request, abort
from flask_login import current_user
from ares_app.security.audit import log_security_event
from ares_app.telemetry.engine import startup_baseline


def generate_telemetry_sse(sim_config, sim_lock, global_telemetry_cache):
    """
    High-frequency SSE telemetry stream with connection scaling protection.
    Pushes synchronized coordinates & sensor readings to the frontend dashboard.
    """
    is_local = request.remote_addr in ['127.0.0.1', '::1']
    if not is_local:
        if not (current_user and current_user.is_authenticated):
            log_security_event("UNKNOWN", "ACCESS_DENIED:GET /api/telemetry/stream", "FAILURE", "Unauthenticated remote telemetry stream blocked.")
            return abort(401)
        if not current_user.has_permission('view_live_telemetry'):
            log_security_event(current_user.username, "ACCESS_DENIED:GET /api/telemetry/stream", "FAILURE", "User lacks required view_live_telemetry permission.")
            return abort(403)

    def sse_emitter():
        try:
            active_user = current_user.username if (current_user and current_user.is_authenticated) else "Anonymous_Node"
        except Exception:
            active_user = "Anonymous_Node"

        print(f"[+] SSE Connected // {active_user} tapped into global stream")
        heartbeat_counter = 40
        try:
            while True:
                with sim_lock:
                    is_simulating = sim_config.get("is_simulating", False)
                    launch_pending = sim_config.get("launch_pending", False)
                    mission_aborted = sim_config.get("mission_aborted", False)
                    realtime_active = (sim_config.get("dashboard_mode") == "realtime")

                if launch_pending:
                    pending_payload = startup_baseline.copy()
                    pending_payload["status"] = pending_payload.get("status", {}).copy()
                    pending_payload["status"]["is_simulating"] = False
                    pending_payload["status"]["launch_pending"] = True
                    pending_payload["status"]["mission_aborted"] = False
                    pending_payload["status"]["ai_status_banner"] = "Preparing mission stream // please wait"
                    yield f"data: {json.dumps(pending_payload)}\n\n"
                    time.sleep(0.05)
                    continue

                if (not is_simulating and not realtime_active) or mission_aborted:
                    if heartbeat_counter >= 40:
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
                        heartbeat_counter = 0
                    else:
                        time.sleep(0.05)
                        heartbeat_counter += 1
                    continue

                time.sleep(0.05)
                heartbeat_counter += 1
                if heartbeat_counter >= 20:
                    yield ": ping heartbeat\n\n"
                    heartbeat_counter = 0

                cached_data = global_telemetry_cache.get("current_live_telemetry")
                if not cached_data:
                    with sim_lock:
                        cached_data = sim_config.get("current_live_telemetry", {}).copy()

                if not cached_data:
                    cached_data = startup_baseline.copy()

                payload = json.dumps(cached_data)
                yield f"data: {payload}\n\n"
        except GeneratorExit:
            print(f"[-] SSE Disconnected // {active_user}")
        except Exception as e:
            print(f"[!] SSE Error // {active_user}: {e}")
        finally:
            gc.collect()
            print(f"[★] Memory Recycled // SSE resources collected for {active_user}")

    return Response(sse_emitter(), mimetype='text/event-stream')
