"""
ARES FPDF2 Print-Ready PDF Report Builder
"""

from datetime import datetime, timezone


def build_pdf_report(session_id, session_data, telemetry_rows, output_path):
    """Generates a formal print-ready PDF safety audit report using fpdf2."""
    try:
        from fpdf import FPDF
    except ImportError:
        print("[Report Generator WARNING] fpdf2 not installed. Skipping PDF generation.")
        return

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

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
        if "YES" in value or (max_gas > 400 and "PPM" in value):
            pdf.set_text_color(244, 63, 94)
        elif total_victims > 0 and "Victims" in label:
            pdf.set_text_color(168, 85, 247)
        else:
            pdf.set_text_color(16, 185, 129)
        pdf.cell(0, 6, value, ln=True)
    pdf.ln(6)

    pdf.output(output_path)
