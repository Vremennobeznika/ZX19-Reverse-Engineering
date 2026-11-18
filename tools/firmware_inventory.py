"""Static firmware inventory; never connects to hardware."""
import hashlib
import json
import re
import struct
from pathlib import Path

root = Path(__file__).resolve().parents[1]
p = root / 'firmware/R19Z_1.00.18_241125.bin'
b = p.read_bytes()
strings = [{'offset': m.start(), 'value': m.group().decode('ascii')}
           for m in re.finditer(rb'[\x20-\x7e]{6,}', b)]
vectors = []
for off in range(0, len(b) - 64, 4):
    sp, reset = struct.unpack_from('<II', b, off)
    if 0x20000000 < sp <= 0x20040000 and sp % 8 == 0 and reset & 1 and 0x1000 <= reset < 0x100000:
        words = struct.unpack_from('<16I', b, off)
        handlers = [w for w in words[1:] if w]
        if len(handlers) >= 5 and all(w & 1 and w < 0x100000 for w in handlers):
            vectors.append({'file_offset': off, 'initial_sp': hex(sp), 'reset_handler': hex(reset),
                            'words': [hex(w) for w in words]})
report = {'file': p.name, 'size': len(b), 'sha256': hashlib.sha256(b).hexdigest(),
          'first_128_hex': b[:128].hex(), 'cortex_m_vector_candidates': vectors,
          'strings': strings}
out = root / 'firmware/inventory.json'
out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k != 'strings'}, indent=2))
print('Strings:', len(strings))
for entry in strings:
    if re.search(r'nrf|nordic|softdevice|s132|R19|52832|st77|cst|bma|hrs|vc31|sdk|assert|\.c$', entry['value'], re.I):
        print(hex(entry['offset']), entry['value'])
