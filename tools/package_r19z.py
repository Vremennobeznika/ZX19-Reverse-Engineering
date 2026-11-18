"""Build the ZX19 Libre application OTA file for R19Z_V1.0."""
import hashlib
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_r19z_runtime import ROOT, build_runtime
from inspect_realtek import ROM_UUID, image_digest, inspect

BASE = 0x82C000
START = BASE + 1024
END = 0x880F44
OUTPUT = ROOT / 'firmware/ZX19-Libre-0.1.0-dev-R19Z_V1.0.bin'


def flash_payload(elf):
    if (elf[:7] != b'\x7fELF\x01\x01\x01' or
            struct.unpack_from('<HH', elf, 16) != (2, 40)):
        raise ValueError('Expected a linked little-endian ARM ELF32 executable')
    entry, ph, sh = struct.unpack_from('<III', elf, 24)
    ps, pn, ss, sn = struct.unpack_from('<4H', elf, 42)
    if entry != START + 1 or ps != 32 or ss != 40:
        raise ValueError('Unexpected entry point or ELF header layout')
    segments = [struct.unpack_from('<8I', elf, ph + ps*i) for i in range(pn)]
    chunks = []
    for i in range(sn):
        _, kind, flags, va, off, size = struct.unpack_from('<6I', elf, sh + ss*i)
        if not (flags & 2) or kind == 8 or not size:
            continue
        matches = [pa + off - fo for tag, fo, v, pa, n, _, _, _ in segments
                   if tag == 1 and fo <= off and off + size <= fo + n
                   and va - v == off - fo]
        if len(matches) != 1 or off + size > len(elf):
            raise ValueError('Allocated section lacks a unique load address')
        chunks.append((matches[0], elf[off:off+size]))
    chunks.sort()
    if not chunks or chunks[0][0] != START:
        raise ValueError('Missing application entry section')
    payload = bytearray()
    for address, data in chunks:
        gap = address - START - len(payload)
        if gap < 0 or address + len(data) > END:
            raise ValueError('Section overlaps another or exceeds application flash')
        payload.extend(bytes(gap))
        payload.extend(data)
    return bytes(payload)


def package(elf):
    payload = flash_payload(elf)
    header = bytearray(1024)
    struct.pack_into('<BBHHHI16s4I', header, 0, 9, 0, 0x981, 0x2793, 0,
                     len(payload), ROM_UUID, START, START, 0, BASE)
    struct.pack_into('<I4s8s', header, 96, 1 << 4, hashlib.sha256(payload).digest()[:4],
                     b'ZX19LIBR')
    for offset in (736, 1008):
        header[offset:offset+16] = b'\xff' * 16
    image = header + payload
    image[372:404] = image_digest(image)
    wrapper = struct.pack('<4I32s32s', 0x81BDC3E5, len(image), len(image),
                          sum(image) & 0xffffffff, b'R19Z_Libre_0.1.0-dev', b'R19Z_V1.0')
    blob = wrapper + image
    if not 10240 <= len(blob) <= 389200 or not inspect(blob)['realtek_sha_matches_stored']:
        raise ValueError('Package validation failed')
    return blob


if __name__ == '__main__':
    blob = package(build_runtime().read_bytes())
    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_bytes(blob)
    print(OUTPUT.name, len(blob), hashlib.sha256(blob).hexdigest())
