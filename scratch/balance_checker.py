with open("/Users/alial-khazali/Documents/ARES/templates/dashboard.html", "r", encoding="utf-8") as f:
    lines = f.readlines()

in_main_script = False
stack = []

in_string = False
string_char = None

for idx, line in enumerate(lines):
    line_num = idx + 1
    
    if "<script>" in line and line_num > 500:
        in_main_script = True
        continue
    if "</script>" in line and in_main_script:
        in_main_script = False
        continue
        
    if not in_main_script:
        continue
    
    i = 0
    while i < len(line):
        char = line[i]
        
        # Simple comment handling
        if not in_string and i + 1 < len(line) and line[i:i+2] == "//":
            break
            
        if char in ["'", '"', '`']:
            if not in_string:
                in_string = True
                string_char = char
            elif string_char == char:
                # Check escape
                escaped = False
                k = i - 1
                while k >= 0 and line[k] == "\\":
                    escaped = not escaped
                    k -= 1
                if not escaped:
                    in_string = False
                    string_char = None
                    
        if not in_string:
            if char in ["{", "(", "["]:
                stack.append((char, line_num, i + 1))
                if line_num >= 1180:
                    print(f"PUSH: {char} at line {line_num}:{i+1}")
            elif char in ["}", ")", "]"]:
                if not stack:
                    print(f"UNMATCHED CLOSING: {char} at line {line_num}:{i+1}")
                else:
                    top_char, top_line, top_col = stack.pop()
                    if line_num >= 1180 or top_line >= 1180:
                        print(f"POP & MATCH: popped {top_char} (from {top_line}) with {char} at line {line_num}:{i+1}")
                    if (char == "}" and top_char != "{") or \
                       (char == ")" and top_char != "(") or \
                       (char == "]" and top_char != "["):
                        print(f"  MISMATCH DETECTED: {top_char} from {top_line} with {char} at {line_num}:{i+1}")
        i += 1
