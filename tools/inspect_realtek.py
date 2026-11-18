"""Inspect the downloaded R19Z OTA container. This is NOT a flashing tool."""
import hashlib
import json
import struct
import sys
from pathlib import Path

WRAPPER_SIZE = 0x50
IMAGE_HEADER_SIZE = 1024
ROM_UUID = bytes.fromhex('1d6a69f12f38ea1182a767370a3ca32e')

def image_digest(image):
    """RTL8762D SDK SHA scope, independently matched to prepend_header.exe.

    Excludes control header, digest itself and 256-byte header signature.
    Includes payload MAC at 0x2e0 and header MAC at 0x3f0.
    """
    if len(image) < IMAGE_HEADER_SIZE:
        raise ValueError('Truncated Realtek image')
    return hashlib.sha256(image[12:372] + image[404:752] + image[1008:]).digest()

def inspect(data):
    if len(data) < WRAPPER_SIZE + IMAGE_HEADER_SIZE:
        raise ValueError('Truncated container')
    magic, length1, length2 = struct.unpack_from('<III', data)
    if magic != 0x81BDC3E5:
        raise ValueError('Unrecognized wrapper magic')
    if length1 != length2 or length1 != len(data) - WRAPPER_SIZE:
        raise ValueError('Container size fields do not match file length')
    def text(offset):
        return data[offset:offset+32].split(b'\0', 1)[0].decode('ascii')
    version, hardware = text(0x10), text(0x30)
    if hardware != 'R19Z_V1.0' or not version.startswith('R19Z_'):
        raise ValueError('Not an R19Z_V1.0 container')
    image = data[WRAPPER_SIZE:]
    expected_sum=struct.unpack_from('<I',data,12)[0]
    actual_sum=sum(image)&0xffffffff
    if expected_sum!=actual_sum:
        raise ValueError('Vendor wrapper byte sum mismatch')
    ic, secure, flags, image_id, crc, payload_len = struct.unpack_from('<BBHHHI', image)
    if image_id != 0x2793:
        raise ValueError('Expected AppPatch image ID')
    if payload_len != len(image) - IMAGE_HEADER_SIZE:
        raise ValueError('Image payload size does not match file length')
    exe, load, load_len, base = struct.unpack_from('<4I', image, 28)
    stored_sha = image[372:404]
    payload_sha = hashlib.sha256(image[IMAGE_HEADER_SIZE:]).digest()
    actual_sha = image_digest(image)
    warnings = []
    if ic != 9 or image[12:28] != ROM_UUID:
        warnings.append('ROM identity differs from the matched RTL8762D SDK reference')
    if stored_sha != actual_sha:
        warnings.append('Realtek image SHA256 mismatch')
    warnings.append('Downloaded application image is not a full flash backup or a proven recovery method')
    return {'hardware': hardware, 'version': version, 'file_size': len(data),
            'file_sha256': hashlib.sha256(data).hexdigest(), 'ic_type': ic,
            'wrapper_byte_sum':hex(actual_sum), 'wrapper_byte_sum_matches':True,
            'rom_uuid': image[12:28].hex(), 'image_id': hex(image_id),
            'secure_version': secure, 'flags': hex(flags), 'header_crc16': crc,
            'encrypted_payload_flag': bool(flags & 2),
            'boot_integrity_check_flag': bool(flags & (1 << 9)),
            'image_type': flags >> 13, 'payload_size': payload_len,
            'execute_base': hex(exe), 'load_base': hex(load), 'load_length': load_len,
            'image_base': hex(base), 'stored_sha_field': stored_sha.hex(),
            'sha256_realtek_image': actual_sha.hex(),
            'realtek_sha_matches_stored': stored_sha == actual_sha,
            'sha256_scope': '[12:372] + [404:752] + [1008:image_end], inner image offsets',
            'sha256_payload': payload_sha.hex(), 'payload_sha_matches_stored': stored_sha == payload_sha,
            'warnings': warnings, 'flash_authorized': False}

if __name__ == '__main__':
    p = Path(sys.argv[1])
    result = inspect(p.read_bytes())
    p.with_suffix('.header.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
