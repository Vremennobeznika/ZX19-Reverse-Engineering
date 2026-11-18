"""Link the R19Z display runtime. Output is an ELF for debugging."""
import os
import hashlib
import secrets
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
    # Only the verifier is linked into the image. Keep the owner's key local.
    key_file = ROOT / 'firmware/ZX19-owner.key'
    try:
        with key_file.open('x', encoding='ascii') as f:
            f.write(secrets.token_hex(16)+'\n')
    except FileExistsError:
        pass
    key = bytes.fromhex(key_file.read_text(encoding='ascii').strip())
    if len(key) != 16:
        raise ValueError('Invalid ZX19-owner.key length')
    digest = hashlib.sha256(key).digest()
    (BUILD/'r19z_owner.h').write_text('#define R19Z_OWNER_HASH {'+
        ','.join(hex(b) for b in digest)+'}\n',encoding='ascii')
    modules = ('r19z_startup', 'r19z_runtime', 'r19z_display_app', 'r19z_panel',
               'watch_lcd', 'watch_core', 'watch_render', 'watch_input', 'watch_touch',
               'r19z_i2c', 'r19z_touch_setup', 'r19z_calendar','r19z_ble','r19z_update')
    subprocess.run([str(zig), 'cc', '-target', 'thumb-freestanding-eabi', '-mcpu=cortex_m4',
                    '-mfloat-abi=soft', '-Os', '-g', '-std=c11', '-Wall', '-Wextra',
                    '-Werror', '-ffreestanding', '-fno-builtin', '-fno-stack-protector',
                    '-nostdlib', '-Wl,-e,r19z_system_init', '-Wl,-u,r19z_display_update',
                    '-Wl,-u,r19z_receive_time',
                    '-Wl,-T,' + str(ROOT / 'src/r19z_memory.ld'),
                    '-I'+str(sdk), '-I'+str(BUILD),
                    *(str(ROOT / 'src' / (name + '.c')) for name in modules),
                    str(sdk/'libgap_utils.a'),
                    '-o', str(OUTPUT)], check=True,
                   env=dict(os.environ, ZIG_GLOBAL_CACHE_DIR=str(BUILD/'zig-cache')))
    return OUTPUT

if __name__ == '__main__':
    print(build_runtime())
