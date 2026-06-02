import os

pb_path = "/Users/alial-khazali/.gemini/antigravity/conversations/4fd3c875-79ac-4365-8d8a-f60f82d3bd92.pb"

if os.path.exists(pb_path):
    with open(pb_path, 'rb') as f:
        data = f.read()
    
    idx = data.find(b'Orbitron')
    if idx != -1:
        print(f"Found 'Orbitron' at index {idx}")
        # Let's inspect the surrounding bytes.
        # We will try to scan backwards to find the start of the HTML (e.g. '<!DOCTYPE html>' or '<html')
        # and forwards to find '</html>'.
        start_idx = idx
        while start_idx > 0:
            # Look for typical start of HTML or the start of the string
            if data[start_idx:start_idx+15] == b'<!DOCTYPE html>' or data[start_idx:start_idx+5] == b'<html':
                break
            start_idx -= 1
            
        end_idx = idx
        while end_idx < len(data):
            if data[end_idx:end_idx+7] == b'</html>':
                end_idx += 7
                break
            end_idx += 1
            
        print(f"HTML bounds found: start={start_idx}, end={end_idx}, size={end_idx - start_idx} bytes")
        
        # If the size is reasonable, let's extract and write it!
        html_content = data[start_idx:end_idx]
        if len(html_content) > 5000:
            with open("templates/dashboard.html", "wb") as out:
                out.write(html_content)
            print("Restored templates/dashboard.html from surroundings!")
        else:
            # Let's just grab 60,000 bytes starting 2,000 bytes before 'Orbitron'
            start_fallback = max(0, idx - 2000)
            end_fallback = min(len(data), idx + 55000)
            fallback_content = data[start_fallback:end_fallback]
            
            # Let's see if we can find a standard start/end within it
            html_start = fallback_content.find(b'<!DOCTYPE html>')
            if html_start == -1:
                html_start = fallback_content.find(b'<html')
                
            html_end = fallback_content.find(b'</html>')
            if html_end != -1:
                html_end += 7
            else:
                html_end = len(fallback_content)
                
            if html_start != -1:
                final_content = fallback_content[html_start:html_end]
                with open("templates/dashboard.html", "wb") as out:
                    out.write(final_content)
                print(f"Restored fallback dashboard ({len(final_content)} bytes) successfully!")
            else:
                print("Could not locate HTML start in fallback range.")
    else:
        print("Orbitron was not found in the entire .pb file.")
else:
    print("Not found")
