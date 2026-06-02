import os

implicit_dir = "/Users/alial-khazali/.gemini/antigravity/implicit"
found = []

if os.path.exists(implicit_dir):
    for f in os.listdir(implicit_dir):
        if f.endswith(".pb"):
            fp = os.path.join(implicit_dir, f)
            try:
                with open(fp, 'rb') as file:
                    data = file.read()
                idx = data.find(b'Orbitron')
                if idx != -1:
                    print(f"FOUND 'Orbitron' in implicit {f} at index {idx}!")
                    found.append((f, idx))
            except Exception as e:
                pass
else:
    print("Implicit folder not found")
