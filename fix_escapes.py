#!/usr/bin/env python3
"""Fix escaped newline issues in generated Phase 15.6 files."""
import glob, re

for f in sorted(glob.glob("memoryx/context_budget/*.py")):
    with open(f, "r", encoding="utf-8") as fh:
        c = fh.read()
    
    orig = c
    
    # Fix 1: source = "\\n" + ".join(clean)" -> source = "\\n".join(clean)
    c = re.sub(r'source = "\\\\n" \+ "\.join\(', 'source = "\\n".join(', c)
    
    # Fix 2: text = "\\n" + ".join(lines)" -> text = "\\n".join(lines)  
    c = re.sub(r'text = "\\\\n" \+ "\.join\(', 'text = "\\n".join(', c)
    
    # Fix 3: Any = "\\n" + ".join(...) -> = "\\n".join(...)
    c = re.sub(r'= "\\\\n" \+ "\.join\(', '= "\\n".join(', c)
    
    # Fix 4: literal newline inside string like "actual_newline.join" 
    # This happens when the original \\n in the template became real newlines
    # Pattern: something = " literal_newline ".join(...
    c = re.sub(r'(=\s*")\n("[^"]*\.join\()', lambda m: m.group(1) + '\\n' + m.group(2), c)
    
    if c != orig:
        with open(f, "w", encoding="utf-8") as fh:
            fh.write(c)
        print(f"FIXED {f}")

print("Done")
