import os

conv_dir = "/Users/alial-khazali/.gemini/antigravity/conversations"
found = []

if os.path.exists(conv_dir):
    for f in os.listdir(conv_dir):
        if f.endswith(".pb"):
            fp = os.path.join(conv_dir, f)
            try:
                with open(fp, 'rb') as file:
                    data = file.read()
                idx = data.find(b'Orbitron')
                if idx != -1:
                    print(f"FOUND 'Orbitron' in {f} at index {idx}!")
                    found.append((f, idx))
            except Exception as e:
                pass
else:
    print("Conversations folder not found")
