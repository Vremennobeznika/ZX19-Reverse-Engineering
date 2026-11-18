"""Link the R19Z display runtime. Output is an ELF for debugging."""
import os
from pathlib import Path
import subprocess
import ziglang
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from r19z_sdk import prepare

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / 'build'
OUTPUT = BUILD / 'r19z-display-runtime.elf'

def build_runtime():
    BUILD.mkdir(exist_ok=True)
    zig = Path(ziglang.__file__).parent / 'zig.exe'
    sdk = prepare(BUILD)
    modules = ('r19z_startup', 'r19z_runtime', 'r19z_display_app', 'r19z_panel',
               'watch_lcd', 'watch_core', 'watch_render', 'watch_input', 'watch_touch',
               'r19z_i2c', 'r19z_touch_setup', 'r19z_calendar','r19z_ble')
    subprocess.run([str(zig), 'cc', '-target', 'thumb-freestanding-eabi', '-mcpu=cortex_m4',
                    '-mfloat-abi=soft', '-Os', '-g', '-std=c11', '-Wall', '-Wextra',
                    '-Werror', '-ffreestanding', '-fno-builtin', '-fno-stack-protector',
                    '-nostdlib', '-Wl,-e,r19z_system_init', '-Wl,-u,r19z_display_update',
                    '-Wl,-u,r19z_receive_time',
                    '-Wl,-T,' + str(ROOT / 'src/r19z_memory.ld'),
                    '-I'+str(sdk),
                    *(str(ROOT / 'src' / (name + '.c')) for name in modules),
                    str(sdk/'libgap_utils.a'),
                    '-o', str(OUTPUT)], check=True,
                   env=dict(os.environ, ZIG_GLOBAL_CACHE_DIR=str(BUILD/'zig-cache')))
    return OUTPUT

if __name__ == '__main__':
    print(build_runtime())
