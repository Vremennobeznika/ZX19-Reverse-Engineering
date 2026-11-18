import ctypes as C
import unittest
from pathlib import Path
from test_watch_core import State

ROOT = Path(__file__).resolve().parents[1]
FILL = C.CFUNCTYPE(None,C.c_void_p,C.c_int,C.c_int,C.c_int,C.c_int,C.c_uint16)
class Canvas(C.Structure):
    _fields_=[('width',C.c_int),('height',C.c_int),('fill',FILL),('context',C.c_void_p)]

class Renderer(unittest.TestCase):
    def setUp(self):
        self.lib=C.CDLL(str(ROOT/'build/watch_core.dll'))
        self.lib.watch_init.argtypes=[C.POINTER(State),C.c_uint32]
        self.lib.watch_render.argtypes=[C.POINTER(State),C.POINTER(Canvas),C.c_uint,C.c_uint,C.c_uint,C.c_uint]
        self.s=State()
        self.lib.watch_init(C.byref(self.s),0)
        self.ops=[]
        self.callback=FILL(lambda ctx,x,y,w,h,color:self.ops.append((x,y,w,h,color)))

    def render(self,width=172,height=320,dirty=2):
        canvas=Canvas(width,height,self.callback,None)
        self.lib.watch_render(C.byref(self.s),C.byref(canvas),dirty,45240,17,11)

    def test_all_screens_stay_inside_viewport(self):
        for width,height in ((172,320),(128,200),(240,320)):
            for page in range(5):
                self.s.page=page
                self.ops=[]
                self.render(width,height)
                self.assertTrue(self.ops)
                for x,y,w,h,_ in self.ops:
                    self.assertGreaterEqual(x,0)
                    self.assertGreaterEqual(y,0)
                    self.assertGreater(w,0)
                    self.assertGreater(h,0)
                    self.assertLessEqual(x+w,width)
                    self.assertLessEqual(y+h,height)

    def test_clean_screen_emits_no_commands(self):
        self.render(dirty=0)
        self.assertEqual(self.ops,[])

    def test_value_update_avoids_full_screen_clear(self):
        for page in (0,2,3):
            self.s.page=page
            self.ops=[]
            self.render(dirty=1)
            self.assertTrue(self.ops)
            self.assertFalse(any(w==172 and h==320 for x,y,w,h,c in self.ops))

    def test_invalid_viewport_is_rejected(self):
        for width,height in ((0,0),(127,320),(172,199),(1025,320)):
            self.render(width,height)
        self.assertEqual(self.ops,[])

    def test_notification_render_with_unsupported_unicode(self):
        msg='Сообщение: Привет 🌍'.encode()
        self.lib.watch_notice.argtypes=[C.POINTER(State),C.c_char_p,C.c_size_t]
        self.assertEqual(self.lib.watch_notice(C.byref(self.s),msg,len(msg)),1)
        self.s.page=4
        self.render()
        self.assertTrue(self.ops)

    def test_region_matches_cropped_full_render_including_wrapped_text(self):
        self.lib.watch_render_region.argtypes = [C.POINTER(State), C.POINTER(Canvas),
            C.c_uint, C.c_uint, C.c_uint, C.c_uint, C.c_int, C.c_int]
        self.lib.watch_notice.argtypes = [C.POINTER(State), C.c_char_p, C.c_size_t]
        message = ('Длинное сообщение со словами и переносами строк. ' * 3).encode()
        self.lib.watch_notice(C.byref(self.s), message, len(message))
        for page in range(5):
            self.s.page = page
            self.ops = []
            self.render()
            full = list(self.ops)
            for top, bottom in ((0, 1), (17, 28), (70, 101), (145, 213), (319, 320)):
                with self.subTest(page=page, top=top, bottom=bottom):
                    self.ops = []
                    canvas = Canvas(172, 320, self.callback, None)
                    self.lib.watch_render_region(C.byref(self.s), C.byref(canvas),
                                                2, 45240, 17, 11, top, bottom)
                    expected = []
                    for x,y,w,h,color in full:
                        a,b = max(y,top), min(y+h,bottom)
                        if a < b: expected.append((x,a,w,b-a,color))
                    self.assertEqual(self.ops, expected)

    def test_invalid_region_emits_no_commands(self):
        self.lib.watch_render_region.argtypes = [C.POINTER(State), C.POINTER(Canvas),
            C.c_uint, C.c_uint, C.c_uint, C.c_uint, C.c_int, C.c_int]
        canvas = Canvas(172, 320, self.callback, None)
        for top,bottom in ((-1,10), (0,321), (10,10), (20,10)):
            self.lib.watch_render_region(C.byref(self.s), C.byref(canvas),
                                        2, 45240, 17, 11, top, bottom)
        self.assertEqual(self.ops, [])

if __name__=='__main__':
    unittest.main()
