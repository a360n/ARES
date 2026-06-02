import os

pb_path = "/Users/alial-khazali/.gemini/antigravity/conversations/4fd3c875-79ac-4365-8d8a-f60f82d3bd92.pb"

if os.path.exists(pb_path):
    with open(pb_path, 'rb') as f:
        header = f.read(100)
    print("Header bytes:")
    print(header)
    print("Hex representation:")
    print(header.hex())
else:
    print("Not found")
