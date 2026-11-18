"""Extract a straight-line LCD init candidate. Does not execute or transmit commands."""
import json
from pathlib import Path
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
from capstone.arm import ARM_OP_REG, ARM_OP_IMM, ARM_REG_R0

root = Path(__file__).resolve().parents[1]
b = (root / 'firmware/R19Z_1.00.18_241125.bin').read_bytes()
start, end = 0x83AB7A, 0x83AD5A
offset = start - 0x82C000 + 0x50
cs = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
cs.detail = True
ops = []
r0 = None
for ins in cs.disasm(b[offset:offset+end-start], start):
    if ins.mnemonic in ('movs', 'mov', 'movw') and len(ins.operands) == 2:
        left, right = ins.operands
        if left.type == ARM_OP_REG and left.reg == ARM_REG_R0 and right.type == ARM_OP_IMM:
            r0 = right.imm
    if ins.mnemonic in ('bl', 'b.w') and ins.operands[0].type == ARM_OP_IMM:
        target = ins.operands[0].imm
        kind = {0x208560: 'command', 0x20857E: 'data', 0x83AA20: 'delay_candidate_ms'}.get(target)
        if not kind or r0 is None:
            raise ValueError(f'Unresolved init operation at {ins.address:x}')
        ops.append({'address': hex(ins.address), 'kind': kind, 'value': r0})
        r0 = None
commands = []
for op in ops:
    if op['kind'] == 'command':
        commands.append({'command': hex(op['value']), 'data': []})
    elif op['kind'] == 'data':
        commands[-1]['data'].append(op['value'])
windows = {}
for command in commands:
    if command['command'] in ('0x2a', '0x2b') and len(command['data']) == 4:
        x = command['data']
        lo, hi = (x[0] << 8) | x[1], (x[2] << 8) | x[3]
        windows[command['command']] = {'start': lo, 'end': hi, 'span': hi-lo+1}
report = {'function_candidate': hex(start), 'commands': commands, 'windows': windows,
          'operations': ops, 'note': 'Static candidate, ST7789-compatible command set. Panel ID and live hardware operation unverified.'}
(root / 'research/lcd-init-candidate.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps({'windows': windows, 'operations': len(ops), 'command_count': len(commands)}, indent=2))
