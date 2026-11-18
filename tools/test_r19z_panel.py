"""Execute the board adapter on Cortex-M4 with modeled ROM, bus and clock."""
import json
from pathlib import Path
import struct
import sys
import ctypes as C
import hashlib
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_r19z_runtime import build_runtime
import unicorn as U
from unicorn import arm_const as A

root = Path(__file__).resolve().parents[1]
build = root / 'build'
build.mkdir(exist_ok=True)
elf = build_runtime().read_bytes()
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

def frame_operations(seconds=45240, day=17, month=11, page=0):
    lib = C.CDLL(str(build / 'watch_core.dll'))
    state = State()
    lib.watch_init(C.byref(state), 500)
    lib.watch_open(C.byref(state), page)
    ops = []
    @FILL
    def rectangle(ctx, x, y, w, h, color):
        for cmd, first, last in [(0x2a, x+34, x+w+33), (0x2b, y, y+h-1)]:
            ops.append(('command', cmd))
            ops.extend(('data', b) for b in struct.pack('>HH', first, last))
        ops.append(('command', 0x2c))
        ops.extend([('data', color >> 8), ('data', color & 255)] * (w*h))
    canvas = Canvas(172, 320, rectangle, None)
    lib.watch_render(C.byref(state), C.byref(canvas), 2, C.c_uint(seconds), day, month)
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

