"""Verify the stock display-to-application task chain without device access."""
import hashlib
import json
import struct
from pathlib import Path
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB

ROOT = Path(__file__).resolve().parents[1]
blob = (ROOT / 'firmware/R19Z_1.00.18_241125.bin').read_bytes()
digest = hashlib.sha256(blob).hexdigest()
if digest != '22f94070c13c157048b335e25af21e3421cc0a92c77c6b13f3c8088f88ddd7bd':
    raise SystemExit('Unknown firmware')


def read(address, count):
    offset = address - 0x82c000 + 80
    if offset < 80 or offset + count > len(blob):
        raise ValueError('Address outside image')
    return blob[offset:offset+count]


words = {0x83a9a8: 0x83a755, 0x83a9bc: 0x83a75b,
         0x83a9d8: 0x83a761, 0x83a9f4: 0x83a767,
         0x839094: 0x20c970, 0x83a5d8: 0x20c970,
         0x83a990: 0x20c964, 0x857768: 0x210644}
for address, expected in words.items():
    if struct.unpack('<I', read(address, 4))[0] != expected:
        raise SystemExit(f'Literal mismatch at {address:#x}')
cs = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
branches = {0x83a756: 0x838c98, 0x83a75c: 0x838c98,
            0x83a762: 0x838c98, 0x838ca4: 0x85763c,
            0x857646: 0x13236, 0x8576dc: 0x13210,
            0x8576f0: 0x83116e, 0x857706: 0x83a538,
            0x83a604: 0x83a93e, 0x83a68a: 0x8fc0}
decoded = []
for address, expected in branches.items():
    ins = next(cs.disasm(read(address, 4), address))
    if ins.mnemonic not in ('bl', 'b.w') or int(ins.op_str.lstrip('#'), 16) != expected:
        raise SystemExit(f'Branch mismatch at {address:#x}')
    decoded.append({'instruction': hex(address), 'target': hex(expected),
                    'bytes': ins.bytes.hex(), 'mnemonic': ins.mnemonic})
result = {'stock_sha256': digest, 'method': 'Exact-image literal and Thumb branch checks',
          'literal_checks': len(words), 'branch_checks': len(branches),
          'branches': decoded, 'display_state': '0x20c970',
          'application_task_state': '0x210644',
          'event_path': ['timer callback', '0x838c98: OR display event byte',
                         '0x85763c: OR task event word and give semaphore',
                         '0x8576dc: take semaphore', '0x857706: call display dispatcher'],
          'shared_task_ota_dispatch': '0x8576f0 -> 0x83116e',
          'display_dispatcher_controls_sleep': True,
          'replacement_hook_proven': False, 'hardware_execution_verified': False}
table = []
for index in range(210):
    address = 0x865b24 + index * 8
    page_id, callback = struct.unpack('<II', read(address, 8))
    if page_id != index or not callback & 1 or not (0x82c400 <= (callback & ~1) < 0x880f44):
        raise SystemExit(f'Unexpected display table entry {index}')
    table.append({'page_id': page_id, 'pointer_address': hex(address + 4),
                  'callback_thumb': hex(callback)})
for address, expected in {0x838fc4: 'e863', 0x8397fc: 'e06b',
                          0x8397fe: '8047', 0x839848: 'b4f9b800',
                          0x83984c: '2028'}.items():
    if read(address, len(expected)//2).hex() != expected:
        raise SystemExit(f'Strip dispatch instruction mismatch at {address:#x}')
result['page_table'] = table
result['render_callback_slot'] = '0x20c9ac (display state + 0x3c)'
result['render_callback_call'] = '0x8397fe'
result['strip_geometry'] = {'width': 172, 'rows': 10, 'count': 32,
                          'buffer_bytes': 3440, 'buffer_count': 2,
                          'first_buffer_address': hex(0x20c970 + 0x12e4),
                          'second_buffer_address': hex(0x20c970 + 0x12e4 + 3440)}
result['integration_caveat'] = 'Table and strip callback identified statically; page meanings, new code placement and state lifetime remain unverified.'
path = ROOT / 'research/display-dispatch-map.json'
path.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
print(f'PASS: {len(words)} literals, {len(branches)} branches; no device writes')
