import json
import os

paths = [
    "/Users/alial-khazali/.gemini/antigravity/brain/4fd3c875-79ac-4365-8d8a-f60f82d3bd92/.system_generated/logs/transcript.jsonl",
    "/Users/alial-khazali/.gemini/antigravity/brain/5f6516cc-ab3d-4cb9-9bd3-6259dbbce026/.system_generated/logs/transcript.jsonl"
]

for p in paths:
    if os.path.exists(p):
        print(f"Scanning {p}")
        with open(p, 'r', encoding='utf-8') as f:
            for idx, line in enumerate(f):
                if 'Orbitron' in line:
                    # Parse as json
                    try:
                        step = json.loads(line)
                        print(f"Line {idx}, Step {step.get('step_index')}: type={step.get('type')}, length={len(line)} bytes")
                        # Print keys
                        print(f"Keys: {list(step.keys())}")
                    except Exception as e:
                        print(f"Line {idx}: raw length={len(line)} bytes, err={e}")
