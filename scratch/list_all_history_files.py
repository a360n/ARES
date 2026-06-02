import os

history_paths = [
    "/Users/alial-khazali/Library/Application Support/Antigravity IDE/User/History",
    "/Users/alial-khazali/Library/Application Support/Antigravity/User/History",
    "/Users/alial-khazali/Library/Application Support/Code/User/History"
]

all_files = []

for base_path in history_paths:
    if os.path.exists(base_path):
        print(f"Scanning base: {base_path}")
        for root, dirs, files in os.walk(base_path):
            for f in files:
                fp = os.path.join(root, f)
                try:
                    all_files.append((fp, os.path.getsize(fp)))
                except:
                    pass

print(f"Total files in IDE history: {len(all_files)}")
# Print the 30 largest files in the history to see what they are
all_files.sort(key=lambda x: x[1], reverse=True)
for fp, sz in all_files[:30]:
    print(f"- {fp}: {sz} bytes")
