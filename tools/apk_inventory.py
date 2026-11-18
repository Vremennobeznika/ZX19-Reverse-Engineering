"""Static APK inventory; does not execute application code."""
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

p = Path(sys.argv[1])
data = p.read_bytes()
report = {'file': p.name, 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
with zipfile.ZipFile(p) as z:
    report['zip_integrity_error'] = z.testzip()
    report['files'] = z.namelist()
    hits = {}
    for name in z.namelist():
        if not (name.endswith('.dex') or name.startswith('assets/')):
            continue
        content = z.read(name)
        strings = re.findall(rb'[\x20-\x7e]{5,}', content)
        selected = set()
        for raw in strings:
            value = raw.decode('ascii')
            if re.search(r'R19Z|ZX19|firmware|oudmon|qcwireless|ota|dfu|https?://', value, re.I):
                # Avoid copying unrelated large assets into the report.
                if len(value) < 1000:
                    selected.add(value)
        if selected:
            hits[name] = sorted(selected)
    report['strings'] = hits
out = p.with_suffix('.inventory.json')
out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(out)
print('sha256:', report['sha256'])
print('entries:', len(report['files']), 'integrity:', report['zip_integrity_error'])
