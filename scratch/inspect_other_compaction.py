import json
import os

log_path = "/Users/alial-khazali/.gemini/antigravity/brain/5f6516cc-ab3d-4cb9-9bd3-6259dbbce026/.system_generated/logs/transcript.jsonl"

if os.path.exists(log_path):
    with open(log_path, 'r', encoding='utf-8') as f:
        for idx, line in enumerate(f):
            if idx == 35 or "CODE_ACTION" in line:
                try:
                    step = json.loads(line)
                    print(f"Step {step.get('step_index')}: type={step.get('type')}")
                    print(json.dumps(step, indent=2)[:3000])
                    print("="*80)
                except Exception as e:
                    print(f"Err: {e}")
else:
    print("Not found")
