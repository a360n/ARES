import os

pb_path = "/Users/alial-khazali/.gemini/antigravity/conversations/4fd3c875-79ac-4365-8d8a-f60f82d3bd92.pb"

if os.path.exists(pb_path):
    with open(pb_path, 'rb') as f:
        data = f.read()
    
    # Search for occurrences of b'Rescue Operations Monitor'
    query = b'Rescue Operations Monitor'
    idx = 0
    while True:
        idx = data.find(query, idx)
        if idx == -1:
            break
        print(f"Found '{query.decode()}' at index {idx}")
        # Print 200 bytes around it
        start = max(0, idx - 100)
        end = min(len(data), idx + 200)
        print(data[start:end])
        print("-" * 50)
        idx += len(query)
else:
    print("Not found")
