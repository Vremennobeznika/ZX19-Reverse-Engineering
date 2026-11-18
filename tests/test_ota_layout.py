import importlib.util
from pathlib import Path
import struct
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('ota_layout', ROOT / 'tools/find_ota_layout.py')
layout = importlib.util.module_from_spec(spec)
spec.loader.exec_module(layout)


class LayoutTests(unittest.TestCase):
    def fixture(self):
        data = bytearray(4096)
        struct.pack_into('<BBHHHI', data, 0, 9, 0, 0x981, 0x2790, 0, 3072)
        data[12:28] = layout.ROM_UUID
        struct.pack_into('<II', data, 0x1a8, 0x82c000, 0x60000)
        return data

    def test_synthetic_header_app_fields_and_prefix(self):
        result = layout.find_layouts(b'prefix' + self.fixture())
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['file_offset'], '0x6')
        app = result[0]['regions'][2]
        self.assertEqual(app, {'name':'app', 'field_offset':'0x1a8',
                              'address':'0x82c000', 'size':0x60000})
        self.assertFalse(result[0]['active_bank_verified'])

    def test_truncated_header_and_wrong_id_are_not_candidates(self):
        blob = self.fixture()
        self.assertEqual(layout.find_layouts(blob[:-1]), [])
        struct.pack_into('<H', blob, 4, 0x2793)
        self.assertEqual(layout.find_layouts(blob), [])

    def test_stock_application_is_not_a_bank_header(self):
        stock = (ROOT / 'firmware/R19Z_1.00.18_241125.bin').read_bytes()
        self.assertEqual(layout.find_layouts(stock), [])
