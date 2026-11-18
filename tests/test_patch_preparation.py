import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('patcher', ROOT / 'tools/prepare_r19z_patch.py')
patcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patcher)


class PatchPreparation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stock = (ROOT / 'firmware/R19Z_1.00.18_241125.bin').read_bytes()
        cls.address = 0x82c400
        cls.original = cls.stock[1104:1108]
        cls.changed = bytes([cls.original[0] ^ 1]) + cls.original[1:]

    def test_identity_roundtrip(self):
        result, manifest = patcher.prepare(self.stock, [])
        self.assertEqual(result, self.stock)
        self.assertTrue(manifest['checksum_verified'])
        self.assertFalse(manifest['hardware_boot_verified'])

    def test_mutation_changes_only_requested_bytes_and_checksums(self):
        result, manifest = patcher.prepare(self.stock, [(self.address, self.original, self.changed)])
        allowed = set(range(12, 16)) | set(range(452, 484)) | set(range(1104, 1108))
        differences = {i for i, (a, b) in enumerate(zip(self.stock, result)) if a != b}
        self.assertTrue(differences <= allowed)
        self.assertIn(1104, differences)
        self.assertEqual(len(result), len(self.stock))
        self.assertTrue(patcher.inspector.inspect(result)['realtek_sha_matches_stored'])
        self.assertFalse(manifest['flash_authorized'])

    def test_unknown_source_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Unknown stock'):
            patcher.prepare(self.stock[:-1], [])

    def test_bad_patch_rejected(self):
        cases = [
            (0x82c000, self.original, self.changed),
            (0x900000, self.original, self.changed),
            (self.address, b'', b''),
            (self.address, self.original, self.changed + b'\0'),
            (self.address, self.changed, self.original),
            ('0x82c400', self.original, self.changed),
        ]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                patcher.prepare(self.stock, [case])

    def test_overlap_rejected(self):
        entry = (self.address, self.original, self.changed)
        with self.assertRaisesRegex(ValueError, 'Overlapping'):
            patcher.prepare(self.stock, [entry, entry])

    def test_last_payload_byte_supported(self):
        address = patcher.BASE + len(self.stock) - patcher.WRAPPER - 1
        result, _ = patcher.prepare(self.stock, [(address, self.stock[-1:], bytes([self.stock[-1] ^ 1]))])
        self.assertEqual(result[-1], self.stock[-1] ^ 1)
