import os

search_paths = [
    "/Users/alial-khazali/Library/Application Support/Code/User/History",
    "/Users/alial-khazali/Library/Application Support/Cursor/User/History",
    "/Users/alial-khazali/.cursor",
    "/Users/alial-khazali/.vscode"
]

found = []
for base_path in search_paths:
    if not os.path.exists(base_path):
        continue
    print(f"Scanning {base_path}...")
    for root, dirs, files in os.walk(base_path):
        for f in files:
            if "dashboard.html" in f or f.endswith(".html"):
                fp = os.path.join(root, f)
                try:
                    sz = os.path.getsize(fp)
                    if sz > 10000: # We only care about files larger than 10KB
                        # Read the first few lines to check if it's the ARES dashboard
                        with open(fp, 'rb') as file:
                            header = file.read(200)
                        if b'ARES' in header or b'Orbitron' in header:
                            print(f"MATCH: {fp} ({sz} bytes)")
                            found.append((fp, sz))
                except:
                    pass

if found:
    # Find the largest one
    best_fp, best_sz = max(found, key=lambda x: x[1])
    print(f"Restoring largest backup: {best_fp} ({best_sz} bytes)")
    with open("templates/dashboard.html", "rb") as src:
        content = src.read()
    with open(best_fp, "rb") as src:
        content = src.read()
    with open("templates/dashboard.html", "wb") as out:
        out.write(content)
    print("Successfully restored templates/dashboard.html!")
else:
    print("No backups found in user history.")
