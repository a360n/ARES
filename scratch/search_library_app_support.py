import os

base_dir = "/Users/alial-khazali/Library/Application Support"
matches = []

print("Starting Library App Support search...")
for root, dirs, files in os.walk(base_dir):
    for f in files:
        if "dashboard.html" in f:
            fp = os.path.join(root, f)
            try:
                sz = os.path.getsize(fp)
                print(f"FOUND: {fp} ({sz} bytes)")
                matches.append((fp, sz))
            except:
                pass

print(f"Search complete. Found {len(matches)} files.")
