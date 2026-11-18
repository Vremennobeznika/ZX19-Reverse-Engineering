"""Fetch the pinned public Realtek headers and GAP client library used by the build."""
import hashlib
from pathlib import Path
import tempfile
from urllib.request import urlopen

BASE = ('https://raw.githubusercontent.com/ART-Badge/SDK/'
        '116b2296a9f6442a85c68daf4855d9ed36cc330d/bsp_for_art-badge/libraries/')
UPPER = 'bin/upperstack_img/upperstack_0_0/'
FILES = [UPPER+'libgap_utils.a', UPPER+'upperstack_config.h', 'inc/app/app_msg.h',
         'inc/os/os_msg.h', 'inc/bluetooth/profile/profile_server.h', 'inc/bluetooth/profile/gatt.h']
FILES += ['inc/bluetooth/gap/'+name+'.h' for name in
          ('bt_types','gap','gap_adv','gap_le','gap_msg','gap_callback_le','gap_storage_le','gap_le_types','gap_bond_le')]

def prepare(build):
    directory = build/'r19z-sdk'
    directory.mkdir(exist_ok=True)
    for path in FILES:
        target = directory/Path(path).name
        if not target.is_file():
            with urlopen(BASE+path,timeout=30) as response:
                data = response.read()
            with tempfile.NamedTemporaryFile(dir=directory,delete=False) as tmp:
                tmp.write(data)
            Path(tmp.name).replace(target)
    archive = directory/'libgap_utils.a'
    if hashlib.sha256(archive.read_bytes()).hexdigest() != 'cfb84a03b916d55d8f220d83818577033c3f5a06f52449c7dead1e7dc356ee0c':
        raise ValueError('Unexpected SDK library digest')
    return directory
