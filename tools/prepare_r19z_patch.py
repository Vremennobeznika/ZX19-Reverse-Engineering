"""Offline, same-size patch preparation. No device or transport access.

Checksum correctness does not establish bootability. Only the exact stock image
is accepted; callers must provide the original bytes at every patch location.
No header, length, ROM identity or load-address modifications are supported.
"""
import hashlib
import importlib.util
import struct
from pathlib import Path

STOCK_SHA = '22f94070c13c157048b335e25af21e3421cc0a92c77c6b13f3c8088f88ddd7bd'
BASE = 0x82c000
WRAPPER = 80
HEADER = 1024
spec = importlib.util.spec_from_file_location('r19z_inspector', Path(__file__).with_name('inspect_realtek.py'))
inspector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inspector)


def prepare(source, patches):
    """Return bytes and review manifest; never writes a file.

    patches: iterable of (mapped flash address, expected bytes, replacement bytes).
    All edits are checked against the original, and overlapping edits are rejected.
    """
    if hashlib.sha256(source).hexdigest() != STOCK_SHA:
        raise ValueError('Unknown stock image')
    output = bytearray(source)
    occupied = set()
    entries = []
    for address, expected, replacement in patches:
        if not isinstance(address, int) or isinstance(address, bool):
            raise ValueError('Address must be an integer')
        if not isinstance(expected, bytes) or not isinstance(replacement, bytes):
            raise ValueError('Patch values must be bytes')
        if not expected or len(expected) != len(replacement):
            raise ValueError('Only nonempty same-size patches are supported')
        offset = address - BASE + WRAPPER
        end = offset + len(expected)
        if offset < WRAPPER + HEADER or end > len(source):
            raise ValueError('Patch outside existing payload')
        positions = set(range(offset, end))
        if occupied.intersection(positions):
            raise ValueError('Overlapping patches')
        if source[offset:end] != expected:
            raise ValueError('Expected original bytes mismatch')
        occupied.update(positions)
        output[offset:end] = replacement
        entries.append({'address': hex(address), 'file_offset': offset,
                        'before': expected.hex(), 'after': replacement.hex()})
    output[WRAPPER+372:WRAPPER+404] = inspector.image_digest(output[WRAPPER:])
    struct.pack_into('<I', output, 12, sum(output[WRAPPER:]) & 0xffffffff)
    result = bytes(output)
    checked = inspector.inspect(result)
    if not checked['realtek_sha_matches_stored']:
        raise ValueError('Internal digest verification failed')
    return result, {'source_sha256': STOCK_SHA,
                    'output_sha256': hashlib.sha256(result).hexdigest(),
                    'file_size': len(result), 'patches': entries,
                    'checksum_verified': True, 'hardware_boot_verified': False,
                    'flash_authorized': False,
                    'limitation': 'Existing payload edits only; ABI, code reachability, signatures and recovery are not validated.'}
