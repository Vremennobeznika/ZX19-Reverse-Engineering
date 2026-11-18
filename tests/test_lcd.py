import ctypes as C
import json
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
COMMAND=C.CFUNCTYPE(C.c_int,C.c_void_p,C.c_uint8)
DATA=C.CFUNCTYPE(C.c_int,C.c_void_p,C.POINTER(C.c_uint8),C.c_size_t)
DELAY=C.CFUNCTYPE(C.c_int,C.c_void_p,C.c_uint)
class Lcd(C.Structure):
    _fields_=[('context',C.c_void_p),('command',COMMAND),('data',DATA),('fault',C.c_uint8)]
class LcdTests(unittest.TestCase):
    def setUp(self):
        self.lib=C.CDLL(str(ROOT/'build/watch_core.dll'))
        self.lib.watch_lcd_fill.argtypes=[C.POINTER(Lcd),C.c_int,C.c_int,C.c_int,C.c_int,C.c_uint16]
        self.ops=[]; self.fail_at=None
        def command(ctx,n):
            self.ops.append(('command',n)); return len(self.ops)!=self.fail_at
        def data(ctx,p,n):
            self.ops.append(('data',C.string_at(p,n))); return len(self.ops)!=self.fail_at
        self.cmd=COMMAND(command); self.data=DATA(data)
        self.lcd=Lcd(None,self.cmd,self.data,0)
        self.init=self.lib.watch_lcd_init_r19z_first
        self.init.argtypes=[C.POINTER(Lcd),DELAY]
        def delay(ctx,ms):
            self.ops.append(('delay_candidate_ms',ms))
            return len(self.ops)!=self.fail_at
        self.delay=DELAY(delay)
    def test_init_matches_stock_operations(self):
        self.assertEqual(self.init(C.byref(self.lcd),self.delay),1)
        recorded=[]
        for kind,value in self.ops:
            if kind=='data':
                recorded.extend((kind,b) for b in value)
            else:
                recorded.append((kind,value))
        stock=json.loads((ROOT/'research/lcd-init-candidate.json').read_text())
        self.assertEqual(recorded,[(op['kind'],op['value']) for op in stock['operations']])
    def test_reset_before_panel_commands(self):
        start=self.lib.watch_lcd_start_r19z_first
        start.argtypes=[C.POINTER(Lcd),DELAY,DELAY]
        @DELAY
        def mode(ctx,value):
            self.ops.append(('mode',value))
            return len(self.ops)!=self.fail_at
        expected=[('mode',0),('delay_candidate_ms',5),('mode',1),
                  ('delay_candidate_ms',20),('mode',0),('delay_candidate_ms',120)]
        self.assertEqual(start(C.byref(self.lcd),mode,self.delay),1)
        self.assertEqual(self.ops[:7],expected+[('command',0x11)])
        for position in range(1,7):
            self.ops.clear()
            self.fail_at=position
            self.lcd.fault=0
            self.assertEqual(start(C.byref(self.lcd),mode,self.delay),0)
            self.assertEqual(self.ops,expected[:position])
            self.assertEqual(self.lcd.fault,1)
    def test_each_init_failure_stops_bus(self):
        self.assertEqual(self.init(C.byref(self.lcd),self.delay),1)
        for position in range(1,len(self.ops)+1):
            with self.subTest(position=position):
                self.ops.clear()
                self.fail_at=position
                self.lcd.fault=0
                self.assertEqual(self.init(C.byref(self.lcd),self.delay),0)
                self.assertEqual(self.lcd.fault,1)
                self.assertEqual(self.fill(0,0,1,1),0)
                self.assertEqual(len(self.ops),position)
    def fill(self,x,y,w,h,color=0xf800):
        return self.lib.watch_lcd_fill(C.byref(self.lcd),x,y,w,h,color)
    def test_geometry_offset_and_rgb565_byte_order(self):
        self.assertEqual(self.fill(0,0,2,1),1)
        self.assertEqual(self.ops,[('command',0x2a),('data',bytes([0,34,0,35])),
            ('command',0x2b),('data',bytes([0,0,0,0])),('command',0x2c),('data',b'\xf8\x00'*2)])
    def test_clipping_and_bounded_transfer(self):
        self.assertEqual(self.fill(170,319,0x7fffffff,0x7fffffff),1)
        self.assertEqual(self.ops[1],('data',bytes([0,204,0,205])))
        self.assertEqual(self.ops[3],('data',bytes([1,63,1,63])))
        self.assertEqual(len(self.ops[-1][1]),4)
    def test_empty_and_offscreen_emit_nothing(self):
        for rectangle in ((0,0,0,1),(-100,0,5,1),(172,0,1,1),(-2147483648,0,2147483647,1)):
            self.assertEqual(self.fill(*rectangle),1)
        self.assertEqual(self.ops,[])
    def test_transport_failure_latches_and_does_not_retry(self):
        self.fail_at=2
        self.assertEqual(self.fill(0,0,1,1),0)
        self.assertEqual(self.lcd.fault,1)
        self.assertEqual(len(self.ops),2)
        self.assertEqual(self.fill(0,0,1,1),0)
        self.assertEqual(len(self.ops),2)
    def test_chunk_budget(self):
        self.assertEqual(self.fill(0,0,172,320),1)
        chunks=[payload for kind,payload in self.ops[5:] if kind=='data']
        self.assertEqual(sum(map(len,chunks)),172*320*2)
        self.assertLessEqual(max(map(len,chunks)),64)
if __name__=='__main__': unittest.main()
