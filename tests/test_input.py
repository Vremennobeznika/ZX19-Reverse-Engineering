import ctypes as C
import unittest
from pathlib import Path
from test_watch_core import State

ROOT=Path(__file__).resolve().parents[1]
class InputTests(unittest.TestCase):
    def setUp(self):
        self.lib=C.CDLL(str(ROOT/'build/watch_core.dll'))
        self.lib.watch_init.argtypes=[C.POINTER(State),C.c_uint32]
        self.lib.watch_tap.argtypes=[C.POINTER(State),C.c_int,C.c_int,C.c_int,C.c_int,C.c_uint32]
        self.lib.watch_button.argtypes=[C.POINTER(State),C.c_int,C.c_uint32]
        self.lib.watch_tick.argtypes=[C.POINTER(State),C.c_uint32,C.c_uint32]
        self.s=State(); self.lib.watch_init(C.byref(self.s),0)
    def tap(self,x,y,now=0):
        return self.lib.watch_tap(C.byref(self.s),172,320,x,y,now)
    def test_clock_menu_timer_pause_resume_home(self):
        self.assertEqual(self.tap(50,100),1)
        self.assertEqual(self.s.page,1)
        self.assertEqual(self.tap(30,70),1)
        self.assertEqual(self.s.page,2)
        self.assertEqual(self.s.timer_ms,300000)
        self.tap(30,260,0)
        self.tap(30,260,1500)
        self.assertEqual(self.s.timer_ms,298500)
        self.assertEqual(self.s.timer_running,0)
        self.tap(30,260,5000)
        self.lib.watch_button(C.byref(self.s),0,6000)
        self.lib.watch_tick(C.byref(self.s),7000,7)
        self.assertEqual(self.s.page,0)
        self.assertEqual(self.s.timer_ms,296500)
    def test_stopwatch_and_explicit_long_button_reset(self):
        self.tap(10,10); self.tap(20,125); self.tap(30,260,0)
        self.assertEqual(self.s.page,3)
        self.lib.watch_tick(C.byref(self.s),1234,1)
        self.assertEqual(self.s.stopwatch_ms,1234)
        self.lib.watch_button(C.byref(self.s),1,1500)
        self.assertEqual(self.s.stopwatch_ms,0)
        self.assertEqual(self.s.stopwatch_running,0)
    def test_invalid_and_gap_taps_do_not_change_state(self):
        before=bytes(self.s)
        self.assertEqual(self.tap(-1,0),0)
        self.assertEqual(self.tap(172,0),0)
        self.assertEqual(bytes(self.s),before)
        self.tap(10,10)
        before=bytes(self.s)
        self.assertEqual(self.tap(20,107),0)
        self.assertEqual(bytes(self.s),before)
    def test_timer_adjustment_is_blocked_while_running(self):
        self.tap(10,10);self.tap(20,70)
        self.assertEqual(self.tap(120,190),1)
        self.assertEqual(self.s.timer_ms,360000)
        self.tap(30,260,0)
        self.assertEqual(self.tap(120,190,100),0)
        self.assertEqual(self.s.timer_preset_s,360)
    def test_expired_timer_restarts_chosen_duration(self):
        self.tap(10,10);self.tap(20,70);self.tap(120,190)
        self.tap(30,260,0)
        self.lib.watch_tick(C.byref(self.s),360000,0)
        self.assertEqual(self.s.timer_ms,0)
        self.tap(30,260,361000)
        self.assertEqual(self.s.timer_ms,360000)
        self.assertEqual(self.s.timer_running,1)
if __name__=='__main__': unittest.main()
