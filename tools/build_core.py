"""Build a host test DLL and Cortex-M4 object; deliberately no flashable image."""
import importlib.util
import json
import os
import struct
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
spec = importlib.util.find_spec('ziglang')
if spec is None:
    raise SystemExit('Missing build dependency: ziglang')
zig = Path(spec.origin).parent / 'zig.exe'
build = root / 'build'
build.mkdir(exist_ok=True)
env = dict(os.environ)
env['ZIG_GLOBAL_CACHE_DIR'] = str(build / 'zig-cache')
source = root / 'src/watch_core.c'
renderer = root / 'src/watch_render.c'
lcd = root / 'src/watch_lcd.c'
input_source = root / 'src/watch_input.c'
touch_source = root / 'src/watch_touch.c'
strip_source = root / 'src/watch_strip.c'
common = ['-std=c11', '-Os', '-Wall', '-Wextra', '-Werror', '-ffreestanding', '-fno-builtin',
          '-fno-stack-protector', '-fno-unwind-tables', '-fno-asynchronous-unwind-tables']
commands = [
    [str(zig), 'cc', *common, '-target', 'x86_64-windows-gnu', '-shared', '-nostdlib',
     '-Wl,--entry,DllMainCRTStartup', str(source), str(renderer), str(lcd), str(input_source), str(touch_source), str(strip_source), str(root / 'tests/host_dll.c'), '-o', str(build / 'watch_core.dll')],
    [str(zig), 'cc', *common, '-target', 'thumb-freestanding-eabi', '-mcpu=cortex_m4',
     '-mfloat-abi=soft', '-c', str(source), '-o', str(build / 'watch_core.arm.o')],
    [str(zig), 'cc', *common, '-target', 'thumb-freestanding-eabi', '-mcpu=cortex_m4',
     '-mfloat-abi=soft', '-c', str(renderer), '-o', str(build / 'watch_render.arm.o')],
    [str(zig), 'cc', *common, '-target', 'thumb-freestanding-eabi', '-mcpu=cortex_m4',
     '-mfloat-abi=soft', '-c', str(lcd), '-o', str(build / 'watch_lcd.arm.o')],
    [str(zig), 'cc', *common, '-target', 'thumb-freestanding-eabi', '-mcpu=cortex_m4',
     '-mfloat-abi=soft', '-c', str(input_source), '-o', str(build / 'watch_input.arm.o')],
    [str(zig), 'cc', *common, '-target', 'thumb-freestanding-eabi', '-mcpu=cortex_m4',
     '-mfloat-abi=soft', '-c', str(touch_source), '-o', str(build / 'watch_touch.arm.o')],
]
results = []
commands.append([str(zig), 'cc', *common, '-target', 'thumb-freestanding-eabi',
                 '-mcpu=cortex_m4', '-mfloat-abi=soft', '-c', str(strip_source),
                 '-o', str(build / 'watch_strip.arm.o')])
for command in commands:
    proc = subprocess.run(command, env=env, capture_output=True, text=True)
    results.append({'command': command, 'return_code': proc.returncode,
                    'stdout': proc.stdout, 'stderr': proc.stderr})
    (build / 'build-log.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    if proc.returncode:
        print(proc.stderr)
        raise SystemExit(proc.returncode)
obj = (build / 'watch_core.arm.o').read_bytes()
if obj[:5] != b'\x7fELF\x01':
    raise SystemExit('Expected ELF32 ARM object')
shoff = struct.unpack_from('<I', obj, 32)[0]
entsize, count = struct.unpack_from('<HH', obj, 46)
allocated = 0
for i in range(count):
    values = struct.unpack_from('<10I', obj, shoff + i * entsize)
    if values[2] & 2:
        allocated += values[5]
report = {'compiler': subprocess.check_output([str(zig), 'version'], text=True).strip(),
          'arm_object_allocated_section_bytes': allocated, 'arm_object_file_bytes': len(obj),
          'note': 'Relocatable core object, not linked firmware; excludes all drivers, startup, BLE and renderer.'}
render_obj = (build / 'watch_render.arm.o').read_bytes()
rshoff = struct.unpack_from('<I', render_obj, 32)[0]
rentsize, rcount = struct.unpack_from('<HH', render_obj, 46)
report['renderer_allocated_section_bytes'] = sum(
    struct.unpack_from('<10I', render_obj, rshoff+i*rentsize)[5]
    for i in range(rcount) if struct.unpack_from('<10I', render_obj, rshoff+i*rentsize)[2] & 2)
report['module_allocated_section_bytes'] = {}
for module in ('watch_core','watch_render','watch_lcd','watch_input','watch_touch','watch_strip'):
    blob=(build/(module+'.arm.o')).read_bytes()
    offset=struct.unpack_from('<I',blob,32)[0]
    stride,num=struct.unpack_from('<HH',blob,46)
    sections=[struct.unpack_from('<10I',blob,offset+i*stride) for i in range(num)]
    report['module_allocated_section_bytes'][module]=sum(s[5] for s in sections if s[2]&2)
report['own_modules_allocated_section_total']=sum(report['module_allocated_section_bytes'].values())
report['note']='Relocatable application objects, not linked firmware. Excludes board startup, MMIO drivers, Bluetooth and vendor runtime. Renderer and LCD protocol adapter are included in module totals.'
(build / 'core-build.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))
