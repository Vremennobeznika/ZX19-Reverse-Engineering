"""Version-specific static OTA evidence. No BLE imports, no image modification."""
import hashlib
import json
import struct
import uuid
from pathlib import Path
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_LITTLE_ENDIAN

ROOT = Path(__file__).resolve().parents[1]
data = (ROOT / 'firmware/R19Z_1.00.18_241125.bin').read_bytes()
assert hashlib.sha256(data).hexdigest() == '22f94070c13c157048b335e25af21e3421cc0a92c77c6b13f3c8088f88ddd7bd'

def at(address, length):
    offset = address - 0x82c000 + 0x50
    assert 0 <= offset <= len(data) - length
    return data[offset:offset + length]

def word(address):
    return struct.unpack('<I', at(address, 4))[0]

decoder = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_LITTLE_ENDIAN)
commands = {}
for command, displacement in enumerate(at(0x8311ac, 6)):
    if command == 0:
        continue
    route = 0x8311ac + 2 * displacement
    instructions = list(decoder.disasm(at(route, 6), route))
    call = next(i for i in instructions if i.mnemonic == 'bl')
    commands[str(command)] = {'route': hex(route), 'handler': call.op_str.replace('#', '')}
assert [commands[str(i)]['handler'] for i in range(1, 6)] == [
    '0x8315dc', '0x8315ee', '0x831674', '0x83178a', '0x8317c6']
staging = word(0x831884)
bound = word(0x831880)
assert staging == 0x88f000 and bound == 0x5c851
assert uuid.UUID('de5bf728-d711-4e47-af26-65e3012a5dc7').bytes[::-1] == at(0x8620f8, 16)
# 0x831614 SUB len,0x2800; 0x831618 CMP bound; 0x83161a BLO accept.
assert at(0x831614, 8).hex() == 'a1f52054ac4204d3', 'Length-guard instructions changed'
minimum = 0x2800
maximum = minimum + bound - 1
report = {'method': 'static analysis of exact stock image; hardware behavior not tested',
          'gatt_write_callback': '0x82ce14', 'bc_frame_assembler': '0x8303de',
          'crc_dispatch': '0x8302b8', 'queued_command_dispatch': '0x83116e',
          'commands': commands, 'staging_base': hex(staging),
          'length_guard_minimum_inclusive': minimum,
          'length_guard_maximum_inclusive': maximum,
          'length_guard_headroom_over_current_file': maximum - len(data),
          'important': 'Accepted file-length bound does NOT prove free executable space or recovery.',
          'device_writes': False}
path = ROOT / 'research/qc-ota-map.json'
path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print(json.dumps(report, indent=2))
