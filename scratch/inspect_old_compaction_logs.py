import json
import os

log_path = "/Users/alial-khazali/.gemini/antigravity/brain/5f6516cc-ab3d-4cb9-9bd3-6259dbbce026/.system_generated/logs/transcript.jsonl"

if os.path.exists(log_path):
    print("Found old transcript.jsonl")
    with open(log_path, 'r', encoding='utf-8') as f:
        for idx, line in enumerate(f):
            try:
                step = json.loads(line)
                # print summary of steps containing dashboard.html
                if "dashboard.html" in line:
                    tc_names = []
                    if "tool_calls" in step:
                        tc_names = [tc.get("name") for tc in step["tool_calls"]]
                    print(f"Line {idx}, Step {step.get('step_index')}: type={step.get('type')}, tool_calls={tc_names}, len={len(line)} bytes")
            except Exception as e:
                pass
else:
    print("Not found")