def run(stall_at, delay_slot=0x2d801, hz=40000000, boot=False, create_ok=True, sync=False):
    cpu = U.Uc(U.UC_ARCH_ARM, U.UC_MODE_THUMB | U.UC_MODE_MCLASS)
    cpu.ctl_set_cpu_model(A.UC_CPU_ARM_CORTEX_M4)
    for base, size in [(0, 0x40000), (0x100000, 0x20000), (0x200000, 0x20000),
                       (0x800000,0x100000),(0x4800000,0x100000),(0xe000e000,4096)]:
        cpu.mem_map(base, size)
    for i in range(count):
        section = struct.unpack_from('<10I', elf, offset + stride * i)
        if section[2] & 2 and section[1] != 8 and section[5]:
            cpu.mem_write(section[3], elf[section[4]:section[4]+section[5]])
            if section[3] == symbols[b'__r19z_data_start']:
                cpu.mem_write(symbols[b'__r19z_data_load'],elf[section[4]:section[4]+section[5]])
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
    if boot:
        registers = {}
        packets = iter([(0xa7,[0xb4]),(1,[0,1,0,40,0,80]),(1,[0,0,0,40,0,80])])
        response, fifo = [], []
        stops = 0
        def i2c_write(machine, offset, size, value, user):
            nonlocal stops
            reg = offset-0x400
            if reg != 0x10:
                registers[reg] = value
            elif not value & 0x100:
                index, data = next(packets)
                assert value == index and registers[4] == 0x15 and registers[0] == 0x65
                response.extend(data)
            else:
                fifo.append(response.pop(0))
                if value & 0x200:
                    assert not response
                    stops += 1
        def i2c_read(machine, offset, size, user):
            reg = offset-0x400
            if reg == 0x70: return 2 | (8 if fifo else 0)
            if reg == 0x10: return fifo.pop(0)
            if reg == 0x34: return 0x200 if not response and not fifo and stops else 0
            return registers.get(reg,0)
        cpu.mmio_map(0x40015000,4096,i2c_read,None,i2c_write,None)
        # ROM model drives the slots installed by the linked entry point.
        bank, stack = 0x802000, 0x810000
        cpu.mem_write(bank+0x1e0,struct.pack('<II',stack,0x10000))
        cpu.mem_write(stack|0x4000000, struct.pack('<BBHHHI',9,0,0x901,0x279a,0,0xfc00)
                      + bytes.fromhex('1d6a69f12f38ea1182a767370a3ca32e') + struct.pack('<I',stack+1025))
        cpu.mem_write(0x2002dc,b'\x01')
        cpu.mem_write(symbols[b'__r19z_bss_start'], b'\xa5'*(symbols[b'__r19z_bss_end']-symbols[b'__r19z_bss_start']))
        task = []
        calls = []
        base_ms = 500
        registered = {}
        radio_calls = []
        io_messages = [(0,1,1),(0,2,0)]
        def rom(machine, pc, size, user):
            calls.append(pc)
            arg = machine.reg_read(A.UC_ARM_REG_R0)
            if pc == 0xd8a4: result = 0
            elif pc == 0x112c: result = bank
            elif pc == 0xd8bc: result = int(arg == bank)
            elif pc == 0x4d38:
                assert arg == 0x200000
                machine.mem_write(0xe000ed08,struct.pack('<I',arg))
                result = 0
            elif pc == 0x1330c:
                name = b'ZX19 BLE\0' if task else b'ZX19\0'
                assert machine.mem_read(machine.reg_read(A.UC_ARM_REG_R1),len(name))==name
                task.append(machine.reg_read(A.UC_ARM_REG_R2))
                result = int(create_ok)
            elif pc == 0x130a0:
                if sync:
                    machine.emu_stop()
                    return
                machine.reg_write(A.UC_ARM_REG_PC,task[0])
                return
            elif pc == 0x8036: result = 0
            elif pc == 0x12cdc:
                machine.mem_write(arg,struct.pack('<I',machine.reg_read(A.UC_ARM_REG_R2)))
                result = 1
            elif pc == 0x12e2c:
                if not io_messages:
                    machine.emu_stop()
                    return
                msg = machine.reg_read(A.UC_ARM_REG_R1)
                if arg == 1: machine.mem_write(msg,b'\x02')
                else: machine.mem_write(msg,struct.pack('<HHI',*io_messages.pop(0)))
                result = 1
            elif pc == 0x2c800:
                regs = [machine.reg_read(r) for r in (A.UC_ARM_REG_R1,A.UC_ARM_REG_R2,A.UC_ARM_REG_R3)]
                sp = machine.reg_read(A.UC_ARM_REG_SP)
                stack_args = struct.unpack('<4I',machine.mem_read(sp,16))
                radio_calls.append(arg)
                if arg == 0x3001: machine.mem_write(regs[1],b'\x01')
                elif arg in (0x3005,0x3300): machine.mem_write(stack_args[0],b'\x00')
                elif arg == 0x3102:
                    service, table, length = regs
                    assert length == 3*32 or length == 3*28
                    uuid_address = struct.unpack('<I',machine.mem_read(table+20,4))[0]
                    assert bytes(machine.mem_read(uuid_address,16)).hex() == '9ecadc240ee5a9e093f3a3b5f0ff406e'
                    assert bytes(machine.mem_read(table+2*(length//3)+2,16)).hex() == '9ecadc240ee5a9e093f3a3b50200406e'
                    registered['write'] = stack_args[1]
                    machine.mem_write(service,b'\x03')
                    machine.mem_write(stack_args[3],b'\x01')
                elif arg == 0x100: machine.mem_write(stack_args[0],b'\x01')
                elif arg == 0x3302: machine.mem_write(regs[0],b'\x00')
                result = 0
            elif pc == 0x13046:
                machine.reg_write(A.UC_ARM_REG_R1,0)
                result = (base_ms + 32*calls.count(0x13028)) & 0xffffffff
            elif pc == 0x13028:
                assert arg == 32
                if calls.count(pc) == 3:
                    machine.emu_stop()
                    return
                result = 0
            elif pc == stack+1024: result = 0
            else: raise AssertionError(hex(pc))
            machine.reg_write(A.UC_ARM_REG_R0,result)
            machine.reg_write(A.UC_ARM_REG_PC,machine.reg_read(A.UC_ARM_REG_LR))
        for address in (0xd8a4,0x112c,0xd8bc,0x4d38,0x1330c,0x130a0,0x13046,0x13028,
                        0x8036,0x12cdc,0x12e2c,0x2c800,stack+1024):
            cpu.hook_add(U.UC_HOOK_CODE,rom,begin=address,end=address)
        def invoke(addr):
            cpu.reg_write(A.UC_ARM_REG_LR,stop|1)
            cpu.emu_start(addr|1,stop,count=12000000)
        assert entry & ~1 == 0x82c400
        invoke(entry)
        assert cpu.reg_read(A.UC_ARM_REG_R0)==1
        slots = struct.unpack('<III',cpu.mem_read(0x200cc0,12))
        assert slots == (symbols[b'r19z_pre_main'],stack+1025,symbols[b'r19z_app_main'])
        for addr in slots[:2]: invoke(addr)
        face_time = (0xffffffff,0,0)
        if sync:
            cpu.mem_write(0x202a60,struct.pack('<I',0x2c801))
            invoke(slots[2])
            assert len(task) == 2
            cpu.reg_write(A.UC_ARM_REG_SP,0x21fff0)
            invoke(task[1])
            assert radio_calls.count(0x3302) == 2
            def deliver(fields, length=16, corrupt=False):
                packet = bytearray.fromhex(fields) + bytearray(9)
                packet[-1] = (sum(packet) + int(corrupt)) & 255
                cpu.mem_write(0x202800,bytes(packet))
                cpu.reg_write(A.UC_ARM_REG_SP,0x21ffe0)
                cpu.mem_write(0x21ffe0,struct.pack('<III',length,0x202800,0x202840))
                for r,v in [(A.UC_ARM_REG_R0,0),(A.UC_ARM_REG_R1,3),(A.UC_ARM_REG_R2,2),(A.UC_ARM_REG_R3,0)]:
                    cpu.reg_write(r,v)
                invoke(registered['write'])
                return cpu.reg_read(A.UC_ARM_REG_R0) == 0
            base_ms = 0xfffffff0
            assert deliver('01 24 02 28 23 59 59')
            for fields in ('01 23 02 29 01 02 03','01 24 04 31 01 02 03',
                           '01 24 01 31 1a 02 03','01 24 01 31 24 02 03'):
                assert not deliver(fields)
            assert not deliver('01 24 02 28 23 59 59',corrupt=True)
            assert not deliver('01 24 02 28 23 59 59',length=15)
            base_ms = (base_ms + 2000) & 0xffffffff
            face_time = (1,29,2)
        if sync:
            cpu.reg_write(A.UC_ARM_REG_SP,0x21fff0)
            invoke(task[0])
        else: invoke(slots[2])
        if not create_ok:
            assert 0x130a0 not in calls and not ops
            return
        assert calls[-6:] == [0x13046,0x13028]*3
        assert stops == 3
        assert ops == ([('delay_candidate_ms', n) for n in (50,5,20,120)] + expected
                       + frame_operations(*face_time) + frame_operations(*face_time,1))
        return
    cpu.emu_start(symbols[b'r19z_display_start'] | 1, stop, count=12000000)
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
run(0,boot=True)
run(0,boot=True,create_ok=False)
run(0,boot=True,sync=True)
print(f'15 cases passed including QC time handler, leap day and tick wrap; {len(frame)} timed-face transfers')
