"""
ARES Decision Tree Environmental Risk Classification Engine
"""

from ares_app.config import (
    GAS_MQ9_HAZARD_THRESHOLD, GAS_MQ135_TOXIC_THRESHOLD,
    TEMP_CRITICAL_THRESHOLD, TEMP_WARNING_THRESHOLD,
    LIDAR_CRITICAL_DISTANCE
)


def classify_hazard_level(temp_c, gas_mq9, gas_mq135, lidar_cm, fire_detected):
    """
    Intelligent Environmental Risk Classification (Decision Tree Inference).
    Returns (hazard_grade, hazard_status, hazard_summary).
    """
    is_fire_event = fire_detected or (temp_c > TEMP_CRITICAL_THRESHOLD and gas_mq9 > GAS_MQ9_HAZARD_THRESHOLD)
    is_toxic_event = (gas_mq135 > GAS_MQ135_TOXIC_THRESHOLD or gas_mq9 > GAS_MQ9_HAZARD_THRESHOLD)

    if (is_fire_event or is_toxic_event) and (lidar_cm < LIDAR_CRITICAL_DISTANCE):
        grade = 4
        status = "CRITICAL FLASHOVER"
        summary = "🚨 INSTANT EVACUATION: STRUCTURAL FAILURE IMMINENT // ACTIVATING AUTOMATED EMERGENCY SAFETY RETURN PROTOCOLS"
    elif is_fire_event:
        grade = 3
        status = "FIRE CONTINGENCY"
        summary = "⚠️ HAZARD ALERT: CRITICAL FIRE CONTINGENCY TRIGGERED"
    elif is_toxic_event and temp_c <= TEMP_WARNING_THRESHOLD and not fire_detected:
        grade = 2
        status = "GAS LEAK WARNING"
        summary = "⚠️ GAS ALERT: UNIDENTIFIED INDUSTRIAL GAS DISPERSION LOCALIZED"
    else:
        grade = 1
        status = "NORMAL"
        summary = "Systems Nominal // Multi-Spectral Patrol Secure"

    return grade, status, summary
