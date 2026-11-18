"""ARM transport execution with an explicitly synthetic I2C register model."""
import json
import os
import struct
import subprocess
from pathlib import Path
import unicorn as U
from unicorn import arm_const as A

ROOT=Path(__file__).resolve().parents[1]
BUILD=ROOT/'build'
linker=BUILD/'i2c-test-only.ld'
linker.write_text((ROOT/'tests/emulator.ld').read_text().replace('ENTRY(watch_init)',
    'ENTRY(r19z_touch_i2c_read)'),encoding='utf-8')
target=BUILD/'i2c-test-only.elf'
command=[str(ROOT/'tools/python/Lib/site-packages/ziglang/zig.exe'),'cc',
    '-target','thumb-freestanding-eabi','-mcpu=cortex_m4','-mfloat-abi=soft',
    '-nostdlib','-g','-std=c11','-Os','-Wall','-Wextra','-Werror','-ffreestanding',
    '-fno-builtin','-fno-stack-protector','-Wl,-e,r19z_touch_i2c_read',
    '-Wl,-T,'+str(linker),str(ROOT/'src/r19z_i2c.c'),'-o',str(target)]
p=subprocess.run(command,env=dict(os.environ,ZIG_GLOBAL_CACHE_DIR=str(BUILD/'zig-cache')),
                 capture_output=True,text=True)
if p.returncode: raise SystemExit(p.stderr)
elf=target.read_bytes();entry=struct.unpack_from('<I',elf,24)[0]
offset=struct.unpack_from('<I',elf,32)[0];stride,count=struct.unpack_from('<HH',elf,46)
sections=[struct.unpack_from('<10I',elf,offset+i*stride) for i in range(count)]

def test(name):
    uc=U.Uc(U.UC_ARCH_ARM,U.UC_MODE_THUMB|U.UC_MODE_MCLASS)
    uc.ctl_set_cpu_model(A.UC_CPU_ARM_CORTEX_M4)
    uc.mem_map(0x100000,0x20000);uc.mem_map(0x200000,0x20000)
    for s in sections:
        if s[2]&2 and s[1]!=8 and s[5]: uc.mem_write(s[3],elf[s[4]:s[4]+s[5]])
    uc.mem_protect(0x100000,0x20000,U.UC_PROT_READ|U.UC_PROT_EXEC)
    base=0x40015400; bus=0x201000; output=0x202001; sp=0x21fff0
    size=1 if name=='probe' else 6
    if name=='bad_size': size=7
    values=[0xb4] if size==1 else [0,1,0,30,0,40]
    state={'commands':[],'queue':[],'started':False,'stop':False,'last':False,'disabled':False,'polls':0,'reads':[]}
    uc.mem_write(bus,struct.pack('<IB3x',0xffffffff if name=='large_budget' else 80,int(name=='fault_latched')))
    uc.mem_write(output-1,b'\xa5'*8)
    uc.mem_write(sp,struct.pack('<I',size))
    def read(machine,access,address,n,value,user):
        if not base<=address<base+0xa0: return 0
        reg=address-base;result=0
        if reg==0: result=0x63
        elif reg==4: result=0x16 if name=='wrong_target' else 0x15
        elif reg==0x6c: result=0 if state['disabled'] else 1
        elif reg==0x70:
            state['polls']+=1
            result=2 | (8 if state['queue'] or name=='stale_rx' else 0)
            if name=='busy' or (state['started'] and not state['stop']): result|=1
        elif reg==0x34:
            if name=='nack' and state['started']: result=0x40
            elif state['stop'] and name!='missing_stop': result=0x200
        elif reg==0x10:
            assert state['queue']
            result=state['queue'].pop(0)
            if state['last']: state['stop']=True
        state['reads'].append((hex(reg),result))
        return result
    def write(machine,access,address,n,value,user):
        if base<=address<base+0xa0:
            reg=address-base
            assert reg in (0x10,0x6c),hex(reg)
            if reg==0x6c:
                assert value==0
                state['disabled']=True
                return
            state['commands'].append(value)
            if not value&0x100:
                assert value==0xa7
                state['started']=True
            else:
                index=len(state['commands'])-2
                if name not in ('stuck_rx','large_budget'): state['queue'].append(values[index])
                state['last']=bool(value&0x200)
            return
        assert (bus<=address and address+n<=bus+8) or (output<=address and address+n<=output+6) or (sp-1024<=address and address+n<=sp),hex(address)
    uc.mmio_map(0x40015000,0x1000,
        lambda m,o,n,u: read(m,0,0x40015000+o,n,0,u),None,
        lambda m,o,n,v,u: write(m,0,0x40015000+o,n,v,u),None)
    def ram_write(m,a,address,n,v,u):
        if not 0x40015000<=address<0x40016000: write(m,a,address,n,v,u)
    uc.hook_add(U.UC_HOOK_MEM_WRITE,ram_write)
    for reg,value in [(A.UC_ARM_REG_R0,bus),(A.UC_ARM_REG_R1,0x15),
        (A.UC_ARM_REG_R2,0xa7),(A.UC_ARM_REG_R3,output),(A.UC_ARM_REG_SP,sp),
        (A.UC_ARM_REG_LR,0x11fff1)]: uc.reg_write(reg,value)
    uc.emu_start(entry|1,0x11fff0,timeout=1_000_000,count=100000)
    assert uc.reg_read(A.UC_ARM_REG_PC)==0x11fff0
    assert uc.reg_read(A.UC_ARM_REG_SP)==sp
    success=name in ('probe','sample')
    assert uc.reg_read(A.UC_ARM_REG_R0)==int(success),(name,state,uc.reg_read(A.UC_ARM_REG_R0))
    received=bytes(uc.mem_read(output,6))
    if success:
        assert received[:size]==bytes(values)
        assert state['commands']==[0xa7]+[0x100]*(size-1)+[0x300]
        assert not state['disabled']
    else: assert received==b'\xa5'*6
    fault=bytes(uc.mem_read(bus+4,1))[0]
    assert fault==int(name in ('nack','stuck_rx','large_budget','missing_stop','stale_rx','fault_latched'))
    assert bytes(uc.mem_read(output-1,1))==b'\xa5'
    assert bytes(uc.mem_read(output+6,1))==b'\xa5'
    assert state['polls']<=(4098 if name=='large_budget' else 82)
    return {'case':name,'passed':True,'commands':state['commands'],
            'status_polls':state['polls'],'fault':fault,'controller_disabled':state['disabled']}

cases=[test(name) for name in ('probe','sample','nack','stuck_rx','missing_stop',
                              'busy','stale_rx','wrong_target','bad_size','fault_latched','large_budget')]
report={'cases':cases,'cpu':'Cortex-M4','hardware_test':False,'device_access':False,
        'limitation':'Synthetic register behavior; electrical timing, pinmux, clocks and physical controller are not verified.'}
(ROOT/'reports/r19z-i2c-tests.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,indent=2))
