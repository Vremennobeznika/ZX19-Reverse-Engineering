"""Read ELF symbols from a local vendor archive for offline fingerprinting."""
import json
import re
import struct
from pathlib import Path
from capstone import Cs,CS_ARCH_ARM,CS_MODE_THUMB

root=Path(__file__).resolve().parents[1]
b=(root/'research/sdk-reference/sbee2_sdk.lib').read_bytes()
pos=8; longnames=b''; found=[]
while pos+60<=len(b):
    header=b[pos:pos+60]; size=int(header[48:58]); member=b[pos+60:pos+60+size]
    name=header[:16].decode().strip()
    if name=='//': longnames=member
    elif name.startswith('/') and name[1:].isdigit():
        start=int(name[1:]); name=longnames[start:].split(b'/\n',1)[0].decode(errors='replace')
    if member[:5]==b'\x7fELF\x01':
        shoff=struct.unpack_from('<I',member,32)[0]
        entsize,count=struct.unpack_from('<HH',member,46)
        sections=[struct.unpack_from('<10I',member,shoff+i*entsize) for i in range(count)]
        for sec in sections:
            if sec[1]!=2: continue
            st=sections[sec[6]]; strings=member[st[4]:st[4]+st[5]]
            for off in range(sec[4],sec[4]+sec[5],sec[9] or 16):
                ni,value,length,info,other,idx=struct.unpack_from('<IIIBBH',member,off)
                if not ni or (info&15)!=2 or not idx or idx>=len(sections): continue
                symbol=strings[ni:].split(b'\0',1)[0].decode(errors='replace')
                if not re.search(r'Pinmux|Pad_Config|IF8080',symbol): continue
                code_section=sections[idx]; codeoff=code_section[4]+(value&~1)
                code=member[codeoff:codeoff+length]
                found.append({'member':name,'symbol':symbol,'size':length,'code_hex':code.hex()})
    pos+=60+size+(size%2)
(root/'research/sdk-function-fingerprints.json').write_text(json.dumps(found,indent=2),encoding='utf-8')
cs=Cs(CS_ARCH_ARM,CS_MODE_THUMB)
lines=[]
for f in found:
    lines.append('\n'+f['symbol']+' ['+f['member']+']')
    lines.extend(f'{i.address:04x} {i.mnemonic} {i.op_str}' for i in cs.disasm(bytes.fromhex(f['code_hex']),0))
(root/'research/sdk-functions-thumb.txt').write_text('\n'.join(lines),encoding='utf-8')
print(json.dumps([{k:v for k,v in f.items() if k!='code_hex'} for f in found],indent=2))
