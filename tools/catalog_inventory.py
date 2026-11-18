"""Describe a public catalog's routes without exposing embedded credentials."""
import re
from pathlib import Path

root = Path(__file__).resolve().parents[1]
s = (root / 'research/public-firmware-catalog.js').read_text(encoding='utf-8')
start = s.find('async authToken')
part = s[start:start + 4500]
def redact(match):
    value = match.group()[1:-1]
    if value.startswith('/') or value.startswith('https://'):
        return match.group()
    return '"[literal omitted]"'
part = re.sub(r'"(?:[^"\\]|\\.)*"|\x27(?:[^\x27\\]|\\.)*\x27', redact, part)
print(part)
print('R19Z literal present:', 'R19Z' in s)
