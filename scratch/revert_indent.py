#!/usr/bin/env python3
import os

app_path = "/Users/alial-khazali/Documents/ARES/app.py"

with open(app_path, "r") as f:
    lines = f.readlines()

new_lines = []
i = 0
n = len(lines)

# Step 1: Copy everything up to lock_acquired = True (around line 1263)
while i < n:
    line = lines[i]
    new_lines.append(line)
    if "video_buffer_lock.acquire()" in line:
        # copy the next line: lock_acquired = True
        i += 1
        new_lines.append(lines[i])
        break
    i += 1

i += 1
# Expecting a try: block next
while i < n:
    line = lines[i]
    new_lines.append(line)
    if "try:" in line:
        break
    i += 1

i += 1
# Copy the double check inside the try block (lines 1266-1278)
while i < n:
    line = lines[i]
    if "finally:" in line:
        # We hit the misaligned finally block!
        break
    
    # Check if we are inside the indented section (line started with 4 extra spaces)
    if line.startswith("    "):
        # Remove 4 spaces of indentation
        new_lines.append(line[4:])
    else:
        new_lines.append(line)
    i += 1

# Skip the finally block we added
i += 4

# Copy the rest of the file
while i < n:
    new_lines.append(lines[i])
    i += 1

# Add back the except block we skipped
# Wait, let's inject it right after the try block's yield continue (around line 1278)
# Actually, let's just write back the cleaned lines.
with open(app_path, "w") as f:
    f.writelines(new_lines)

print("Reverted indentation successfully!")
