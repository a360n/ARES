"""
ARES YOLOv8 Multi-Model AI Inference Manager
"""

import os
from ares_app.config import YOLO_PERSON_MODEL_PATH, YOLO_FIRE_MODEL_PATH

os.environ["ULTRALYTICS_OFFLINE"] = "True"
os.environ["YOLO_OFFLINE"] = "True"

YOLO_PERSON_MODEL = None
YOLO_FIRE_MODEL = None
PERSON_MODEL_LOADED = False
FIRE_MODEL_LOADED = False
yolo_error_msg = ""


def init_yolo_models():
    global YOLO_PERSON_MODEL, YOLO_FIRE_MODEL, PERSON_MODEL_LOADED, FIRE_MODEL_LOADED, yolo_error_msg
    try:
        from ultralytics import YOLO, settings
        try:
            settings.update({
                'sync': False, 'hub': False, 'clearml': False, 'comet': False,
                'dvc': False, 'mlflow': False, 'neptune': False, 'raytune': False,
                'tensorboard': False, 'wandb': False, 'vscode_msg': False, 'openvino_msg': False
            })
            print("[AI] Ultralytics settings configured for offline execution [OK]")
        except Exception as settings_err:
            print(f"[AI WARNING] Failed to configure Ultralytics settings: {settings_err}")

        # 1. Person Model
        try:
            if os.path.exists(YOLO_PERSON_MODEL_PATH):
                YOLO_PERSON_MODEL = YOLO(YOLO_PERSON_MODEL_PATH)
                PERSON_MODEL_LOADED = True
                print("[AI] YOLOv8-nano Person detector loaded successfully [READY]")
        except Exception as e:
            yolo_error_msg += f"Person Model: {str(e)}; "
            print(f"[AI WARNING] Person model failed to load: {e}")

        # 2. Fire Model
        try:
            if os.path.exists(YOLO_FIRE_MODEL_PATH):
                YOLO_FIRE_MODEL = YOLO(YOLO_FIRE_MODEL_PATH)
                FIRE_MODEL_LOADED = True
                print("[AI] Specialized YOLOv8 Fire detector loaded successfully [READY]")
        except Exception as e:
            yolo_error_msg += f"Fire Model: {str(e)}; "
            print(f"[AI WARNING] Fire model failed to load: {e}")

    except Exception as e:
        yolo_error_msg = str(e)
        print(f"[AI WARNING] YOLO package import/initialization failed: {e}")


# Initialize on import
init_yolo_models()
