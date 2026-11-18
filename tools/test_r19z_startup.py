"""Emulated startup contract. ROM return values and headers are TEST fixtures.
No device access and no proof of hardware boot or radio initialization.
"""
import hashlib
import json
import os
import struct
import subprocess
from pathlib import Path
import unicorn as U
from unicorn import arm_const as A

ROOT=Path(__file__).resolve().parents[1]
BUILD=ROOT/'build'
zig=ROOT/'tools/python/Lib/site-packages/ziglang/zig.exe'
elf_path=BUILD/'r19z-startup-test-only.elf'
cmd=[str(zig),'cc','-target','thumb-freestanding-eabi','-mcpu=cortex_m4',
     '-mfloat-abi=soft','-std=c11','-Os','-g','-Wall','-Wextra','-Werror',
     '-ffreestanding','-fno-builtin','-fno-stack-protector','-nostdlib',
     '-Wl,-e,r19z_system_init','-Wl,-T,'+str(ROOT/'src/r19z_memory.ld'),
     str(ROOT/'src/r19z_startup.c'),
     str(ROOT/'tests/r19z_boot_fixture.c'),'-o',str(elf_path)]
run=subprocess.run(cmd,env=dict(os.environ,ZIG_GLOBAL_CACHE_DIR=str(BUILD/'zig-cache')),
                   capture_output=True,text=True)
if run.returncode: raise SystemExit(run.stderr)
elf=elf_path.read_bytes()
shoff=struct.unpack_from('<I',elf,32)[0]
stride,count=struct.unpack_from('<HH',elf,46)
sections=[struct.unpack_from('<10I',elf,shoff+i*stride) for i in range(count)]
symbols={}
for s in sections:
    if s[1]!=2: continue
    st=sections[s[6]];names=elf[st[4]:st[4]+st[5]]
    for off in range(s[4],s[4]+s[5],s[9]):
        name,value,size,info,other,index=struct.unpack_from('<IIIBBH',elf,off)
        if index: symbols[names[name:].split(b'\0',1)[0].decode()]=value
assert (symbols['r19z_system_init'] & ~1)==0x82c400
assert struct.unpack_from('<I',elf,24)[0] == symbols['r19z_system_init']

