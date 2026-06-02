import json
import os

transcripts = [
    "/Users/alial-khazali/.gemini/antigravity/brain/4fd3c875-79ac-4365-8d8a-f60f82d3bd92/.system_generated/logs/transcript.jsonl",
    "/Users/alial-khazali/.gemini/antigravity/brain/5f6516cc-ab3d-4cb9-9bd3-6259dbbce026/.system_generated/logs/transcript.jsonl"
]

best_content = ""
best_size = 0

for t_path in transcripts:
    if os.path.exists(t_path):
        print(f"Scanning {t_path}")
        with open(t_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    step = json.loads(line)
                    tool_calls = step.get("tool_calls", [])
                    for tc in tool_calls:
                        args = tc.get("args", {})
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except:
                                pass
                        
                        tf = args.get("TargetFile")
                        if tf and ("dashboard.html" in tf or "index.html" in tf):
                            # Try write_to_file or replace_file_content
                            content = args.get("CodeContent") or args.get("ReplacementContent")
                            if content and len(content) > best_size:
                                best_size = len(content)
                                best_content = content
                                print(f"Found code of size {best_size} in {t_path}")
                except Exception as e:
                    pass

if best_content:
    print(f"Successfully found best content of size {best_size}")
    with open("templates/dashboard.html", "w", encoding="utf-8") as out:
        out.write(best_content)
    print("Restored templates/dashboard.html successfully!")
else:
    print("Failed to find any content in transcripts.")
