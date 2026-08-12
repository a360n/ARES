"""
ARES UGV Navigation Mode Manager
"""

UGV_MODES = ["USER_CONTROL", "PLANNED_ROUTE", "AI_AUTONOMOUS"]
NAV_OVERRIDE_MODES = ["AUTOPILOT", "MANUAL"]
ENGINE_POWER_STATUSES = ["ONLINE", "OFFLINE"]


def set_ugv_navigation_mode(sim_config, sim_lock, mode):
    """Sets UGV navigation mode and updates override flags."""
    mode = mode.upper()
    if mode not in UGV_MODES:
        raise ValueError(f"Invalid UGV mode: {mode}")

    with sim_lock:
        sim_config["ugv_mode"] = mode
        if mode == "USER_CONTROL":
            sim_config["navigation_override_status"] = "MANUAL"
        else:
            sim_config["navigation_override_status"] = "AUTOPILOT"

        if "current_live_telemetry" in sim_config and "status" in sim_config["current_live_telemetry"]:
            sim_config["current_live_telemetry"]["status"]["ugv_mode"] = mode
            sim_config["current_live_telemetry"]["status"]["navigation_override_status"] = sim_config["navigation_override_status"]

    return mode
