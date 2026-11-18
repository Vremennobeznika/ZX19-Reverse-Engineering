"""Check the production installer against independently encoded wire frames in Chrome."""
import base64
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
image=(root/'firmware/ZX19-Libre-0.2.0-dev-R19Z_V1.0.bin').read_bytes()
def crc(data):
    value=65535
    for b in data:
        value^=b
        for _ in range(8):
            value=(value>>1)^(0xa001 if value&1 else 0)
    return value
def frame(command,data=b''):
    return struct.pack('<BBHH',188,command,len(data),crc(data))+data
requests=[frame(7),frame(1),frame(2,struct.pack('<BIHH',1,len(image),crc(image),sum(image)&65535))]
for i in range(0,len(image),1024):
    requests.append(frame(3,struct.pack('<H',i//1024+1)+image[i:i+1024]))
requests.extend((frame(4),frame(5)))
response={cmd:frame(cmd,bytes(6 if cmd==7 else 1)).hex() for cmd in (1,2,3,4,7)}
assert response[7]=='bc070600001b000000000000'
test="""<script>
(async()=>{
const seq=REQUESTS, responses=RESPONSES;
const fromHex=s=>Uint8Array.from(s.match(/../g),v=>parseInt(v,16));
const bytes=Uint8Array.from(atob('IMAGE'),x=>x.charCodeAt(0));
Object.defineProperty(byId('imageFile'),'files',{value:[new File([bytes],'test.bin')]});
let index,buffer,handler,scenario,writeCount;
const radio={
connected:true,async connect(){this.connected=true;return this},disconnect(){this.connected=false},
async getPrimaryService(){return this},async getCharacteristic(id){
 if(id.endsWith('_string'))return {readValue:async()=>new DataView(new TextEncoder().encode(
 id==='hardware_revision_string'?(scenario==='wrong'?'OTHER':'R19Z_V1.0'):'R19Z_1.00.18_241125').buffer)};
 return this;
},async startNotifications(){},addEventListener(type,cb){if(type==='characteristicvaluechanged')handler=cb},
removeEventListener(){},async writeValueWithResponse(part){
 writeCount++;const expected=fromHex(seq[index]);
 if(part.length>20||!part.every((v,i)=>v===expected[buffer+i]))throw Error('frame mismatch');
 buffer+=part.length;
 if(buffer!==expected.length)return;
 const cmd=expected[1];index++;buffer=0;
 if(cmd===5)return;
 const ack=fromHex(responses[cmd]);
 if(scenario==='badack'&&cmd===3)ack[4]^=1;
 if(scenario==='busy'&&cmd===7){ack[7]=1;new DataView(ack.buffer).setUint16(4,crc(ack.subarray(6)),true)}
 for(const chunk of [ack.slice(0,3),ack.slice(3)])handler({target:{value:new DataView(chunk.buffer)}});
}};
const device={gatt:radio,addEventListener(){},removeEventListener(){}};
Object.defineProperty(navigator,'bluetooth',{value:{requestDevice:async()=>device}});
for(const mode of ['success','wrong','badack','busy','badfile']){
 scenario=mode;index=buffer=writeCount=0;
 if(mode==='badfile'){
   const altered=bytes.slice();altered[100]^=1;
   byId('imageFile').files[0]=new File([altered],'wrong.bin');
 }
 await run(false);
 if(index!==({success:seq.length,wrong:0,badack:4,busy:1,badfile:0})[mode]||
    (mode==='success'?!note.textContent.includes('Образ передан'):!note.textContent.includes('не подтверждены')))
    throw Error(mode+' '+index+' '+note.textContent);
}
await run(true);if(!note.textContent.includes('запустили Libre'))throw Error('boot check');
document.body.dataset.qa='passed';
})().catch(e=>document.body.dataset.qa=String(e))
</script>""".replace('REQUESTS',json.dumps([s.hex() for s in requests])).replace(
    'RESPONSES',json.dumps(response)).replace('IMAGE',base64.b64encode(image).decode())
with tempfile.TemporaryDirectory(dir=root/'build',ignore_cleanup_errors=True) as tmp:
    page=Path(tmp)/'test.html'
    page.write_text((root/'ZX19-install.html').read_text(encoding='utf-8').replace('</html>',test+'</html>'),encoding='utf-8')
    result=subprocess.run([str(Path(os.environ['PROGRAMFILES'])/'Google/Chrome/Application/chrome.exe'),
                           '--headless','--disable-gpu','--no-first-run','--user-data-dir='+str(Path(tmp)/'profile'),
                           '--virtual-time-budget=20000','--dump-dom',page.as_uri()],capture_output=True,timeout=50,check=True)
    if b'data-qa="passed"' not in result.stdout:
        import re
        raise AssertionError(re.findall(rb'<body[^>]*>|<output[^>]*>[^<]*',result.stdout))
print('PASS Chrome simulated GATT: complete transfer, identity, damaged ACK, busy, damaged file, boot-service check')
