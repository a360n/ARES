import json
import os

log_path = "/Users/alial-khazali/.gemini/antigravity/brain/5f6516cc-ab3d-4cb9-9bd3-6259dbbce026/.system_generated/logs/transcript.jsonl"

if os.path.exists(log_path):
    print("Found old transcript.jsonl")
    with open(log_path, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                step = json.loads(line)
                if step.get("step_index") == 22 and step.get("type") == "CODE_ACTION":
                    content = step.get("content", "")
                    print(f"Found step 22 content of size: {len(content)} bytes")
                    with open("scratch/recovered_diff_22.txt", "w", encoding="utf-8") as out:
                        out.write(content)
                    print("Wrote scratch/recovered_diff_22.txt successfully!")
            except Exception as e:
                pass
else:
    print("Not found")
