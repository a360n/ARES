import os

brain_dir = "/Users/alial-khazali/.gemini/antigravity/brain"
found = []

for root, dirs, files in os.walk(brain_dir):
    for f in files:
        if "dashboard.html" in f:
            fp = os.path.join(root, f)
            found.append((fp, os.path.getsize(fp)))

print("Found dashboard.html in brain:")
for fp, sz in found:
    print(f"- {fp}: {sz} bytes")
