import json
import os

log_path = "/Users/alial-khazali/.gemini/antigravity/brain/4fd3c875-79ac-4365-8d8a-f60f82d3bd92/.system_generated/logs/transcript.jsonl"

if os.path.exists(log_path):
    with open(log_path, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                step = json.loads(line)
                if step.get("step_index") == 90:
                    print(json.dumps(step, indent=2)[:2000])
            except Exception as e:
                pass
