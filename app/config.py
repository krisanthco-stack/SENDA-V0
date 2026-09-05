from __future__ import annotations
import os
from pathlib import Path

APP_NAME='SENDA.V0'

def default_data_dir() -> Path:
    explicit=os.environ.get('SENDA_DATA_DIR')
    if explicit:return Path(explicit).expanduser().resolve()
    if os.name=='nt':
        base=Path(os.environ.get('LOCALAPPDATA') or Path.home()/'AppData'/'Local')
        return base/'SENDA.V0'
    return Path.home()/'.local'/'share'/'SENDA.V0'

def ensure_data_dirs(root:Path|None=None):
    root=Path(root or default_data_dir())
    dirs={name:root/name for name in ('database','imports','exports','backups','expedientes','logs','tmp')}
    for p in dirs.values():p.mkdir(parents=True,exist_ok=True)
    return root,dirs
