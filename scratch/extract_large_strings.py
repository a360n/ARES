import os
import re

pb_path = "/Users/alial-khazali/.gemini/antigravity/conversations/4fd3c875-79ac-4365-8d8a-f60f82d3bd92.pb"

if os.path.exists(pb_path):
    print("Found .pb file")
    with open(pb_path, 'rb') as f:
        data = f.read()
    
    # We will search for any string chunk in the binary file.
    # In binary files, text strings are stored as contiguous printable ASCII/UTF-8 characters.
    # Let's find all contiguous blocks of printable characters (ASCII 32 to 126, plus newlines and tabs)
    # that are at least 5,000 bytes long.
    print(f"File size: {len(data)} bytes")
    
    # regex for printable ASCII characters plus common whitespace (\n, \r, \t)
    pattern = re.compile(b'[\\x20-\\x7E\\x0A\\x0D\\x09]{5000,}')
    
    matches = []
    for m in pattern.finditer(data):
        chunk = m.group(0)
        if b'Orbitron' in chunk and b'ARES | Rescue Operations Monitor' in chunk:
            matches.append(chunk)
            print(f"Found printable chunk of size: {len(chunk)} bytes")
            
    if matches:
        # Save the largest one
        largest = max(matches, key=len)
        print(f"Saving largest chunk ({len(largest)} bytes)")
        
        # Clean up any potential double-escaped characters (like \\n and \\" or \\')
        # Wait, if it is stored as a raw JSON string in protobuf, it will be escaped.
        # Let's try to unescape it if it's escaped.
        try:
            # If the string starts with a quote, let's decode it as JSON string
            decoded = largest.decode('utf-8', errors='ignore')
            if decoded.startswith('"'):
                # Unescape using json.loads
                # We wrap it in a JSON array to make it valid JSON
                decoded = json.loads("[" + decoded + "]")[0]
                print("Successfully decoded escaped JSON string!")
                largest = decoded.encode('utf-8')
        except Exception as json_err:
            print(f"JSON unescaping failed (using raw): {json_err}")
            
        with open("templates/dashboard.html", "wb") as out:
            out.write(largest)
        print("Restored templates/dashboard.html successfully!")
    else:
        print("No matching large chunks found.")
else:
    print("Not found")
