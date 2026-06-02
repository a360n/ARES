import os

base_dir = "/Users/alial-khazali"
matches = []

print("Starting size search for exactly 51109 bytes...")
for root, dirs, files in os.walk(base_dir):
    if any(p in root for p in ["/Library", "/.Trash", "/.system_generated"]):
        continue
    for f in files:
        fp = os.path.join(root, f)
        try:
            sz = os.path.getsize(fp)
            if sz == 51109:
                print(f"FOUND EXACT SIZE MATCH: {fp}")
                matches.append(fp)
        except:
            pass

print(f"Search complete. Found {len(matches)} matches.")
