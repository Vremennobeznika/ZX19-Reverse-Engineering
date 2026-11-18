import importlib.util
import struct
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('inspect_realtek', ROOT / 'tools/inspect_realtek.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class FirmwareInspection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = (ROOT / 'firmware/R19Z_1.00.18_241125.bin').read_bytes()

    def test_downloaded_identity_and_hash(self):
        r = module.inspect(self.original)
        self.assertEqual(r['file_sha256'], '22f94070c13c157048b335e25af21e3421cc0a92c77c6b13f3c8088f88ddd7bd')
        self.assertEqual(r['hardware'], 'R19Z_V1.0')
        self.assertEqual(r['version'], 'R19Z_1.00.18_241125')
        self.assertEqual(r['ic_type'], 9)
        self.assertEqual(r['rom_uuid'], module.ROM_UUID.hex())

    def test_truncation_rejected(self):
        for end in (0, 79, 80, 1103, len(self.original)-1):
            with self.subTest(end=end), self.assertRaises(ValueError):
                module.inspect(self.original[:end])

    def test_bad_magic_rejected(self):
        b = bytearray(self.original)
        b[0] ^= 1
        with self.assertRaises(ValueError):
            module.inspect(b)

    def test_wrong_hardware_rejected(self):
        b = bytearray(self.original)
        b[0x30] = ord('X')
        with self.assertRaises(ValueError):
            module.inspect(b)

    def test_payload_length_mismatch_rejected(self):
        b = bytearray(self.original)
        struct.pack_into('<I', b, 0x58, 0xFFFFFFFF)
        struct.pack_into('<I',b,12,sum(b[0x50:])&0xffffffff)
        with self.assertRaisesRegex(ValueError,'payload size'):
            module.inspect(b)

    def test_wrong_image_id_rejected(self):
        b = bytearray(self.original)
        struct.pack_into('<H', b, 0x54, 0x2791)
        struct.pack_into('<I',b,12,sum(b[0x50:])&0xffffffff)
        with self.assertRaisesRegex(ValueError,'AppPatch'):
            module.inspect(b)

    def test_rom_difference_is_reported(self):
        b = bytearray(self.original)
        b[0x5c] ^= 1
        struct.pack_into('<I',b,12,sum(b[0x50:])&0xffffffff)
        self.assertTrue(any('ROM identity differs' in s for s in module.inspect(b)['warnings']))

    def test_payload_corruption_rejected_by_vendor_byte_sum(self):
        b=bytearray(self.original)
        b[0x1000]^=1
        with self.assertRaisesRegex(ValueError,'byte sum'):
            module.inspect(b)

    def test_realtek_hash_scope_matches_stock(self):
        r = module.inspect(self.original)
        self.assertFalse(r['payload_sha_matches_stored'])
        self.assertTrue(r['realtek_sha_matches_stored'])
        self.assertEqual(r['sha256_realtek_image'], '993c94d2c4be45bff9cc8d80a1a1de545cade9ecd3c3674afc307a3378166ddd')
        self.assertFalse(r['flash_authorized'])
        self.assertFalse(any('SHA' in s for s in r['warnings']))

    def test_sha_detects_payload_corruption_even_after_outer_sum_repaired(self):
        b = bytearray(self.original)
        b[0x1000] ^= 1
        struct.pack_into('<I', b, 12, sum(b[0x50:]) & 0xffffffff)
        r = module.inspect(b)
        self.assertFalse(r['realtek_sha_matches_stored'])
        self.assertIn('Realtek image SHA256 mismatch', r['warnings'])

    def test_hash_covered_header_corruption_detected(self):
        b = bytearray(self.original)
        b[0x50 + 100] ^= 1
        struct.pack_into('<I', b, 12, sum(b[0x50:]) & 0xffffffff)
        self.assertFalse(module.inspect(b)['realtek_sha_matches_stored'])

    def test_sha_field_excluded_from_its_own_hash(self):
        image = bytearray(self.original[0x50:])
        expected = module.image_digest(image)
        image[372:404] = bytes(32)
        self.assertEqual(module.image_digest(image), expected)

    def test_hash_rejects_truncated_header(self):
        with self.assertRaises(ValueError):
            module.image_digest(bytes(1023))

if __name__ == '__main__':
    unittest.main()
