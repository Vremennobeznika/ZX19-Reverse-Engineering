import ctypes as C
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class State(C.Structure):
    _fields_ = [('last_ms', C.c_uint32), ('timer_ms', C.c_uint32),
                ('stopwatch_ms', C.c_uint32), ('shown_second', C.c_uint32), ('timer_preset_s',C.c_uint32),
                ('timer_running', C.c_uint8), ('stopwatch_running', C.c_uint8),
                ('alarm_pending', C.c_uint8), ('page', C.c_uint8),
                ('selected', C.c_uint8), ('dirty', C.c_uint8),
                ('notice_count', C.c_uint8), ('notice_head', C.c_uint8),
                ('notices', (C.c_char * 192) * 4)]

class Core(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lib = C.CDLL(str(ROOT / 'build/watch_core.dll'))
        signatures = {
            'watch_init': ([C.POINTER(State), C.c_uint32], None),
            'watch_tick': ([C.POINTER(State), C.c_uint32, C.c_uint32], None),
            'watch_timer_set': ([C.POINTER(State), C.c_uint32, C.c_uint32], C.c_int),
            'watch_timer_toggle': ([C.POINTER(State), C.c_uint32], None),
            'watch_stopwatch_toggle': ([C.POINTER(State), C.c_uint32], None),
            'watch_stopwatch_reset': ([C.POINTER(State), C.c_uint32], None),
            'watch_open': ([C.POINTER(State), C.c_int], None),
            'watch_next': ([C.POINTER(State), C.c_int], None),
            'watch_select': ([C.POINTER(State)], None),
            'watch_notice': ([C.POINTER(State), C.c_char_p, C.c_size_t], C.c_int),
            'watch_take_alarm': ([C.POINTER(State)], C.c_int),
            'watch_deadline_ms': ([C.POINTER(State), C.c_int], C.c_uint32),
            'watch_take_dirty': ([C.POINTER(State)], C.c_uint8),
            'watch_state_bytes': ([], C.c_size_t),
        }
        for name, (args, result) in signatures.items():
            method = getattr(cls.lib, name)
            method.argtypes, method.restype = args, result

    def setUp(self):
        self.s = State()
        self.lib.watch_init(C.byref(self.s), 0)

    def call(self, name, *args):
        return getattr(self.lib, 'watch_' + name)(C.byref(self.s), *args)

    def test_memory_budget_and_abi(self):
        self.assertEqual(self.lib.watch_state_bytes(), C.sizeof(State))
        self.assertLessEqual(C.sizeof(State), 1024)

    def test_timer_expiry_delivers_one_alarm(self):
        self.assertEqual(self.call('timer_set', 2, 0), 1)
        self.call('timer_toggle', 0)
        self.call('tick', 2500, 2)
        self.assertEqual(self.s.timer_ms, 0)
        self.assertEqual(self.s.timer_running, 0)
        self.assertEqual(self.call('take_alarm'), 1)
        self.call('tick', 9000, 9)
        self.assertEqual(self.call('take_alarm'), 0)

    def test_timer_pause_resume_accounts_for_event_time(self):
        self.call('timer_set', 10, 0)
        self.call('timer_toggle', 0)
        self.call('timer_toggle', 1500)
        self.assertEqual(self.s.timer_ms, 8500)
        self.call('timer_toggle', 9000)
        self.call('tick', 10000, 10)
        self.assertEqual(self.s.timer_ms, 7500)

    def test_timer_expiry_refreshes_start_control(self):
        self.call('open',2)
        self.call('timer_set',1,0)
        self.call('timer_toggle',0)
        self.call('take_dirty')
        self.call('tick',1000,1)
        self.assertEqual(self.s.timer_running,0)
        self.assertEqual(self.call('take_dirty'),2)

    def test_invalid_timer_is_non_destructive(self):
        self.call('timer_set', 10, 0)
        before = bytes(self.s)
        for value in (0, 86401, 0xffffffff):
            self.assertEqual(self.call('timer_set', value, 100), 0)
            self.assertEqual(bytes(self.s), before)
        self.assertEqual(self.call('timer_set', 86400, 100), 1)

    def test_counter_wrap(self):
        self.lib.watch_init(C.byref(self.s), 0xffffff00)
        self.call('timer_set', 1, 0xffffff00)
        self.call('timer_toggle', 0xffffff00)
        self.call('tick', 0x100, 0)
        self.assertEqual(self.s.timer_ms, 488)

    def test_stopwatch_pause_reset_and_saturation(self):
        self.call('stopwatch_toggle', 0)
        self.call('stopwatch_toggle', 1234)
        self.call('tick', 5000, 5)
        self.assertEqual(self.s.stopwatch_ms, 1234)
        self.call('stopwatch_reset', 5000)
        self.call('stopwatch_toggle', 5000)
        self.call('tick', 400000000, 10)
        self.assertEqual(self.s.stopwatch_ms, 359999000)
        self.assertEqual(self.s.stopwatch_running, 0)

    def test_utf8_truncation_and_queue_bound(self):
        msg = ('Ч' * 100).encode()
        self.assertEqual(self.call('notice', msg, len(msg)), 1)
        saved = bytes(self.s.notices[0]).split(b'\0', 1)[0]
        self.assertEqual(saved.decode(), 'Ч' * 94 + '...')
        for i in range(7):
            self.assertEqual(self.call('notice', str(i).encode(), 1), 1)
        self.assertEqual(self.s.notice_count, 4)
        self.assertEqual(self.s.notice_head, 0)
        self.assertEqual([bytes(x).split(b'\0',1)[0] for x in self.s.notices], [b'3',b'4',b'5',b'6'])

    def test_malformed_utf8_does_not_destroy_notifications(self):
        self.call('notice', b'hello', 5)
        before = bytes(self.s)
        for msg in (b'\xc0\x80', b'\xed\xa0\x80', b'\xf4\x90\x80\x80', b'\xd0', b'a\0b'):
            self.assertEqual(self.call('notice', msg, len(msg)), 0)
            self.assertEqual(bytes(self.s), before)
        self.assertEqual(self.call('notice', None, 1), 0)

    def test_menu_navigation(self):
        self.call('select')
        self.assertEqual(self.s.page, 1)
        self.call('next', -1)
        self.assertEqual(self.s.selected, 2)
        self.call('select')
        self.assertEqual(self.s.page, 4)
        self.call('open', 100)
        self.assertEqual(self.s.page, 4)

    def test_redraw_is_event_driven(self):
        self.assertEqual(self.call('take_dirty'), 2)
        self.call('tick', 0, 10)
        self.assertEqual(self.call('take_dirty'), 1)
        self.call('tick', 100, 10)
        self.assertEqual(self.call('take_dirty'), 0)
        self.call('tick', 1000, 11)
        self.assertEqual(self.call('take_dirty'), 0)
        self.call('tick', 50000, 60)
        self.assertEqual(self.call('take_dirty'), 1)

    def test_sleep_deadline_does_not_poll_stopwatch_with_screen_off(self):
        self.call('stopwatch_toggle', 0)
        self.assertEqual(self.call('deadline_ms', 0), 0xffffffff)
        self.call('timer_set', 60, 0)
        self.call('timer_toggle', 0)
        self.assertEqual(self.call('deadline_ms', 0), 60000)
        self.assertEqual(self.call('deadline_ms', 1), 1000)

if __name__ == '__main__':
    unittest.main()
