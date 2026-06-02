import os

history_paths = [
    "/Users/alial-khazali/Library/Application Support/Antigravity IDE/User/History",
    "/Users/alial-khazali/Library/Application Support/Antigravity/User/History",
    "/Users/alial-khazali/Library/Application Support/Code/User/History"
]

found = []

for base_path in history_paths:
    if os.path.exists(base_path):
        print(f"Scanning base: {base_path}")
        for root, dirs, files in os.walk(base_path):
            for f in files:
                fp = os.path.join(root, f)
                try:
                    with open(fp, 'rb') as file:
                        content = file.read()
                    if b'Orbitron' in content:
                        print(f"MATCH: {fp} ({len(content)} bytes)")
                        found.append((fp, len(content)))
                except Exception as e:
                    pass

print(f"Total matches: {len(found)}")
