"""Read-only extraction of R19Z startup literals; never creates a flash image."""
import hashlib
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / 'firmware/R19Z_1.00.18_241125.bin'
blob = path.read_bytes()
expected = '22f94070c13c157048b335e25af21e3421cc0a92c77c6b13f3c8088f88ddd7bd'
if hashlib.sha256(blob).hexdigest() != expected:
    raise SystemExit('Unknown image: refusing version-specific address interpretation')

def word(address):
    offset = address - 0x82c000 + 0x50
    return struct.unpack_from('<I', blob, offset)[0]

checks = {
    'entry_system_init_thumb': (0x82c404, 0x82c61f),
    'runtime_stack': (0x82c464, 0x203400),
    'pre_main_slot': (0x82c788, 0x200cc0),
    'upperstack_slot': (0x82c78c, 0x200cc4),
    'app_main_callback_thumb': (0x82c790, 0x85073f),
    'app_main_slot': (0x82c794, 0x200cc8),
    'app_data_base': (0x82c79c, 0x208500),
    'app_data_size': (0x82c7a0, 0x13f00),
    'zero_size': (0x82c714, 0x7700),
    'zero_base': (0x82c718, 0x209830),
}
result = {'image_sha256': expected, 'method': 'Static literals, verified against exact image; not device execution', 'literals': {}}
for name, (address, expected_value) in checks.items():
    actual = word(address)
    if actual != expected_value:
        raise SystemExit(f'{name}: {actual:#x} != {expected_value:#x}')
    result['literals'][name] = {'literal_address': hex(address), 'value': hex(actual)}
result['flash_image_created'] = False
result['hardware_boot_verified'] = False
output = ROOT / 'research/boot-map.json'
output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
print(f'{len(checks)} startup literals verified; {output}')
