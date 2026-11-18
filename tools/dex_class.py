import sys
import zipfile
from pathlib import Path
from loguru import logger
logger.remove()
from androguard.core.dex import DEX

p = Path(sys.argv[1])
names = set(sys.argv[2:])
with p.with_suffix('.selected-bytecode.txt').open('w', encoding='utf-8') as f, zipfile.ZipFile(p) as z:
    for n in z.namelist():
        if not (n.startswith('classes') and n.endswith('.dex')):
            continue
        d = DEX(z.read(n))
        for c in d.get_classes():
            if c.get_name() not in names:
                continue
            for m in c.get_methods():
                f.write('\n' + c.get_name() + ' ' + m.get_name() + ' ' + m.get_descriptor() + '\n')
                for i in m.get_instructions():
                    f.write(i.get_name() + ' ' + i.get_output() + '\n')
