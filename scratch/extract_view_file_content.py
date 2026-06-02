import json
import os

log_path = "/Users/alial-khazali/.gemini/antigravity/brain/4fd3c875-79ac-4365-8d8a-f60f82d3bd92/.system_generated/logs/transcript.jsonl"

if os.path.exists(log_path):
    print("Found transcript.jsonl")
    with open(log_path, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                step = json.loads(line)
                if step.get("type") == "VIEW_FILE":
                    # Check if the tool calls or the filepath matches dashboard.html
                    # Usually the system stores the viewed file content in step["content"]
                    # Let's inspect step["content"] to see if it starts with HTML or dashboard patterns
                    content = step.get("content", "")
                    if "ARES | Rescue Operations Monitor" in content or "ARES OPERATIONS HUB" in content:
                        print(f"Found dashboard VIEW_FILE in step {step.get('step_index')}, size: {len(content)} bytes")
                        # Let's write this to recovered_dashboard.html
                        # Wait, we want to unescape if there's any escaping, but step["content"] is raw string, so it should be fine.
                        # Wait, sometimes there are line numbers prefixed (e.g. "123: <div>"). If so, we need to clean them up.
                        lines = content.split('\n')
                        cleaned_lines = []
                        has_line_numbers = False
                        
                        # Check if lines have line numbers like "123: <div"
                        for l in lines[:10]:
                            if ":" in l and l.split(":")[0].strip().isdigit():
                                has_line_numbers = True
                                break
                                
                        if has_line_numbers:
                            print("Detect line numbers in view_file. Cleaning up...")
                            for l in lines:
                                parts = l.split(":", 1)
                                if len(parts) == 2 and parts[0].strip().isdigit():
                                    # Remove the line number, colon, and the single space after the colon
                                    cleaned_lines.append(parts[1][1:] if parts[1].startswith(" ") else parts[1])
                                else:
                                    cleaned_lines.append(l)
                            cleaned_content = "\n".join(cleaned_lines)
                        else:
                            cleaned_content = content
                            
                        # Save it
                        with open(f"scratch/recovered_view_{step.get('step_index')}.html", "w", encoding="utf-8") as out:
                            out.write(cleaned_content)
                        print(f"Saved scratch/recovered_view_{step.get('step_index')}.html")
            except Exception as e:
                pass
else:
    print("Log not found")
