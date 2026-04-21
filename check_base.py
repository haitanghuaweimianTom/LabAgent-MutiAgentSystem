import sys
path = r'E:\cherryClaw\math_modeling_multi_agent\backend\app\agents\base.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

print(f"File length: {len(content)}")

# Try to find sensitivity in multiple ways
print(f"Find 'sensitivity=': {content.find('sensitivity=')}")
print(f"Find 'sensitivity': {content.find('sensitivity')}")
print(f"Find '.4f')': {content.find('.4f\')')}")

# Check around index 18194
print(f"Content at 18180-18220: {repr(content[18180:18220])}")