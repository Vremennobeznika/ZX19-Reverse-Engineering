"""Build a standalone offline HTML preview from the same application C source."""
import base64
import importlib.util
import os
import subprocess
from pathlib import Path

root=Path(__file__).resolve().parents[1]
zig=Path(importlib.util.find_spec('ziglang').origin).parent/'zig.exe'
wasm=root/'build/watch_preview.wasm'
env=dict(os.environ);env['ZIG_GLOBAL_CACHE_DIR']=str(root/'build/zig-cache')
sources=[root/'src'/name for name in ('watch_core.c','watch_render.c','watch_input.c','watch_touch.c')]
cmd=[str(zig),'cc','-target','wasm32-freestanding','-std=c11','-Os','-Wall','-Wextra','-Werror',
     '-ffreestanding','-fno-builtin','-nostdlib','-Wl,--no-entry','-rdynamic',
     '-Wl,--export-memory','-Wl,-z,stack-size=16384',*[str(p) for p in sources],
     str(root/'tests/preview_wasm.c'),'-o',str(wasm)]
r=subprocess.run(cmd,capture_output=True,text=True,env=env)
(root/'build/preview-build.txt').write_text(r.stdout+r.stderr,encoding='utf-8')
if r.returncode: raise SystemExit(r.stderr)
template=(root/'tools/preview-template.html').read_text(encoding='utf-8')
output=root/'ZX19-preview.html'
output.write_text(template.replace('WASM_BASE64_PLACEHOLDER',base64.b64encode(wasm.read_bytes()).decode()),encoding='utf-8')
print(output)
print('WASM bytes:',wasm.stat().st_size,'standalone HTML bytes:',output.stat().st_size)
