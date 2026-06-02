import json
import os

brain_dir = "/Users/alial-khazali/.gemini/antigravity/brain"
dashboard_lines = {}

# Scan all subdirectories in brain_dir for transcript.jsonl
print("Scanning all historical conversation transcripts...")
for root, dirs, files in os.walk(brain_dir):
    if "logs" in root and "transcript.jsonl" in files:
        t_path = os.path.join(root, "transcript.jsonl")
        try:
            with open(t_path, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        step = json.loads(line)
                        content = ""
                        is_dashboard = False
                        
                        if step.get("type") == "VIEW_FILE" or step.get("type") == "CODE_ACTION":
                            content = step.get("content", "")
                            # Check if the content is part of dashboard.html
                            if "ARES | Rescue Operations Monitor" in content or "ARES OPERATIONS HUB" in content or "hud-spectral-mode" in content:
                                is_dashboard = True
                                
                        tool_calls = step.get("tool_calls", [])
                        for tc in tool_calls:
                            args = tc.get("args", {})
                            if isinstance(args, str):
                                try: args = json.loads(args)
                                except: pass
                            tf = args.get("TargetFile") or args.get("AbsolutePath")
                            if tf and "dashboard.html" in tf:
                                is_dashboard = True
                                
                        if is_dashboard:
                            # Extract prefixed lines
                            lines = content.split('\n')
                            for l in lines:
                                parts = l.split(":", 1)
                                if len(parts) == 2 and parts[0].strip().isdigit():
                                    line_num = int(parts[0].strip())
                                    line_content = parts[1][1:] if parts[1].startswith(" ") else parts[1]
                                    
                                    # Save to global dictionary
                                    # If the line already exists, keep the longer one or first one,
                                    # but they should be identical.
                                    dashboard_lines[line_num] = line_content
                    except Exception as e:
                        pass
        except Exception as e:
            print(f"Error reading {t_path}: {e}")

if dashboard_lines:
    print(f"SUCCESS! Gathered a total of {len(dashboard_lines)} unique lines of dashboard.html globally!")
    min_line = min(dashboard_lines.keys())
    max_line = max(dashboard_lines.keys())
    print(f"Global line range: {min_line} to {max_line}")
    
    # Reconstruct the file sequentially
    reconstructed = []
    missing_count = 0
    for i in range(1, max_line + 1):
        if i in dashboard_lines:
            reconstructed.append(dashboard_lines[i])
        else:
            reconstructed.append(f"<!-- MISSING LINE {i} -->")
            missing_count += 1
            
    print(f"Missing lines globally: {missing_count}")
    with open("templates/dashboard.html", "w", encoding="utf-8") as out:
        out.write("\n".join(reconstructed))
    print("Restored templates/dashboard.html successfully!")
else:
    print("Failed to find any dashboard lines in any conversation history.")
