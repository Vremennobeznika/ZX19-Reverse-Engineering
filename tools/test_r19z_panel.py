"""Execute the board adapter on Cortex-M4 with modeled ROM, bus and clock."""
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import ctypes as C
import hashlib
import unicorn as U
from unicorn import arm_const as A

root = Path(__file__).resolve().parents[1]
build = root / 'build'
build.mkdir(exist_ok=True)
image = build / 'r19z-panel-test.elf'
zig = root / 'tools/python/Lib/site-packages/ziglang/zig.exe'
subprocess.run([str(zig), 'cc', '-target', 'thumb-freestanding-eabi', '-mcpu=cortex_m4',
                '-Os', '-g', '-Wall', '-Wextra', '-Werror', '-ffreestanding', '-nostdlib',
                '-Wl,-u,r19z_display_update',
                '-Wl,-T,' + str(root / 'tests/emulator.ld'), '-Wl,-e,r19z_display_start',
                str(root / 'src/r19z_panel.c'), str(root / 'src/watch_lcd.c'),
                str(root / 'src/r19z_display_app.c'), str(root / 'src/watch_core.c'),
                str(root / 'src/watch_render.c'),
                '-o', str(image)], check=True,
               env=dict(os.environ, ZIG_GLOBAL_CACHE_DIR=str(build / 'zig-cache')))
elf = image.read_bytes()
entry = struct.unpack_from('<I', elf, 24)[0]
offset = struct.unpack_from('<I', elf, 32)[0]
stride, count = struct.unpack_from('<HH', elf, 46)
sections = [struct.unpack_from('<10I', elf, offset + stride*i) for i in range(count)]
symbols = {}
for section in sections:
    if section[1] == 2:
        strings = sections[section[6]]
        names = elf[strings[4]:strings[4]+strings[5]]
        for pos in range(section[4], section[4]+section[5], section[9]):
            name, value = struct.unpack_from('<II', elf, pos)
            symbols[names[name:].split(b'\0', 1)[0]] = value
stock = json.loads((root / 'research/lcd-init-candidate.json').read_text())
expected = [(op['kind'], op['value']) for op in stock['operations']]

# Independent host renderer output expanded into LCD windows and pixel bytes.
sys.path.insert(0, str(root / 'tests'))
from test_renderer import Canvas, FILL, State

def frame_operations():
    lib = C.CDLL(str(build / 'watch_core.dll'))
    state = State()
    lib.watch_init(C.byref(state), 500)
    ops = []
    @FILL
    def rectangle(ctx, x, y, w, h, color):
        for cmd, first, last in [(0x2a, x+34, x+w+33), (0x2b, y, y+h-1)]:
            ops.append(('command', cmd))
            ops.extend(('data', b) for b in struct.pack('>HH', first, last))
        ops.append(('command', 0x2c))
        ops.extend([('data', color >> 8), ('data', color & 255)] * (w*h))
    canvas = Canvas(172, 320, rectangle, None)
    lib.watch_render(C.byref(state), C.byref(canvas), 2, 45240, 17, 11)
    assert len(ops) > 172*320*2
    return ops

frame = frame_operations()

def stock_bus_trace(hz):
    blob = (root / 'firmware/R19Z_1.00.18_241125.bin').read_bytes()
    assert hashlib.sha256(blob).hexdigest() == '22f94070c13c157048b335e25af21e3421cc0a92c77c6b13f3c8088f88ddd7bd'
    cpu = U.Uc(U.UC_ARCH_ARM, U.UC_MODE_THUMB | U.UC_MODE_MCLASS)
    for base, size in [(0,0x40000),(0x800000,0x100000),(0x200000,0x20000),(0x40000000,0x30000)]:
        cpu.mem_map(base,size)
    cpu.mem_write(0x82c000,blob[80:])
    cpu.mem_write(0x40000000,b'\xa5'*4096)
    cpu.mem_write(0x200100,struct.pack('<I',hz))
    cpu.reg_write(A.UC_ARM_REG_SP,0x210000)
    cpu.reg_write(A.UC_ARM_REG_R5,1)
    trace = []
    def aon(machine,pc,size,user):
        addr = machine.reg_read(A.UC_ARM_REG_R0)
        if pc == 0x2d5b0:
            machine.reg_write(A.UC_ARM_REG_R0, 0xa5)
        else:
            assert pc == 0x2d5f2
            trace.append((addr,machine.reg_read(A.UC_ARM_REG_R1)))
        machine.reg_write(A.UC_ARM_REG_PC,machine.reg_read(A.UC_ARM_REG_LR))
    cpu.hook_add(U.UC_HOOK_CODE,aon,begin=0x2d5b0,end=0x2d5f2)
    cpu.hook_add(U.UC_HOOK_MEM_WRITE,lambda m,t,p,n,v,c: trace.append((p,v)),
                 begin=0x40000000,end=0x4002ffff)
    cpu.emu_start(0x83228b,0x832478,count=5000)
    assert cpu.reg_read(A.UC_ARM_REG_PC) == 0x832478
    return trace

