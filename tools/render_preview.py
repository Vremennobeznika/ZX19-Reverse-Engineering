"""Capture the actual C renderer to PNG, using a host-only RGB canvas."""
import ctypes as C
import struct
import sys
import zlib
from pathlib import Path

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'tests'))
from test_watch_core import State
from test_renderer import Canvas,FILL

def png(path,width,height,rgb):
    def chunk(kind,data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    rows=b''.join(b'\0'+rgb[y*width*3:(y+1)*width*3] for y in range(height))
    path.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))+
                     chunk(b'IDAT',zlib.compress(rows))+chunk(b'IEND',b''))

lib=C.CDLL(str(root/'build/watch_core.dll'))
lib.watch_init.argtypes=[C.POINTER(State),C.c_uint32]
lib.watch_render.argtypes=[C.POINTER(State),C.POINTER(Canvas),C.c_uint,C.c_uint,C.c_uint,C.c_uint]
lib.watch_notice.argtypes=[C.POINTER(State),C.c_char_p,C.c_size_t]
s=State();lib.watch_init(C.byref(s),0)
message='Привет! Встреча в 15:30. Не забудь ключи.'.encode()
lib.watch_notice(C.byref(s),message,len(message))
s.timer_ms=300000;s.stopwatch_ms=83400
width,height=172,320
sheet_w=5*(width+12)+12
sheet=bytearray([28])*(sheet_w*(height+24)*3)
out=root/'reports/preview';out.mkdir(exist_ok=True)
for page in range(5):
    rgb=bytearray(width*height*3)
    def fill(ctx,x,y,w,h,color):
        pixel=bytes((((color>>11)&31)*255//31,((color>>5)&63)*255//63,(color&31)*255//31))
        for row in range(y,y+h):
            start=(row*width+x)*3
            rgb[start:start+w*3]=pixel*w
    callback=FILL(fill)
    canvas=Canvas(width,height,callback,None)
    s.page=page
    lib.watch_render(C.byref(s),C.byref(canvas),2,45240,17,11)
    png(out/f'page-{page}.png',width,height,bytes(rgb))
    for y in range(height):
        offset=((y+12)*sheet_w+12+page*(width+12))*3
        sheet[offset:offset+width*3]=rgb[y*width*3:(y+1)*width*3]
png(out/'screens.png',sheet_w,height+24,bytes(sheet))
print(out/'screens.png')
