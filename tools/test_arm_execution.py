"""Execute linked application code on emulated Cortex-M4, never on a device.

API reference: https://github.com/unicorn-engine/unicorn/blob/master/include/unicorn/unicorn.h
Synthetic memory map is deliberately unrelated to the watch's flash layout.
"""
import ctypes as C
import hashlib
import json
import os
import struct
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / 'build'
ZIG = ROOT / 'tools/python/Lib/site-packages/ziglang/zig.exe'
ELF = BUILD / 'emulator-only.elf'
env = dict(os.environ, ZIG_GLOBAL_CACHE_DIR=str(BUILD / 'zig-cache'))
command = [str(ZIG), 'cc', '-target', 'thumb-freestanding-eabi', '-mcpu=cortex_m4',
           '-mfloat-abi=soft', '-nostdlib', '-Wl,-T,' + str(ROOT / 'tests/emulator.ld'),
           *[str(BUILD / (name + '.arm.o')) for name in ('watch_core', 'watch_render', 'watch_strip')],
           '-o', str(ELF)]
subprocess.run(command, env=env, check=True, capture_output=True)
import unicorn as U
from unicorn import arm_const as A
elf = ELF.read_bytes()
shoff = struct.unpack_from('<I', elf, 32)[0]
stride, count = struct.unpack_from('<HH', elf, 46)
sections = [struct.unpack_from('<10I', elf, shoff+i*stride) for i in range(count)]
symbols = {}
for section in sections:
    if section[1] != 2:
        continue
    strings = sections[section[6]]
    names = elf[strings[4]:strings[4]+strings[5]]
    for offset in range(section[4], section[4]+section[5], section[9]):
        name, value, size, info, other, index = struct.unpack_from('<IIIBBH', elf, offset)
        text = names[name:].split(b'\0', 1)[0].decode()
        if index:
            symbols[text] = value

uc = U.Uc(U.UC_ARCH_ARM, U.UC_MODE_THUMB | U.UC_MODE_MCLASS)
uc.ctl_set_cpu_model(A.UC_CPU_ARM_CORTEX_M4)
uc.mem_map(0x100000, 0x20000)
uc.mem_map(0x200000, 0x20000, U.UC_PROT_READ | U.UC_PROT_WRITE)
for section in sections:
    if section[2] & 2 and section[1] != 8 and section[5]:
        uc.mem_write(section[3], elf[section[4]:section[4]+section[5]])
uc.mem_protect(0x100000, 0x20000, U.UC_PROT_READ | U.UC_PROT_EXEC)
STATE, BUFFER, SP, STOP = 0x201000, 0x202002, 0x21fff0, 0x11fff0
minimum_stack = SP
allowed = []


def write_check(machine, access, address, size, value, user):
    global minimum_stack
    if 0x218000 <= address and address + size <= SP:
        minimum_stack = min(minimum_stack, address)
        return
    if any(start <= address and address + size <= end for start, end in allowed):
        return
    raise AssertionError(f'Unexpected ARM write: {address:#x}, {size}')


uc.hook_add(U.UC_HOOK_MEM_WRITE, write_check)
calls = 0
instructions = 0
profile = os.environ.get('ZX19_ARM_PROFILE') == '1'
def count_instruction(machine, address, size, user):
    global instructions
    instructions += 1
if profile:
    uc.hook_add(U.UC_HOOK_CODE, count_instruction)


def call(name, *args, writable=()):
    global calls, allowed
    allowed = writable
    registers = (A.UC_ARM_REG_R0, A.UC_ARM_REG_R1, A.UC_ARM_REG_R2, A.UC_ARM_REG_R3)
    for register, value in zip(registers, args):
        uc.reg_write(register, value)
    # Extra arguments lie above entry SP; stack guard covers only callee writes.
    for index, value in enumerate(args[4:]):
        uc.mem_write(SP+index*4, struct.pack('<I', value))
    uc.reg_write(A.UC_ARM_REG_SP, SP)
    uc.reg_write(A.UC_ARM_REG_LR, STOP | 1)
    uc.emu_start(symbols[name] | 1, STOP, timeout=5_000_000, count=2_000_000)
    assert uc.reg_read(A.UC_ARM_REG_PC) == STOP, 'Execution budget exceeded'
    assert uc.reg_read(A.UC_ARM_REG_SP) == SP, 'Stack not restored'
    calls += 1
    return uc.reg_read(A.UC_ARM_REG_R0)


host = C.CDLL(str(BUILD / 'watch_core.dll'))
host.watch_state_bytes.restype = C.c_size_t
state_size = call('watch_state_bytes')
assert state_size == host.watch_state_bytes() == 796
state = (C.c_ubyte * state_size)()
host.watch_init.argtypes = [C.c_void_p, C.c_uint32]
host.watch_render_strip.argtypes = [C.c_void_p, C.POINTER(C.c_uint16), C.c_size_t,
                                  C.c_uint, C.c_uint, C.c_uint, C.c_uint]
host.watch_init(state, 0)
call('watch_init', STATE, 0, writable=[(STATE, STATE+state_size)])
assert bytes(uc.mem_read(STATE, state_size)) == bytes(state)
for name, args in [('watch_timer_set', (3, 0)), ('watch_timer_toggle', (0,)),
                   ('watch_tick', (4000, 4000))]:
    getattr(host, name).argtypes = [C.c_void_p] + [C.c_uint32]*len(args)
    getattr(host, name)(state, *args)
    call(name, STATE, *args, writable=[(STATE, STATE+state_size)])
    assert bytes(uc.mem_read(STATE, state_size)) == bytes(state), name

pages = []
for page in range(5):
    host.watch_open.argtypes = [C.c_void_p, C.c_int]
    host.watch_open(state, page)
    call('watch_open', STATE, page, writable=[(STATE, STATE+state_size)])
    before = bytes(uc.mem_read(STATE, state_size))
    assert before == bytes(state)
    pixels = (C.c_uint16 * 1720)()
    digest = hashlib.sha256()
    instruction_start = instructions
    for row in range(0, 320, 10):
        uc.mem_write(BUFFER-2, b'\xa5' * 3444)
        assert host.watch_render_strip(state, pixels, 1720, row, 45240, 17, 11) == 1
        assert call('watch_render_strip', STATE, BUFFER, 1720, row, 45240, 17, 11,
                    writable=[(BUFFER, BUFFER+3440)]) == 1
        output = bytes(uc.mem_read(BUFFER, 3440))
        assert output == bytes(pixels), (page, row)
        assert bytes(uc.mem_read(BUFFER-2, 2)) == b'\xa5\xa5'
        assert bytes(uc.mem_read(BUFFER+3440, 2)) == b'\xa5\xa5'
        digest.update(output)
    assert bytes(uc.mem_read(STATE, state_size)) == before
    pages.append({'page': page, 'rgb565_sha256': digest.hexdigest(), 'strips_matched': 32,
                  'render_instructions': instructions-instruction_start if profile else None})
report = {'passed': True, 'unicorn_version': U.__version__, 'cpu': 'Cortex-M4',
          'elf_sha256': hashlib.sha256(elf).hexdigest(), 'calls': calls,
          'state_bytes': state_size, 'observed_stack_bytes': SP-minimum_stack,
          'pages': pages, 'memory_write_guards': True, 'instruction_profiling': profile,
          'hardware_test': False, 'flashable_image': False,
          'limitations': 'CPU-only synthetic map: no ROM, interrupts, DMA, BLE, display hardware or energy measurement.'}
(ROOT / 'reports/arm-execution.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
print(json.dumps(report, indent=2))
