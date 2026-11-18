"""Validate actual viewport geometry and WASM flows in isolated headless Chrome."""
import base64
import json
import os
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
import websocket

root=Path(__file__).resolve().parents[1]
chrome=Path(os.environ.get('PROGRAMFILES','C:/Program Files'))/'Google/Chrome/Application/chrome.exe'
if not chrome.exists(): raise SystemExit('Chrome not found')
profile=Path(tempfile.mkdtemp(prefix='preview-cdp-',dir=root/'build'))
stderr=(root/'build/browser-cdp-stderr.txt').open('wb')
proc=subprocess.Popen([str(chrome),'--headless','--disable-gpu','--no-first-run',
    '--no-default-browser-check','--disable-background-networking','--remote-debugging-address=127.0.0.1',
    '--remote-debugging-port=0','--user-data-dir='+str(profile),'about:blank'],
    stdout=subprocess.DEVNULL,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW)
ws=None;results=[];sequence=0
def call(method,params=None):
    global sequence
    sequence+=1
    ws.send(json.dumps({'id':sequence,'method':method,'params':params or {}}))
    while True:
        result=json.loads(ws.recv())
        if result.get('id')==sequence:
            if 'error' in result: raise RuntimeError(result['error'])
            return result.get('result',{})
def evaluate(expression):
    result=call('Runtime.evaluate',{'expression':expression,'returnByValue':True})
    if 'exceptionDetails' in result: raise RuntimeError(result['exceptionDetails'])
    return result.get('result',{}).get('value')
def tap_canvas(x,y):
    r=evaluate('(()=>{const r=document.getElementById("screen").getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height}})()')
    px=r['x']+x*r['w']/172;py=r['y']+y*r['h']/320
    call('Input.dispatchMouseEvent',{'type':'mouseMoved','x':px,'y':py})
    call('Input.dispatchMouseEvent',{'type':'mousePressed','x':px,'y':py,'button':'left','buttons':1,'clickCount':1})
    call('Input.dispatchMouseEvent',{'type':'mouseReleased','x':px,'y':py,'button':'left','buttons':0,'clickCount':1})
try:
    deadline=time.monotonic()+12
    port_file=profile/'DevToolsActivePort'
    while not port_file.exists():
        if proc.poll() is not None or time.monotonic()>deadline: raise RuntimeError('Chrome did not start')
        time.sleep(.1)
    port=port_file.read_text().splitlines()[0]
    with urllib.request.urlopen('http://127.0.0.1:'+port+'/json/list',timeout=5) as r:
        pages=json.load(r)
    target=next(p for p in pages if p['type']=='page')
    ws=websocket.create_connection(target['webSocketDebuggerUrl'],timeout=10,suppress_origin=True)
    call('Page.enable')
    for name,width,height in [('desktop',980,850),('narrow',360,800)]:
        call('Emulation.setDeviceMetricsOverride',{'width':width,'height':height,
             'deviceScaleFactor':1,'mobile':name=='narrow'})
        call('Page.navigate',{'url':(root/'ZX19-preview.html').as_uri()+'#test'})
        deadline=time.monotonic()+10
        while True:
            ready=evaluate('document.body && document.body.dataset.previewReady')
            test=evaluate('document.body && document.body.dataset.selfTest')
            if ready=='true' and test in ('passed','failed'): break
            if time.monotonic()>deadline: raise RuntimeError('Preview failed to initialize')
            time.sleep(.1)
        geometry=evaluate('({innerWidth:innerWidth,clientWidth:document.documentElement.clientWidth,scrollWidth:document.documentElement.scrollWidth})')
        tap_canvas(40,100)
        menu=evaluate('api.ui_page()')==1
        tap_canvas(30,70)
        timer=evaluate('api.ui_page()')==2
        tap_canvas(30,260)
        initial_timer=evaluate('api.ui_timer_ms()')
        time.sleep(.3)
        remaining=evaluate('api.ui_timer_ms()')
        pointer_flow=menu and timer and 0<remaining<initial_timer<=300000
        evaluate('api.ui_init(Math.floor(performance.now())>>>0);draw();true')
        dom=evaluate('document.documentElement.outerHTML')
        (root/f'build/browser-{name}-dom.html').write_text(dom,encoding='utf-8')
        capture=call('Page.captureScreenshot',{'format':'png','captureBeyondViewport':False})
        (root/f'reports/preview/browser-{name}.png').write_bytes(base64.b64decode(capture['data']))
        row={'requested_viewport':[width,height],'actual_geometry':geometry,'ready':ready=='true',
             'self_test_passed':test=='passed','no_horizontal_overflow':geometry['scrollWidth']<=geometry['clientWidth'],
             'pointer_flow_passed':pointer_flow,
             'viewport_matches':geometry['innerWidth']==width,'screenshot':f'reports/preview/browser-{name}.png'}
        results.append(row);print(json.dumps(row))
finally:
    if ws:
        try: call('Browser.close')
        except Exception: pass
        ws.close()
    try: proc.wait(timeout=8)
    except subprocess.TimeoutExpired: proc.terminate();proc.wait(timeout=5)
    stderr.close()
(root/'reports/browser-tests.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
if len(results)!=2 or not all(r['ready'] and r['self_test_passed'] and r['pointer_flow_passed'] and r['no_horizontal_overflow'] and r['viewport_matches'] for r in results):
    raise SystemExit('Browser preview check failed')
