import os

base_dir = "/Users/alial-khazali"
matches = []

print("Starting global search...")
for root, dirs, files in os.walk(base_dir):
    # Skip library and system folders that are too slow or operations not permitted
    if any(p in root for p in ["/Library", "/.Trash", "/.system_generated"]):
        continue
    for f in files:
        if f == "dashboard.html":
            fp = os.path.join(root, f)
            try:
                sz = os.path.getsize(fp)
                print(f"FOUND: {fp} ({sz} bytes)")
                matches.append((fp, sz))
            except:
                pass

print(f"Global search complete. Found {len(matches)} files.")
