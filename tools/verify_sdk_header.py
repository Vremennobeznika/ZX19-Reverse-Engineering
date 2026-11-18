"""Offline SDK checksum cross-check. Only temporary files, no BLE/device access."""
import hashlib
import importlib.util
import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('inspect_realtek', ROOT / 'tools/inspect_realtek.py')
inspector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inspector)
image_digest = inspector.image_digest
TOOL = ROOT / 'research/sdk-reference/prepend_header.exe'
TOOL_SHA = '473a50538a415270e3f95bbb63a8bfd06ce9f7c65cdc82485c81b94a44c63a0a'
SOURCE = ROOT / 'firmware/R19Z_1.00.18_241125.bin'
SOURCE_SHA = '22f94070c13c157048b335e25af21e3421cc0a92c77c6b13f3c8088f88ddd7bd'

def main():
    source = SOURCE.read_bytes()
    assert hashlib.sha256(source).hexdigest() == SOURCE_SHA, 'Unknown stock image'
    assert hashlib.sha256(TOOL.read_bytes()).hexdigest() == TOOL_SHA, 'Unknown SDK tool'
    image = source[80:]
    cases = {}
    with tempfile.TemporaryDirectory(prefix='sdk-check-', dir=ROOT / 'build') as tmp:
        for name in ['stock', 'cleared_digest', 'payload_mutation']:
            data = bytearray(image)
            if name == 'cleared_digest':
                data[372:404] = bytes(32)
            elif name == 'payload_mutation':
                data[1024] ^= 1
            path = Path(tmp) / (name + '.bin')
            path.write_bytes(data)
            run = subprocess.run([str(TOOL), '-b', '9', '-c', 'sha256', '-e', '1',
                                  '-m', '0', '-p', str(path)], cwd=tmp,
                                 capture_output=True, timeout=20, check=True)
            output = path.read_bytes()
            assert len(output) == len(image)
            assert output[372:404] == image_digest(output), 'Independent Python/SDK digest mismatch'
            differences = [i for i, (a, b) in enumerate(zip(data, output)) if a != b]
            assert all(372 <= i < 404 for i in differences), 'Unexpected SDK rewrite'
            if name in ['stock', 'cleared_digest']:
                assert output == image, 'SDK did not reproduce the original image'
            else:
                assert output[372:404] != image[372:404], 'Mutation not detected'
            cases[name] = {'passed': True, 'digest': output[372:404].hex(),
                           'changed_offsets': differences,
                           'sdk_stdout': run.stdout.decode(errors='replace').strip()}
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == SOURCE_SHA
    report = {'sdk_tool_sha256': TOOL_SHA, 'stock_sha256': SOURCE_SHA,
              'cases': cases, 'device_access': False,
              'interpretation': 'SDK checksum reproduced, not signature verification or hardware boot proof'}
    out = ROOT / 'reports/sdk-header-tests.json'
    out.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print('PASS: stock, cleared digest, changed payload; original untouched; no device access')

if __name__ == '__main__':
    main()
