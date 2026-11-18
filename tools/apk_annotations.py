"""Extract Retrofit request annotations and focused repository bytecode."""
import json
import zipfile
from pathlib import Path
from loguru import logger
logger.remove()
from androguard.core.dex import DEX

root = Path(__file__).resolve().parents[1]
rows = []
with zipfile.ZipFile(root / 'research/qwatch.apk') as z:
    for n in z.namelist():
        if not (n.startswith('classes') and n.endswith('.dex')):
            continue
        d = DEX(z.read(n))
        for c in d.get_classes():
            directory = c.annotations_directory_item
            if not directory:
                continue
            for method in directory.get_method_annotations():
                aset = d.CM.get_obj_by_offset(method.get_annotations_off())
                if not aset:
                    continue
                values = []
                for off in aset.get_annotation_off_item():
                    a = off.get_annotation_item().annotation
                    if d.CM.get_type(a.get_type_idx()) == 'Ldalvik/annotation/Signature;':
                        continue
                    vals = []
                    for e in a.get_elements():
                        value = e.get_value().get_value()
                        vals.append(str(value))
                    values.append({'type': d.CM.get_type(a.get_type_idx()), 'values': vals})
                if any(any(key in str(v).lower() for key in ('last-ota', 'login', 'guest', 'visitor', 'register', 'anonymous')) for v in values):
                    rows.append({'class': c.get_name(), 'method': str(d.CM.get_method(method.get_method_idx())), 'annotations': values})
out = root / 'research/ota-request-annotations.json'
out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
print(out)
print(json.dumps(rows, ensure_ascii=False, indent=2))
