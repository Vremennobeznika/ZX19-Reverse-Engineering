import ctypes as C
import unittest
from pathlib import Path
from test_watch_core import State
from test_renderer import Canvas, FILL

ROOT = Path(__file__).resolve().parents[1]


class StripTests(unittest.TestCase):
    def setUp(self):
        self.lib = C.CDLL(str(ROOT / 'build/watch_core.dll'))
        self.lib.watch_init.argtypes = [C.POINTER(State), C.c_uint32]
        self.lib.watch_render.argtypes = [C.POINTER(State), C.POINTER(Canvas),
                                         C.c_uint, C.c_uint, C.c_uint, C.c_uint]
        self.lib.watch_render_strip.argtypes = [C.POINTER(State), C.POINTER(C.c_uint16),
                                               C.c_size_t, C.c_uint, C.c_uint, C.c_uint, C.c_uint]
        self.state = State()
        self.lib.watch_init(C.byref(self.state), 0)

    def test_all_pages_match_full_renderer_pixel_for_pixel(self):
        for page in range(5):
            with self.subTest(page=page):
                self.state.page = page
                full = [0x1234] * (172 * 320)
                def fill(ctx, x, y, w, h, color):
                    for row in range(y, y+h):
                        full[row*172+x:row*172+x+w] = [color]*w
                callback = FILL(fill)
                canvas = Canvas(172, 320, callback, None)
                self.lib.watch_render(C.byref(self.state), C.byref(canvas), 2, 45240, 17, 11)
                assembled = []
                before = bytes(self.state)
                for first_row in range(0, 320, 10):
                    guarded = (C.c_uint16 * 1722)(*([0x1234]*1722))
                    target = C.cast(C.byref(guarded, 2), C.POINTER(C.c_uint16))
                    self.assertEqual(self.lib.watch_render_strip(C.byref(self.state), target, 1720,
                                                                first_row, 45240, 17, 11), 1)
                    self.assertEqual(guarded[0], 0x1234)
                    self.assertEqual(guarded[-1], 0x1234)
                    assembled.extend(guarded[1:-1])
                self.assertEqual(assembled, full)
                self.assertEqual(bytes(self.state), before)

    def test_bad_dimensions_do_not_write(self):
        buffer = (C.c_uint16 * 1720)(*([0x5678]*1720))
        for capacity, row in ((1719, 0), (0, 0), (1720, 1), (1720, 311),
                              (1720, 320), (1720, 0xffffffff)):
            self.assertEqual(self.lib.watch_render_strip(C.byref(self.state), buffer, capacity,
                                                        row, 0, 1, 1), 0)
        self.assertEqual(list(buffer), [0x5678]*1720)

    def test_null_arguments_rejected(self):
        buffer = (C.c_uint16 * 1720)()
        self.assertEqual(self.lib.watch_render_strip(None, buffer, 1720, 0, 0, 1, 1), 0)
        self.assertEqual(self.lib.watch_render_strip(C.byref(self.state), None, 1720, 0, 0, 1, 1), 0)
