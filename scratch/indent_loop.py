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
    if "except Exception:" in line:
        # Skip the except block!
        i += 4 # Skip the except, if lock_acquired, video_buffer_lock.release(), raise lines
        break
    new_lines.append(line)
    i += 1

# Now we are at the start_proc_time block (around line 1283)
# Indent all lines by 4 spaces until the end of the loop iteration (around line 1807 / gc.collect)
while i < n:
    line = lines[i]
    if "if lock_acquired:" in line and "video_buffer_lock.release()" in lines[i+1]:
        # We reached the end of the loop!
        i += 3 # skip the old release check
        break
    
    # Indent the line by 4 spaces if it is not empty
    if line.strip():
        new_lines.append("    " + line)
    else:
        new_lines.append(line)
    i += 1

# Add the finally block
new_lines.append("            finally:\n")
new_lines.append("                if lock_acquired:\n")
new_lines.append("                    video_buffer_lock.release()\n")
new_lines.append("                    lock_acquired = False\n")

# Copy the rest of the file
while i < n:
    new_lines.append(lines[i])
    i += 1

# Write back to app.py
with open(app_path, "w") as f:
    f.writelines(new_lines)

print("Indentation and try...finally lock safety applied successfully!")
