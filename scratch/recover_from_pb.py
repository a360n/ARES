import os
import re

pb_path = "/Users/alial-khazali/.gemini/antigravity/conversations/4fd3c875-79ac-4365-8d8a-f60f82d3bd92.pb"

if os.path.exists(pb_path):
    print("Found conversation .pb file")
    with open(pb_path, 'rb') as f:
        data = f.read()
    
    print(f"Read {len(data)} bytes")
    
    # We want to find a block that matches a large HTML structure starting with a standard dashboard signature
    # Let's search for the Orbitron google font link or custom styling inside dashboard.html
    # "ARES | Rescue Operations Monitor" or similar signature
    matches = []
    
    # Simple regex to find HTML structures
    # We look for a pattern starting with <!DOCTYPE html> or <html lang="en" class="dark
    # and containing "Rescue Operations Monitor" and ending with </html>
    pattern = re.compile(b'<!DOCTYPE html>.*?</html>', re.DOTALL)
    for m in pattern.finditer(data):
        html_bytes = m.group(0)
        # Check if it has our dashboard's unique texts like Orbitron font or beep-sfx
        if b'ARES | Rescue Operations Monitor' in html_bytes:
            matches.append(html_bytes)
            print(f"Matched HTML of size: {len(html_bytes)} bytes")
            
    if matches:
        # Get the largest match
        largest_match = max(matches, key=len)
        print(f"Writing recovered dashboard of size {len(largest_match)} bytes")
        with open("templates/dashboard.html", "wb") as out:
            out.write(largest_match)
        print("Restored templates/dashboard.html successfully!")
    else:
        print("No matches found with exact pattern. Trying a wider search...")
        # Let's do a wider search for the Orbitron font link and the </html> tag
        pattern_wide = re.compile(b'<html lang="en" class="dark bg-slate-950 text-slate-100.*?</html>', re.DOTALL)
        for m in pattern_wide.finditer(data):
            html_bytes = m.group(0)
            if b'Orbitron' in html_bytes:
                matches.append(html_bytes)
                print(f"Matched Wide HTML of size: {len(html_bytes)} bytes")
        
        if matches:
            largest_match = max(matches, key=len)
            print(f"Writing wide recovered dashboard of size {len(largest_match)} bytes")
            # Prepend standard <!DOCTYPE html> if missing
            if not largest_match.startswith(b'<!DOCTYPE html>'):
                largest_match = b'<!DOCTYPE html>\n' + largest_match
            with open("templates/dashboard.html", "wb") as out:
                out.write(largest_match)
            print("Restored templates/dashboard.html successfully!")
        else:
            print("Failed to find HTML inside .pb file.")
else:
    print("Conversation pb file not found")
