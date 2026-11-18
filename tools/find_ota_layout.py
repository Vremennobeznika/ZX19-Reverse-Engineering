"""Read-only search for RTL8762D bank headers in an already obtained dump.

No device access; candidates are not proof of an active/valid bank. Layout:
ART-Badge/SDK libraries/inc/platform/patch_header_check.h T_OTA_HEADER_FORMAT.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path

ROM_UUID = bytes.fromhex('1d6a69f12f38ea1182a767370a3ca32e')
NAMES = ('secure_boot', 'rom_patch', 'app', 'app_data1', 'app_data2',
         'app_data3', 'app_data4', 'app_data5', 'app_data6', 'upperstack')


def find_layouts(blob):
    layouts = []
    start = 0
    while True:
        uuid_at = blob.find(ROM_UUID, start)
        if uuid_at < 0:
            return layouts
        start = uuid_at + 1
        offset = uuid_at - 12
        if offset < 0 or offset + 0x1000 > len(blob):
            continue
        ic, secure, flags, image_id, crc, length = struct.unpack_from('<BBHHHI', blob, offset)
        if ic != 9 or image_id != 0x2790:
            continue
        regions = []
        for index, name in enumerate(NAMES):
            field = 0x198 + index * 8
            address, size = struct.unpack_from('<II', blob, offset + field)
            regions.append({'name': name, 'field_offset': hex(field),
                            'address': hex(address), 'size': size})
        layouts.append({'file_offset': hex(offset), 'ic': ic,
                        'control_flags': hex(flags), 'payload_size': length,
                        'regions': regions, 'active_bank_verified': False,
                        'authenticity_verified': False})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    if args.input.resolve() == args.report.resolve():
        parser.error('Report must not overwrite source')
    blob = args.input.read_bytes()
    layouts = find_layouts(blob)
    report = {'input': str(args.input), 'sha256': hashlib.sha256(blob).hexdigest(),
              'candidate_count': len(layouts), 'candidates': layouts,
              'device_access': False,
              'limitation': 'Only matching SDK-layout headers are recognized; no boot-policy or active-bank proof.'}
    args.report.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
