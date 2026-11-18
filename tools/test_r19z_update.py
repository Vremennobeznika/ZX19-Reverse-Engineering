"""Execute the shipped ARM updater with simulated RTL8762D ROM and NOR flash."""
import hashlib
import struct
import sys
from pathlib import Path
import unicorn as U
from unicorn import arm_const as A
sys.path.insert(0,str(Path(__file__).resolve().parent))
from package_r19z import ROOT, OUTPUT, BASE, package
from build_r19z_runtime import build_runtime
from inspect_realtek import image_digest

elf=build_runtime().read_bytes()
blob=OUTPUT.read_bytes()
assert blob==package(elf)
sh=struct.unpack_from('<I',elf,32)[0]
stride,count=struct.unpack_from('<HH',elf,46)
sections=[struct.unpack_from('<10I',elf,sh+i*stride) for i in range(count)]
symbols={}
for sec in sections:
    if sec[1]!=2: continue
    table=sections[sec[6]]
    strings=elf[table[4]:table[4]+table[5]]
    for pos in range(sec[4],sec[4]+sec[5],sec[9]):
        name,value=struct.unpack_from('<II',elf,pos)
        symbols[strings[name:].split(b'\0',1)[0].decode()]=value

temp=0x900000
capacity=0x60000
stock=(ROOT/'firmware/R19Z_1.00.18_241125.bin').read_bytes()
assert hashlib.sha256(stock).hexdigest()=='22f94070c13c157048b335e25af21e3421cc0a92c77c6b13f3c8088f88ddd7bd'
key=bytes.fromhex((ROOT/'firmware/ZX19-owner.key').read_text().strip())

class Board:
    def __init__(self):
        self.cpu=U.Uc(U.UC_ARCH_ARM,U.UC_MODE_THUMB|U.UC_MODE_MCLASS)
        self.cpu.mem_map(0,0x40000)
        self.cpu.mem_map(0x200000,0x20000)
        self.cpu.mem_map(0x820000,0x20000)
        self.cpu.mem_write(BASE,blob[80:])
        self.flash=bytearray([255])*capacity
        self.writes=self.resets=0
        self.dual=self.overlap=self.bad_read=False
        self.protected=True
        for name in ('SHA256_Init','SHA256_Update','SHA256_Final','flash_get_bank_addr',
                     'flash_get_bank_size','is_ota_support_bank_switch','flash_erase_locked',
                     'flash_sw_protect_unlock_by_addr_locked','flash_set_block_protect_locked',
                     'flash_write_locked','flash_read_locked','check_image_chksum','WDG_SystemReset'):
            addr=symbols[name]&~1
            self.cpu.hook_add(U.UC_HOOK_CODE,self.rom,name,begin=addr,end=addr)
    def rom(self,m,pc,size,name):
        a,b,c=[m.reg_read(r) for r in (A.UC_ARM_REG_R0,A.UC_ARM_REG_R1,A.UC_ARM_REG_R2)]
        ret=1
        if name=='SHA256_Init': self.sha=hashlib.sha256()
        elif name=='SHA256_Update': self.sha.update(m.mem_read(b,c))
        elif name=='SHA256_Final': m.mem_write(b,self.sha.digest())
        elif name=='is_ota_support_bank_switch': ret=int(self.dual)
        elif name=='flash_get_bank_addr': ret={2:0x802000,4:0x840000 if self.overlap else temp}[a]
        elif name=='flash_get_bank_size': ret={2:0x80000,4:capacity}[a]
        elif name=='flash_sw_protect_unlock_by_addr_locked':
            assert self.protected and temp<=a<temp+capacity
            self.protected=False
            m.mem_write(b,b'\x05')
        elif name=='flash_set_block_protect_locked':
            assert a==5
            self.protected=True
        elif name=='flash_erase_locked':
            assert a==2 and b%4096==0 and temp<=b<=temp+capacity-4096 and not self.protected
            self.flash[b-temp:b-temp+4096]=b'\xff'*4096
        elif name=='flash_write_locked':
            assert not self.protected and temp<=a<=temp+capacity-b
            pos=a-temp
            data=m.mem_read(c,b)
            assert all(x&y==y for x,y in zip(self.flash[pos:pos+b],data))
            self.flash[pos:pos+b]=data
            self.writes+=1
        elif name=='flash_read_locked':
            assert temp<=a<=temp+capacity-b
            m.mem_write(c,bytes(self.flash[a-temp:a-temp+b]))
            ret=int(not self.bad_read)
        elif name=='check_image_chksum':
            assert a==temp|0x4000000 and self.flash[2]&128
            length=1024+struct.unpack_from('<I',self.flash,8)[0]
            ret=int(image_digest(self.flash[:length])==self.flash[372:404])
        elif name=='WDG_SystemReset':
            assert (a,b)==(3,0xd4) and not self.flash[2]&128
            self.resets+=1
        m.reg_write(A.UC_ARM_REG_R0,ret)
        m.reg_write(A.UC_ARM_REG_PC,m.reg_read(A.UC_ARM_REG_LR))
    def call(self,name,data=b''):
        m=self.cpu
        m.mem_write(0x210000,data or b'\0')
        for r,v in ((A.UC_ARM_REG_SP,0x21fff0),(A.UC_ARM_REG_LR,0x1001),
                    (A.UC_ARM_REG_R0,0x210000),(A.UC_ARM_REG_R1,len(data))):
            m.reg_write(r,v)
        m.emu_start(symbols[name]|1,0x1000,count=200000)
        assert m.reg_read(A.UC_ARM_REG_PC)==0x1000
        return m.reg_read(A.UC_ARM_REG_R0)
    def send(self,data): return self.call('r19z_update_packet',data)
    def disconnect(self): self.call('r19z_update_disconnect')

def begin(b,img): return b.send(b'\2'+struct.pack('<I',len(img)))
def chunk(b,pos,data): return b.send(b'\3'+struct.pack('<I',pos)+data)
def upload(b,img,size):
    assert b.send(b'\1'+key) and begin(b,img)
    for pos in range(0,len(img),size): assert chunk(b,pos,img[pos:pos+size])

for image,step in ((blob[80:],15),(stock[80:],480)):
    b=Board(); upload(b,image,step)
    assert b.send(b'\4') and b.protected
    expected=bytearray(image); expected[2]&=127
    assert b.flash[:len(image)]==expected and b.resets==0
    b.disconnect(); assert b.resets==1
b=Board(); img=blob[80:]
assert not b.send(b'\1'+bytes(16)) and not begin(b,img)
assert b.send(b'\1'+key)
b.dual=True; assert not begin(b,img)
b.dual=False; b.overlap=True; assert not begin(b,img)
b.overlap=False; assert begin(b,img)
assert not chunk(b,4,img[:16]) and not b.send(b'\4')
assert chunk(b,0,img[:256]); b.disconnect()
assert not chunk(b,256,img[256:512]) and not b.resets and b.flash[2]&128
assert b.send(b'\1'+key) and begin(b,img)
b.bad_read=True
assert not chunk(b,0,img[:256]) and b.protected and not b.send(b'\4')
b=Board(); damaged=bytearray(img); damaged[-1]^=1
upload(b,damaged,200)
assert not b.send(b'\4') and b.flash[2]&128
b.disconnect(); assert b.resets==0
print('PASS: ARM Libre/stock staging, owner key, bank overlap, dual-bank rejection, offset, partial transfer, read error and damaged image')
