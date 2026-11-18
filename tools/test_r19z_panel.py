"""Execute the board adapter on Cortex-M4 with modeled ROM, bus and clock."""
import json
import os
from pathlib import Path
import struct
import subprocess
import unicorn as U
from unicorn import arm_const as A

root = Path(__file__).resolve().parents[1]
build = root / 'build'
build.mkdir(exist_ok=True)
image = build / 'r19z-panel-test.elf'
zig = root / 'tools/python/Lib/site-packages/ziglang/zig.exe'
subprocess.run([str(zig), 'cc', '-target', 'thumb-freestanding-eabi', '-mcpu=cortex_m4',
                '-Os', '-Wall', '-Wextra', '-Werror', '-ffreestanding', '-nostdlib',
                '-Wl,-T,' + str(root / 'tests/emulator.ld'), '-Wl,-e,r19z_panel_start_platform',
                str(root / 'src/r19z_panel.c'), str(root / 'src/watch_lcd.c'),
                '-o', str(image)], check=True,
               env=dict(os.environ, ZIG_GLOBAL_CACHE_DIR=str(build / 'zig-cache')))
elf = image.read_bytes()
entry = struct.unpack_from('<I', elf, 24)[0]
offset = struct.unpack_from('<I', elf, 32)[0]
stride, count = struct.unpack_from('<HH', elf, 46)
stock = json.loads((root / 'research/lcd-init-candidate.json').read_text())
expected = [(op['kind'], op['value']) for op in stock['operations']]

def run(stall_at, delay_slot=0x2d801):
    cpu = U.Uc(U.UC_ARCH_ARM, U.UC_MODE_THUMB | U.UC_MODE_MCLASS)
    cpu.ctl_set_cpu_model(A.UC_CPU_ARM_CORTEX_M4)
    for base, size in [(0x2d000, 4096), (0x100000, 0x20000), (0x200000, 0x20000)]:
        cpu.mem_map(base, size)
    for i in range(count):
        section = struct.unpack_from('<10I', elf, offset + stride * i)
        if section[2] & 2 and section[1] != 8 and section[5]:
            cpu.mem_write(section[3], elf[section[4]:section[4]+section[5]])
    pads = {0xc4: 0xa0, 0xc5: 0xff}
    writes, ops = [], []
    control, payload, transfers, polls = 0x8000, None, 0, 0
    def read_bus(machine, reg, size, user):
        nonlocal control, polls
        assert reg == 0x814 and size == 4
        if control & 0x400:
            polls += 1
            if transfers != stall_at:
                control &= ~0x400
        return control
    def write_bus(machine, reg, size, value, user):
        nonlocal control, payload, transfers
        assert size == 4
        if reg == 0x838:
            assert payload is None
            payload = value
            return
        assert reg == 0x814 and value & 0x8000
        control = value
        if control & 0x400:
            assert payload is not None
            ops.append(('data' if control & 0x200 else 'command', payload))
            transfers += 1
            payload = None
    cpu.mmio_map(0x40024000, 4096, read_bus, None, write_bus, None)
    def callback(machine, address, size, user):
        arg = machine.reg_read(A.UC_ARM_REG_R0)
        if address == 0x2d5b0:
            machine.reg_write(A.UC_ARM_REG_R0, pads[arg])
        elif address == 0x2d5f2:
            assert arg in pads
            pads[arg] = machine.reg_read(A.UC_ARM_REG_R1)
            writes.append((arg, pads[arg]))
        else:
            assert address == 0x2d800
            ops.append(('delay_candidate_ms', arg))
        machine.reg_write(A.UC_ARM_REG_PC, machine.reg_read(A.UC_ARM_REG_LR))
    cpu.hook_add(U.UC_HOOK_CODE, callback, begin=0x2d000, end=0x2dfff)
    stop, lcd = 0x11fff0, 0x201000
    cpu.mem_write(0x2004f4, struct.pack('<I', delay_slot))
    for reg, value in [(A.UC_ARM_REG_R0, lcd), (A.UC_ARM_REG_R1, 0x2d801),
                       (A.UC_ARM_REG_SP, 0x21fff0), (A.UC_ARM_REG_LR, stop | 1)]:
        cpu.reg_write(reg, value)
    cpu.emu_start(entry | 1, stop, count=100000)
    assert cpu.reg_read(A.UC_ARM_REG_PC) == stop
    if delay_slot != 0x2d801:
        assert cpu.reg_read(A.UC_ARM_REG_R0) == 0
        assert not writes and not ops and transfers == 0
        return
    assert cpu.reg_read(A.UC_ARM_REG_R0) == int(not stall_at)
    assert cpu.mem_read(lcd+12, 1)[0] == int(bool(stall_at))
    assert writes == [(0xc4, v) if i % 2 == 0 else (0xc5, v)
                      for i, v in enumerate([0xa7, 0xfd, 0xae, 0xfd, 0xa7, 0xfd])]
    complete = [('delay_candidate_ms', n) for n in (5, 20, 120)] + expected
    if stall_at:
        assert transfers == stall_at and polls == stall_at - 1 + 4096
        assert ops == complete[:len(ops)]
    else:
        assert ops == complete

for stall in (0, 1, 3):
    run(stall)
for invalid in (0, 1, 0xffffffff, 0x2d800):
    run(0, invalid)
print('7 panel adapter cases passed: startup, bus timeouts and invalid delay slots')
