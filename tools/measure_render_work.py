"""Count actual C rendering work on host. This does not measure the watch's speed."""
import ctypes as C
import json
import sys
from pathlib import Path

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'tests'))
from test_watch_core import State
from test_renderer import Canvas,FILL
lib=C.CDLL(str(root/'build/watch_core.dll'))
lib.watch_init.argtypes=[C.POINTER(State),C.c_uint32]
lib.watch_render.argtypes=[C.POINTER(State),C.POINTER(Canvas),C.c_uint,C.c_uint,C.c_uint,C.c_uint]
lib.watch_tick.argtypes=[C.POINTER(State),C.c_uint32,C.c_uint32]
lib.watch_take_dirty.argtypes=[C.POINTER(State)];lib.watch_take_dirty.restype=C.c_uint8
lib.watch_state_bytes.restype=C.c_size_t
s=State();lib.watch_init(C.byref(s),0)
ops=[]
callback=FILL(lambda ctx,x,y,w,h,c:ops.append((w,h,c)))
canvas=Canvas(172,320,callback,None)
def run(dirty,seconds):
    ops.clear()
    lib.watch_render(C.byref(s),C.byref(canvas),dirty,seconds,17,11)
    return {'rectangles':len(ops),'pixel_write_bytes_rgb565':sum(w*h*2 for w,h,c in ops),
            'window_protocol_bytes':len(ops)*11}
full=run(2,45240)
minute=run(1,45300)
lib.watch_tick(C.byref(s),0,45240);lib.watch_take_dirty(C.byref(s))
intermediate=[]
for second in range(1,60):
    lib.watch_tick(C.byref(s),second*1000,45240+second)
    dirty=lib.watch_take_dirty(C.byref(s))
    intermediate.append(run(dirty,45240+second))
report={'state_bytes':lib.watch_state_bytes(),'clock_full':full,'clock_minute_update':minute,
        'intermediate_59_seconds_pixel_bytes':sum(x['pixel_write_bytes_rgb565'] for x in intermediate),
        'scope':'Host callback counters for the actual C renderer, no device CPU, latency or battery measurements.'}
(root/'reports/render-work.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
