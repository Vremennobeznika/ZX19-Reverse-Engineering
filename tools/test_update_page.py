"""Drive the recovery page in Chrome with simulated files and an acknowledged GATT link."""
import base64
import os
from pathlib import Path
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
chrome=Path(os.environ['PROGRAMFILES'])/'Google/Chrome/Application/chrome.exe'
page=(root/'ZX19-update.html').read_text(encoding='utf-8')
image=base64.b64encode((root/'firmware/ZX19-Libre-0.2.0-dev-R19Z_V1.0.bin').read_bytes()).decode()
test="""<script>
(async()=>{
const bytes=Uint8Array.from(atob('IMAGE'),x=>x.charCodeAt(0));
const inputFiles=(el,blob)=>Object.defineProperty(el,'files',{configurable:true,value:[blob]});
inputFiles(key,new File(['11'.repeat(16)],'test.key'));
inputFiles(file,new File([bytes],'test.bin'));
let offset=0,committed=false,closes=0,refuse=false;
const gatt={connected:false,disconnect(){this.connected=false;closes++},async connect(){this.connected=true;return this},
async getPrimaryService(s){if(s!==service)throw Error('service');return this},
async getCharacteristic(c){if(c!==update)throw Error('char');return this},async writeValueWithResponse(p){
if(refuse)throw Error('rejected');
switch(p[0]){
case 1: if(p.length!==17)throw Error('owner');break;
case 2: if(u32(p,1)!==bytes.length-80)throw Error('size');break;
case 3: if(u32(p,1)!==offset||p.length>20||!p.slice(5).every((x,i)=>x===bytes[80+offset+i]))throw Error('data');
offset+=p.length-5;break;
case 4: if(offset!==bytes.length-80)throw Error('incomplete');committed=true;break;
default:throw Error('opcode')
}}};
Object.defineProperty(navigator,'bluetooth',{value:{requestDevice:async()=>({gatt})}});
await send.onclick();if(!committed||closes!==1||!status.textContent.includes('подтвердили'))throw Error(status.textContent);
refuse=true;await send.onclick();if(closes!==2||!status.textContent.includes('rejected'))throw Error('failure');
bytes[1200]^=1;inputFiles(file,new File([bytes],'bad.bin'));await send.onclick();
if(closes!==2||!status.textContent.includes('контейнер')||send.disabled)throw Error('corruption');
document.body.dataset.qa='passed';
})().catch(e=>document.body.dataset.qa=String(e));
</script>""".replace('IMAGE',image)
with tempfile.TemporaryDirectory(dir=root/'build',ignore_cleanup_errors=True) as tmp:
    path=Path(tmp)/'test.html'
    path.write_text(page.replace('</html>',test+'</html>'),encoding='utf-8')
    result=subprocess.run([str(chrome),'--headless','--disable-gpu','--no-first-run',
                           '--virtual-time-budget=15000','--user-data-dir='+str(Path(tmp)/'profile'),
                           '--dump-dom',path.as_uri()],capture_output=True,timeout=50,check=True)
    if b'data-qa="passed"' not in result.stdout:
        import re
        raise AssertionError(re.findall(rb'<body[^>]*>|<output[^>]*>[^<]*',result.stdout))
print('PASS: Chrome transmitted exact bytes; handled rejected write and corrupt file. GATT simulated.')