def check(case):
    uc=U.Uc(U.UC_ARCH_ARM,U.UC_MODE_THUMB|U.UC_MODE_MCLASS)
    uc.ctl_set_cpu_model(A.UC_CPU_ARM_CORTEX_M4)
    uc.mem_map(0,0x20000)
    uc.mem_map(0x200000,0x20000)
    uc.mem_map(0x800000,0x100000)
    uc.mem_map(0x4800000,0x100000)
    for s in sections:
        if s[2]&2 and s[1]!=8 and s[5]:
            data=elf[s[4]:s[4]+s[5]]
            if s[3]>=0x800000: uc.mem_write(s[3],data)
            else: uc.mem_write(symbols['__r19z_data_load'],data)
    uc.mem_write(0x208500,b'\xa5'*0x8a30)
    uc.mem_write(0x2002dc,bytes([0 if case=='stack_disabled' else 1]))
    bank=0x802000; stack=0x810000; stack_size=0x10000
    stored_stack = stack | (0x4000000 if case=='aliased_table' else 0)
    uc.mem_write(bank+0x1e0,struct.pack('<II',stored_stack,stack_size))
    hdr=bytearray(1024)
    struct.pack_into('<BBHHHI',hdr,0,9,0,0x901,0x279a,0,0xfc00)
    hdr[12:28]=bytes.fromhex('1d6a69f12f38ea1182a767370a3ca32e')
    stored_entry = (stack+1025) | (0x4000000 if case=='aliased_entry' else 0)
    struct.pack_into('<I',hdr,28,stored_entry)
    if case=='wrong_uuid': hdr[12]^=1
    if case=='not_ready': hdr[2]|=0x80
    if case=='bad_entry': struct.pack_into('<I',hdr,28,stack+stack_size)
    if case=='bad_id': struct.pack_into('<H',hdr,4,0x2793)
    uc.mem_write(stack | 0x4000000,bytes(hdr))
    for address in (0xd8a4,0x112c,0xd8bc): uc.mem_write(address,b'\x70\x47')
    uc.mem_protect(0,0x20000,U.UC_PROT_READ|U.UC_PROT_EXEC)
    uc.mem_protect(0x800000,0x100000,U.UC_PROT_READ|U.UC_PROT_EXEC)
    uc.mem_protect(0x4800000,0x100000,U.UC_PROT_READ)
    writes=[]; rom_calls=[]
    def rom(machine,address,size,user):
        if address not in (0xd8a4,0x112c,0xd8bc): return
        rom_calls.append(hex(address))
        value={0xd8a4:int(case=='hci'),0x112c:0 if case=='no_bank' else bank,
               0xd8bc:0 if case=='bad_bank_header' else 1}[address]
        if address==0xd8bc:
            assert machine.reg_read(A.UC_ARM_REG_R0)==bank
            assert machine.reg_read(A.UC_ARM_REG_R1)==0x2790
        machine.reg_write(A.UC_ARM_REG_R0,value)
    def on_write(machine,access,address,size,value,user):
        if 0x203000<=address and address+size<=0x203400: return
        writes.append((address,size))
        allowed=((0x200380,0x20038c),(0x200cc0,0x200ccc),(0x200fb4,0x200fb8),
                 (symbols['__r19z_data_start'],symbols['__r19z_data_end']),
                 (symbols['__r19z_bss_start'],symbols['__r19z_bss_end']))
        assert any(lo<=address and address+size<=hi for lo,hi in allowed),hex(address)
    uc.hook_add(U.UC_HOOK_CODE,rom)
    uc.hook_add(U.UC_HOOK_MEM_WRITE,on_write)
    uc.reg_write(A.UC_ARM_REG_SP,0x203400)
    uc.reg_write(A.UC_ARM_REG_LR,0x800101)
    uc.emu_start(symbols['r19z_system_init']|1,0x800100,timeout=1_000_000,count=100000)
    assert uc.reg_read(A.UC_ARM_REG_PC)==0x800100
    assert uc.reg_read(A.UC_ARM_REG_SP)==0x203400
    success=case in ('valid','aliased_entry','aliased_table')
    assert uc.reg_read(A.UC_ARM_REG_R0)==int(success)
    if success:
        expected={0x200380:0x208500,0x200384:0x13f00,0x200388:0x7d00,
                  0x200cc0:symbols['r19z_pre_main'],0x200cc4:stored_entry,
                  0x200cc8:symbols['r19z_app_main'],0x200fb4:symbols['r19z_watchdog_callback'],
                  symbols['boot_fixture_data']:0x1234abcd,symbols['boot_fixture_bss']:0}
        for address,value in expected.items():
            assert struct.unpack('<I',uc.mem_read(address,4))[0]==value,hex(address)
    else: assert not writes, 'Rejected fixture changed application/platform memory'
    return {'case':case,'passed':True,'rom_calls':rom_calls,'non_stack_writes':len(writes)}

cases=[check(c) for c in ('valid','aliased_entry','aliased_table','hci','stack_disabled','no_bank','bad_bank_header',
                         'wrong_uuid','not_ready','bad_entry','bad_id')]
report={'cases':cases,'elf_sha256':hashlib.sha256(elf).hexdigest(),
        'entry':'0x82c400','static_ram_end':hex(symbols['__r19z_bss_end']),
        'source':'src/r19z_startup.c','device_access':False,'hardware_boot_verified':False,
        'limitations':'Synthetic ROM responses and bank/upperstack headers; test-only callbacks. No board/radio/app startup is implemented by these callbacks.'}
(ROOT/'reports/r19z-startup-tests.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,indent=2))
