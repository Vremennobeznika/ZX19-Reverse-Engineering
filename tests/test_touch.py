import ctypes as C
import unittest
from pathlib import Path
from test_watch_core import State

ROOT=Path(__file__).resolve().parents[1]
READ=C.CFUNCTYPE(C.c_int,C.c_void_p,C.c_uint8,C.c_uint8,C.POINTER(C.c_uint8),C.c_size_t)
class Bus(C.Structure): _fields_=[('context',C.c_void_p),('read',READ),('chip_id',C.c_uint8)]
class Sample(C.Structure): _fields_=[('x',C.c_uint16),('y',C.c_uint16),('fingers',C.c_uint8),('gesture',C.c_uint8)]
class Session(C.Structure):
    _fields_=[('started_ms',C.c_uint32),('start_x',C.c_uint16),('start_y',C.c_uint16),
      ('last_x',C.c_uint16),('last_y',C.c_uint16),('max_dx',C.c_uint16),('max_dy',C.c_uint16),('active',C.c_uint8)]
class TouchTests(unittest.TestCase):
    def setUp(self):
        self.lib=C.CDLL(str(ROOT/'build/watch_core.dll'))
        self.lib.watch_init.argtypes=[C.POINTER(State),C.c_uint32]
        self.lib.watch_touch_probe.argtypes=[C.POINTER(Bus)]
        self.lib.watch_touch_read.argtypes=[C.POINTER(Bus),C.POINTER(Sample)]
        self.lib.watch_touch_apply.argtypes=[C.POINTER(State),C.POINTER(Session),C.POINTER(Sample),C.c_uint32]
        self.lib.watch_touch_cancel.argtypes=[C.POINTER(Session)]
        self.state=State();self.session=Session();self.lib.watch_init(C.byref(self.state),0)
        self.calls=[];self.id=0xb4;self.fail=False;self.frame=bytes([0,1,0,50,0,100])
        def read(ctx,addr,reg,p,n):
            self.calls.append((addr,reg,n))
            if self.fail:return 0
            b=bytes([self.id]) if reg==0xa7 else self.frame
            if len(b)!=n:return 0
            C.memmove(p,b,n);return 1
        self.reader=READ(read);self.bus=Bus(None,self.reader,0)
    def apply(self,x,y,fingers,now):
        p=Sample(x,y,fingers,0)
        return self.lib.watch_touch_apply(C.byref(self.state),C.byref(self.session),C.byref(p),now)
    def test_unknown_id_fails_closed(self):
        self.id=0x99
        self.assertEqual(self.lib.watch_touch_probe(C.byref(self.bus)),0)
        self.assertEqual(self.bus.chip_id,0)
        self.assertEqual(self.lib.watch_touch_read(C.byref(self.bus),C.byref(Sample())),0)
        self.assertEqual(self.calls,[(0x15,0xa7,1)])
    def test_known_id_and_coordinates(self):
        for chip in (0xb4,0xb5,0xb6):
            self.id=chip
            self.assertEqual(self.lib.watch_touch_probe(C.byref(self.bus)),1)
            self.assertEqual(self.bus.chip_id,chip)
        sample=Sample()
        self.frame=bytes([5,1,0x80,171,0x81,63])
        self.assertEqual(self.lib.watch_touch_read(C.byref(self.bus),C.byref(sample)),1)
        self.assertEqual((sample.x,sample.y),(171,319))
        self.assertEqual(self.calls[-1],(0x15,1,6))
    def test_bus_failure_and_bad_coordinates_do_not_publish_sample(self):
        self.lib.watch_touch_probe(C.byref(self.bus));sample=Sample(42,43,0,0)
        for frame in (bytes([0,1,0,172,0,20]),bytes([0,2,0,50,0,20])):
            self.frame=frame
            self.assertEqual(self.lib.watch_touch_read(C.byref(self.bus),C.byref(sample)),0)
            self.assertEqual((sample.x,sample.y),(42,43))
        self.fail=True
        self.assertEqual(self.lib.watch_touch_read(C.byref(self.bus),C.byref(sample)),0)
    def test_tap_on_release_occurs_once(self):
        self.assertEqual(self.apply(20,80,1,100),0)
        self.assertEqual(self.apply(20,80,0,200),1)
        self.assertEqual(self.state.page,1)
        self.assertEqual(self.apply(20,80,0,250),0)
    def test_cancel_prevents_ghost_tap(self):
        self.apply(20,80,1,100)
        self.lib.watch_touch_cancel(C.byref(self.session))
        self.assertEqual(self.apply(20,80,0,200),0)
        self.assertEqual(self.state.page,0)
    def test_vertical_swipe_and_drag_return(self):
        self.state.page=1
        self.apply(40,70,1,0);self.apply(40,120,1,100)
        self.assertEqual(self.apply(40,120,0,150),1)
        self.assertEqual(self.state.selected,1)
        self.apply(40,70,1,200);self.apply(90,70,1,250);self.apply(40,70,1,300)
        self.assertEqual(self.apply(40,70,0,350),0)
        self.assertEqual(self.state.page,1)
    def test_long_hold_is_not_tap_and_wrap_is_supported(self):
        self.apply(20,70,1,0)
        self.assertEqual(self.apply(20,70,0,1000),0)
        self.apply(20,70,1,0xfffffff0)
        self.assertEqual(self.apply(20,70,0,50),1)
if __name__=='__main__':unittest.main()
