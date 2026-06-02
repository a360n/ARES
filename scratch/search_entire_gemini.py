import os

gemini_dir = "/Users/alial-khazali/.gemini"
matches = []

for root, dirs, files in os.walk(gemini_dir):
    for f in files:
        fp = os.path.join(root, f)
        # Skip very large log files or bin files if they slow it down, but let's check
        if os.path.getsize(fp) > 50 * 1024 * 1024:
            continue
        try:
            with open(fp, 'rb') as file:
                content = file.read()
            if b'Orbitron' in content:
                print(f"FOUND 'Orbitron' in: {fp} ({os.path.getsize(fp)} bytes)")
                matches.append(fp)
        except Exception as e:
            pass

print(f"Search complete. Found {len(matches)} files.")
