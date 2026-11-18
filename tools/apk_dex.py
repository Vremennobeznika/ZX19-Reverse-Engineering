"""Extract metadata and selected OTA bytecode without executing the APK."""
import json
import re
import sys
import zipfile
from pathlib import Path
from loguru import logger
logger.remove()
from androguard.core.apk import APK
from androguard.core.dex import DEX

p = Path(sys.argv[1])
a = APK(str(p))
metadata = {'package': a.get_package(), 'version': a.get_androidversion_name(),
            'version_code': a.get_androidversion_code(),
            'certificate_sha256': [c.sha256.hex() for c in a.get_certificates()]}
p.with_suffix('.metadata.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
print(json.dumps(metadata))
out = p.with_suffix('.ota-bytecode.txt')
with out.open('w', encoding='utf-8') as f, zipfile.ZipFile(p) as z:
    for name in z.namelist():
        if not re.fullmatch(r'classes\d*\.dex', name):
            continue
        d = DEX(z.read(name))
        for cls in d.get_classes():
            cn = cls.get_name()
            for m in cls.get_methods():
                instructions = [(ins.get_name(), ins.get_output()) for ins in m.get_instructions()]
                interesting = re.search(r'ota|dfu|firmware|upgrade|updatefirm|deviceversion', cn + m.get_name(), re.I)
                interesting = interesting or cn in ('LO6/d;', 'LN8/f;', 'LA7/r;', 'LF6/n;')
                interesting = interesting or any(re.search(r'firmware|dfuFile|hardwareVersion|/upgrade|/ota', s, re.I) for _, s in instructions)
                if not interesting:
                    continue
                f.write('\n' + cn + ' ' + m.get_name() + ' ' + str(m.get_descriptor()) + '\n')
                for op, args in instructions:
                    f.write(op + ' ' + args + '\n')
print(out)
