"""Thumb disassembly and candidate string references, entirely offline."""
import json
import struct
import re
from pathlib import Path
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_LITTLE_ENDIAN
from capstone.arm import ARM_OP_MEM, ARM_REG_PC, ARM_OP_IMM, ARM_OP_REG

root = Path(__file__).resolve().parents[1]
data = (root / 'firmware/R19Z_1.00.18_241125.bin').read_bytes()
inv = json.loads((root / 'firmware/inventory.json').read_text(encoding='utf-8'))
image_base = 0x82C000
file_base = 0x50
payload_offset = file_base + 1024
keywords = ('disp_drv_timer', 'touch_close', 'GSENSOR_ID', 'lis3dh_spi', 'hub_hrm', 'm_ota_write', 'wrong signature')
targets = {image_base + s['offset'] - file_base: s for s in inv['strings'] if any(k in s['value'] for k in keywords)}
cs = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_LITTLE_ENDIAN)
cs.detail = True
cs.skipdata = True
symbols = {}
for line in (root / 'research/sdk-reference/ROM.lib').read_text().splitlines():
    m = re.fullmatch(r'0x([0-9a-fA-F]+) T (\S+)', line)
    if m:
        symbols[int(m.group(1), 16) & ~1] = m.group(2)
lines, refs, calls = [], [], []
for ins in cs.disasm(data[payload_offset:], image_base + 1024):
    annotation = ''
    if ins.id and ins.mnemonic in ('bl', 'blx', 'b.w') and ins.operands and ins.operands[0].type == ARM_OP_IMM:
        target = ins.operands[0].imm & ~1
        if target in symbols:
            annotation = ' ; ROM candidate: ' + symbols[target]
            calls.append({'instruction': hex(ins.address), 'target': hex(target), 'symbol': symbols[target]})
    lines.append(f'{ins.address:08x}  {ins.bytes.hex():12s} {ins.mnemonic:8s} {ins.op_str}{annotation}')
    if not ins.id:
        continue
    target = None
    if ins.mnemonic.startswith('adr'):
        imm = next((op.imm for op in ins.operands if op.type == ARM_OP_IMM), None)
        if imm is not None:
            # Capstone versions may express ADR as an offset or absolute address.
            target = imm if imm in targets else ((ins.address + 4) & ~3) + imm
    elif ins.mnemonic in ('addw', 'subw') and any(op.type == ARM_OP_REG and op.reg == ARM_REG_PC for op in ins.operands):
        imm = next((op.imm for op in ins.operands if op.type == ARM_OP_IMM), None)
        if imm is not None:
            target = ((ins.address + 4) & ~3) + (imm if ins.mnemonic == 'addw' else -imm)
    if target in targets:
        refs.append({'instruction': hex(ins.address), 'addressing': ins.mnemonic,
                     'string_address': hex(target), 'string': targets[target]['value'],
                     'line_index': len(lines)-1})
    if ins.mnemonic not in ('ldr', 'ldr.w'):
        continue
    for op in ins.operands:
        if op.type != ARM_OP_MEM or op.mem.base != ARM_REG_PC:
            continue
        literal = ((ins.address + 4) & ~3) + op.mem.disp
        off = literal - image_base + file_base
        if off < 0 or off + 4 > len(data):
            continue
        value = struct.unpack_from('<I', data, off)[0]
        if value in targets:
            refs.append({'instruction': hex(ins.address), 'literal_address': hex(literal),
                         'string_address': hex(value), 'string': targets[value]['value'],
                         'line_index': len(lines)-1})
(root / 'research/stock-thumb.txt').write_text('\n'.join(lines), encoding='utf-8')
(root / 'research/string-references.json').write_text(json.dumps(refs, indent=2), encoding='utf-8')
(root / 'research/rom-call-candidates.json').write_text(json.dumps(calls, indent=2), encoding='utf-8')
snippets = []
for ref in refs:
    i = ref['line_index']
    snippets.append(json.dumps(ref) + '\n' + '\n'.join(lines[max(0,i-16):i+20]))
(root / 'research/driver-candidates.txt').write_text('\n\n'.join(snippets), encoding='utf-8')
print('Decoded lines:', len(lines), 'candidate references:', len(refs))
print('ROM call candidates:', len(calls), 'unique symbols:', len({c['symbol'] for c in calls}))
print(json.dumps(refs, indent=2))
print('WARNING: linear disassembly includes data and does not establish function boundaries.')
