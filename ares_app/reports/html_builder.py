"""
ARES Tailwind HTML Report Builder
"""

import json
import numpy as np
from datetime import datetime, timezone


def build_html_report(session_id, session_data, telemetry_rows, output_path):
    """Generates a self-contained Tailwind-styled HTML safety audit report."""
    start_time = session_data.get("start_time", "N/A")
    end_time = session_data.get("end_time", "N/A")
    duration_sec = session_data.get("duration_seconds", 0.0)
    video_filename = session_data.get("video_filename", "N/A")
    mode = session_data.get("mode", "Autonomous")
    max_gas = session_data.get("max_gas_ppm", 0.0)
    max_temp = session_data.get("max_temperature", 0.0)
    fire_triggered = bool(session_data.get("fire_incident_triggered", 0))
    total_victims = session_data.get("total_victims_found", 0)

    parsed_telemetry = []
    cleaned_start = start_time.strip()
    if cleaned_start.endswith('Z'): cleaned_start = cleaned_start[:-1] + '+00:00'
    try: dt_start = datetime.fromisoformat(cleaned_start)
    except Exception: dt_start = datetime.now(timezone.utc)

    for i, row in enumerate(telemetry_rows):
        row_dict = dict(row)
        ts_val = row_dict.get("timestamp", "")
        cleaned_ts = ts_val.strip()
        if cleaned_ts.endswith('Z'): cleaned_ts = cleaned_ts[:-1] + '+00:00'
        try:
            dt_row = datetime.fromisoformat(cleaned_ts)
            elapsed = (dt_row - dt_start).total_seconds()
            if elapsed < 0: elapsed = 0.0
        except Exception: elapsed = i * 0.5

        row_dict["elapsed_seconds"] = round(elapsed, 2)
        pos_x = 200.0 + 120.0 * np.cos(elapsed * 0.22)
        pos_y = 200.0 + 120.0 * np.sin(elapsed * 0.22)
        row_dict["position_x"] = round(pos_x, 1)
        row_dict["position_y"] = round(pos_y, 1)

        mq9 = row_dict.get("gas_mq9", 0.0) or 0.0
        row_dict["gas_mq135"] = row_dict.get("gas_mq135") or round(mq9 * 2.5, 2)
        row_dict["gas_mics6814"] = round(mq9 / 72.0, 3)

        temp = row_dict.get("temperature", 0.0) or 0.0
        row_dict["humidity"] = round(max(5.0, 48.0 - (temp - 22.4) * 0.75), 2)
        row_dict["voltage"] = row_dict.get("voltage") or 12.4
        row_dict["gps_latitude"] = row_dict.get("gps_latitude") or 33.3128
        row_dict["gps_longitude"] = row_dict.get("gps_longitude") or 44.3615

        parsed_telemetry.append(row_dict)

    mission_telemetry_json = json.dumps(parsed_telemetry)

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

            flame_badge = '<span style="color:#f43f5e;font-weight:bold;">ACTIVE</span>' if row.get("flame_state") else '<span style="color:#10b981;">CLEAR</span>'
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
                    <td style="padding:10px 12px;font-family:monospace;font-size:11px;color:#64748b;">{row.get('ai_detections_summary', 'N/A')[:80]}</td>
                </tr>"""

    if not hazard_rows_html:
        hazard_rows_html = '<tr><td colspan="7" style="padding:24px;text-align:center;color:#64748b;font-size:13px;">No hazard events detected during this session.</td></tr>'

    fire_badge_html = '<span style="color:#f43f5e;font-weight:bold;">YES — FIRE INCIDENT CONFIRMED</span>' if fire_triggered else '<span style="color:#10b981;font-weight:bold;">NO FIRE INCIDENTS</span>'
    duration_display = f"{int(duration_sec) // 60}m {int(duration_sec) % 60}s" if duration_sec else "N/A"

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>ARES Safety Report — {session_id.upper()}</title>
    <script src="/static/js/tailwind.js"></script>
    <link href="/static/css/fonts_inter_orbitron.css" rel="stylesheet">
    <style>body {{ font-family: 'Inter', sans-serif; background: #0a0e1a; color: #e2e8f0; }} .font-hud {{ font-family: 'Orbitron', monospace; }}</style>
</head>
<body style="margin:0; padding:0; min-height:100vh;">
    <div style="background:linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #0f172a 100%); border-bottom:2px solid rgba(16,185,129,0.3); padding:32px 40px;">
        <div style="max-width:1100px; margin:0 auto;">
            <span class="font-hud" style="font-size:10px;color:#10b981;letter-spacing:4px;">CLASSIFIED // INTERNAL USE ONLY</span>
            <h1 class="font-hud" style="font-size:22px; font-weight:900; color:white; letter-spacing:3px; margin:4px 0;">ARES DISASTER RESPONSE AUDIT REPORT</h1>
            <p style="font-size:12px; color:#64748b; margin:0; font-family:monospace;">Session: {session_id.upper()} | Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
        </div>
    </div>
    <div style="max-width:1100px; margin:0 auto; padding:32px 40px;">
        <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(200px, 1fr)); gap:16px; margin-bottom:32px;">
            <div style="background:rgba(15,23,42,0.8); border:1px solid rgba(255,255,255,0.06); border-radius:8px; padding:20px;">
                <div class="font-hud" style="font-size:9px; color:#64748b;">SESSION ID</div>
                <div style="font-size:16px; font-weight:bold; color:#22d3ee;">{session_id.upper()}</div>
            </div>
            <div style="background:rgba(15,23,42,0.8); border:1px solid rgba(255,255,255,0.06); border-radius:8px; padding:20px;">
                <div class="font-hud" style="font-size:9px; color:#64748b;">DURATION</div>
                <div style="font-size:16px; font-weight:bold; color:#e2e8f0;">{duration_display}</div>
            </div>
            <div style="background:rgba(15,23,42,0.8); border:1px solid rgba(255,255,255,0.06); border-radius:8px; padding:20px;">
                <div class="font-hud" style="font-size:9px; color:#64748b;">MODE</div>
                <div style="font-size:16px; font-weight:bold; color:#e2e8f0;">{mode}</div>
            </div>
            <div style="background:rgba(15,23,42,0.8); border:1px solid rgba(255,255,255,0.06); border-radius:8px; padding:20px;">
                <div class="font-hud" style="font-size:9px; color:#64748b;">VIDEO FILE</div>
                <div style="font-size:13px; font-weight:bold; color:#e2e8f0;">{video_filename}</div>
            </div>
        </div>
        <h2 class="font-hud" style="font-size:13px; font-weight:700; color:#10b981; letter-spacing:3px; margin-bottom:16px;">HAZARD TIMELINE EVENTS</h2>
        <div style="overflow-x:auto; border-radius:8px; border:1px solid rgba(255,255,255,0.06);">
            <table style="width:100%; border-collapse:collapse; background:rgba(15,23,42,0.6);">
                <thead>
                    <tr style="background:rgba(15,23,42,0.95); border-bottom:2px solid rgba(16,185,129,0.2);">
                        <th style="padding:12px; text-align:left; font-size:9px; color:#64748b;" class="font-hud">TIMESTAMP</th>
                        <th style="padding:12px; text-align:left; font-size:9px; color:#64748b;" class="font-hud">GAS MQ-9</th>
                        <th style="padding:12px; text-align:left; font-size:9px; color:#64748b;" class="font-hud">TEMPERATURE</th>
                        <th style="padding:12px; text-align:left; font-size:9px; color:#64748b;" class="font-hud">FLAME</th>
                        <th style="padding:12px; text-align:left; font-size:9px; color:#64748b;" class="font-hud">LIDAR</th>
                        <th style="padding:12px; text-align:left; font-size:9px; color:#64748b;" class="font-hud">VICTIMS</th>
                        <th style="padding:12px; text-align:left; font-size:9px; color:#64748b;" class="font-hud">AI SUMMARY</th>
                    </tr>
                </thead>
                <tbody>{hazard_rows_html}</tbody>
            </table>
        </div>
    </div>
</body>
</html>"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
