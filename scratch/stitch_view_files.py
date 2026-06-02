import json
import os
import re

paths = [
    "/Users/alial-khazali/.gemini/antigravity/brain/4fd3c875-79ac-4365-8d8a-f60f82d3bd92/.system_generated/logs/transcript.jsonl",
    "/Users/alial-khazali/.gemini/antigravity/brain/5f6516cc-ab3d-4cb9-9bd3-6259dbbce026/.system_generated/logs/transcript.jsonl"
]

# We want to find the step(s) where templates/dashboard.html was read.
# When a tool call is made, the system returns a step of type 'VIEW_FILE' (or model response followed by tool output).
# In the JSONL, a tool output step of type VIEW_FILE or PLANNER_RESPONSE contains the content.
# Let's inspect all steps in transcript.jsonl.
for p in paths:
    if not os.path.exists(p):
        continue
    print(f"Analyzing {p}...")
    
    # We will track the line content of dashboard.html by their line numbers.
    # In VIEW_FILE content, each line is prefixed like "123: <original_line>".
    # We can gather all these lines, parse their line numbers, and put them in a dict: {line_num: line_content}
    dashboard_lines = {}
    
    with open(p, 'r', encoding='utf-8') as f:
        for idx, line in enumerate(f):
            try:
                step = json.loads(line)
                content = ""
                # Check tool calls/arguments to see if it's viewing dashboard.html
                is_dashboard = False
                
                # Check if this step is a VIEW_FILE step
                if step.get("type") == "VIEW_FILE" or step.get("type") == "CODE_ACTION":
                    content = step.get("content", "")
                    if "ARES | Rescue Operations Monitor" in content or "ARES OPERATIONS HUB" in content or "hud-spectral-mode" in content:
                        is_dashboard = True
                
                # Also check tool_calls in PLANNER_RESPONSE or other steps
                tool_calls = step.get("tool_calls", [])
                for tc in tool_calls:
                    args = tc.get("args", {})
                    if isinstance(args, str):
                        try: args = json.loads(args)
                        except: pass
                    tf = args.get("TargetFile") or args.get("AbsolutePath")
                    if tf and "dashboard.html" in tf:
                        is_dashboard = True
                
                # If it's a dashboard view, let's extract the lines
                if is_dashboard:
                    # Let's see if we can find lines with prefix "number: content"
                    lines = content.split('\n')
                    for l in lines:
                        parts = l.split(":", 1)
                        if len(parts) == 2 and parts[0].strip().isdigit():
                            line_num = int(parts[0].strip())
                            line_content = parts[1][1:] if parts[1].startswith(" ") else parts[1]
                            dashboard_lines[line_num] = line_content
            except Exception as e:
                pass
                
    if dashboard_lines:
        print(f"Gathered {len(dashboard_lines)} unique lines of dashboard.html from {p}!")
        # Let's print the min and max line numbers
        min_line = min(dashboard_lines.keys())
        max_line = max(dashboard_lines.keys())
        print(f"Line range: {min_line} to {max_line}")
        
        # If we have a substantial number of lines, let's write it out!
        # Write sequentially from 1 to max_line
        reconstructed = []
        missing_count = 0
        for i in range(1, max_line + 1):
            if i in dashboard_lines:
                reconstructed.append(dashboard_lines[i])
            else:
                # If a line is missing, we placeholder it or log it
                reconstructed.append(f"<!-- MISSING LINE {i} -->")
                missing_count += 1
                
        print(f"Missing lines: {missing_count}")
        out_fp = f"scratch/reconstructed_from_{os.path.basename(os.path.dirname(os.path.dirname(p)))}.html"
        with open(out_fp, "w", encoding="utf-8") as out:
            out.write("\n".join(reconstructed))
        print(f"Wrote {out_fp}")