def run(stall_at, delay_slot=0x2d801, hz=40000000):
    cpu = U.Uc(U.UC_ARCH_ARM, U.UC_MODE_THUMB | U.UC_MODE_MCLASS)
    cpu.ctl_set_cpu_model(A.UC_CPU_ARM_CORTEX_M4)
    for base, size in [(0x2d000, 4096), (0x100000, 0x20000), (0x200000, 0x20000)]:
        cpu.mem_map(base, size)
    for i in range(count):
        section = struct.unpack_from('<10I', elf, offset + stride * i)
        if section[2] & 2 and section[1] != 8 and section[5]:
            cpu.mem_write(section[3], elf[section[4]:section[4]+section[5]])
    pads = dict.fromkeys(range(256), 0xa5)
    pads.update({0xc4: 0xa0, 0xc5: 0xff})
    writes, ops = [], []
    cpu.mem_map(0x40000000,4096)
    cpu.mem_write(0x40000000,b'\xa5'*4096)
    cpu.mem_write(0x200100,struct.pack('<I',hz))
    cpu.hook_add(U.UC_HOOK_MEM_WRITE,lambda m,t,p,n,v,c: writes.append((p,v)),
                 begin=0x40000000,end=0x40000fff)
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
        if reg in (0x800,0x804,0x808,0x810) or (reg == 0x814 and value == 0x40000100 and not ops):
            writes.append((0x40024000 + reg,value))
            if reg == 0x814: control = value
            return
        assert reg == 0x814 and value & 0x40000000
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
    cpu.mem_write(0x202000, struct.pack('<IIBB', 500, 45240, 17, 11))
    for reg, value in [(A.UC_ARM_REG_R0, lcd), (A.UC_ARM_REG_R1, 0x202000),
                       (A.UC_ARM_REG_SP, 0x21fff0), (A.UC_ARM_REG_LR, stop | 1)]:
        cpu.reg_write(reg, value)
    cpu.emu_start(entry | 1, stop, count=12000000)
    assert cpu.reg_read(A.UC_ARM_REG_PC) == stop
    if delay_slot != 0x2d801:
        assert cpu.reg_read(A.UC_ARM_REG_R0) == 0
        assert not writes and not ops and transfers == 0
        return
    assert cpu.reg_read(A.UC_ARM_REG_R0) == int(not stall_at)
    assert cpu.mem_read(lcd+12, 1)[0] == int(bool(stall_at))
    assert writes == stock_bus_trace(hz) + [(0xd0,0xa2),(0xd1,0xa5)] + [(0xc4, v) if i % 2 == 0 else (0xc5, v)
                      for i, v in enumerate([0xa7, 0xfd, 0xae, 0xfd, 0xa7, 0xfd])]
    complete = [('delay_candidate_ms', n) for n in (50, 5, 20, 120)] + expected + frame
    if stall_at:
        assert transfers == stall_at and polls == stall_at - 1 + 4096
        assert ops == complete[:len(ops)]
    else:
        assert ops == complete
        for day in (17, 18):
            ops.clear()
            cpu.mem_write(0x202000, struct.pack('<IIBB', 600, 45240, day, 11))
            cpu.reg_write(A.UC_ARM_REG_R0, lcd)
            cpu.reg_write(A.UC_ARM_REG_R1, 0x202000)
            cpu.reg_write(A.UC_ARM_REG_LR, stop | 1)
            cpu.emu_start(symbols[b'r19z_display_update'] | 1, stop, count=12000000)
            assert cpu.reg_read(A.UC_ARM_REG_PC) == stop
            assert cpu.reg_read(A.UC_ARM_REG_R0) == 1
            if day == 17:
                assert not ops
            else:
                assert 0 < len(ops) < len(frame)

for stall in (0, 1, 3, 500):
    run(stall)
for invalid in (0, 1, 0xffffffff, 0x2d800):
    run(0, invalid)
for hz in (8000000,90000000,100000000,48000000):
    run(1,hz=hz)
print(f'12 cases passed; hardware setup matched stock at 5 clocks; {len(frame)} first-frame transfers')
