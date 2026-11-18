"""Headless Chrome check of the offline time page, with a simulated GATT link."""
from pathlib import Path
import os
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
chrome = Path(os.environ['PROGRAMFILES'])/'Google/Chrome/Application/chrome.exe'
page = (root/'ZX19-time.html').read_text(encoding='utf-8')
mock = """<script>
let disconnects=0, writes=0, reject=false;
const channel={writeValueWithResponse:async p=>{
  if(reject) throw Error('test write failure');
  if(p.length!==16||p[15]!==p.slice(0,15).reduce((a,b)=>(a+b)&255,0)) throw Error('packet');
  writes++;
}};
const device={gatt:{connected:true,disconnect:()=>disconnects++, connect:async()=>({
  getPrimaryService:async s=>{if(s!==service)throw Error('service'); return {
    getCharacteristic:async c=>{if(c!==command)throw Error('command');return channel;}
  };}
})}};
Object.defineProperty(navigator,'bluetooth',{value:{requestDevice:async o=>{
  if(o.filters[0].name!=='ZX19 Libre')throw Error('name');return device;
}}});
</script>"""
check = """<script>
(async()=>{
const p=timePacket(new Date(2024,1,29,23,59,58));
if(String(p.slice(0,7))!=='1,36,2,41,35,89,88')throw Error('BCD');
await button.onclick();if(writes!==1||disconnects!==1||!statusText.textContent.includes('подтвердили'))throw Error('success');
reject=true;await button.onclick();if(writes!==1||disconnects!==2||button.disabled||!statusText.textContent.includes('не удалось'))throw Error('failure');
document.body.setAttribute('data-qa','passed');
})().catch(e=>document.body.setAttribute('data-qa',String(e)));
</script>"""
with tempfile.TemporaryDirectory(dir=root/'build') as tmp:
    path = Path(tmp)/'test.html'
    path.write_text(page.replace('<script>',mock+'<script>',1).replace('</html>',check+'</html>'),encoding='utf-8')
    result = subprocess.run([str(chrome),'--headless','--disable-gpu','--no-first-run',
                             '--user-data-dir='+str(Path(tmp)/'profile'),'--dump-dom',path.as_uri()],
                            capture_output=True,timeout=45,check=True)
    assert b'data-qa="passed"' in result.stdout
print('PASS: Chrome calendar encoding, acknowledged write and failed write. Simulated GATT.')
