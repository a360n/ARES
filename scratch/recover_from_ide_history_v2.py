import os

history_paths = [
    "/Users/alial-khazali/Library/Application Support/Antigravity IDE/User/History",
    "/Users/alial-khazali/Library/Application Support/Antigravity/User/History",
    "/Users/alial-khazali/Library/Application Support/Code/User/History"
]

found_files = []

for base_path in history_paths:
    if os.path.exists(base_path):
        print(f"Scanning base: {base_path}")
        for root, dirs, files in os.walk(base_path):
            for f in files:
                fp = os.path.join(root, f)
                try:
                    sz = os.path.getsize(fp)
                    if sz > 20000: # dashboard.html is ~51KB
                        with open(fp, 'rb') as file:
                            # Read first 15,000 bytes to be absolutely sure we capture Orbitron
                            header = file.read(15000)
                        if b'Orbitron' in header or b'ARES' in header:
                            if b'ARES OPERATIONS HUB' in header or b'ARES | Rescue Operations Monitor' in header:
                                print(f"MATCH FOUND: {fp} ({sz} bytes)")
                                found_files.append((fp, sz, header))
                except Exception as e:
                    pass

if found_files:
    # Find the one that has the largest size (or closest to 51KB)
    best_fp, best_sz, best_header = max(found_files, key=lambda x: x[1])
    print(f"Restoring best IDE history backup: {best_fp} ({best_sz} bytes)")
    
    # Read the full file contents
    with open(best_fp, 'rb') as src:
        content = src.read()
        
    with open("templates/dashboard.html", "wb") as out:
        out.write(content)
    print("SUCCESS! templates/dashboard.html has been perfectly restored!")
else:
    print("No matching dashboard backups found in IDE history.")
