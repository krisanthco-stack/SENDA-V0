from __future__ import annotations

import argparse
import os
import sys
import threading
import time
from pathlib import Path

from . import __version__
from .config import default_data_dir
from .server import create_server


WINDOWS_GUI = 'edgechromium'


def resource_root() -> Path:
    bundle = getattr(sys, '_MEIPASS', None)
    if bundle:
        return Path(bundle)
    return Path(__file__).resolve().parents[1]


def ui_dir() -> Path:
    root = resource_root()
    candidate = root / 'ui'
    if not (candidate / 'index.html').is_file():
        raise RuntimeError(f'Interfaz SENDA no encontrada: {candidate}')
    return candidate


def remove_zone_identifiers(root: Path | None = None) -> int:
    """Remove Windows Mark-of-the-Web streams before pythonnet loads DLLs.

    A ZIP downloaded from GitHub can propagate Zone.Identifier to extracted
    binaries. pythonnet may then fail while resolving Python.Runtime.dll before
    the WebView window is created. This runs before importing pywebview/clr.
    """
    if sys.platform != 'win32':
        return 0
    base = Path(root) if root is not None else resource_root()
    removed = 0
    candidates: list[Path] = []
    if base.is_file():
        candidates = [base]
    elif base.exists():
        candidates = [p for p in base.rglob('*') if p.is_file() and p.suffix.lower() in {'.dll', '.pyd', '.exe'}]
    for path in candidates:
        try:
            os.remove(f'{path}:Zone.Identifier')
            removed += 1
        except (FileNotFoundError, PermissionError, OSError):
            pass
    return removed


def check(data_dir=None) -> int:
    root = Path(data_dir) if data_dir else default_data_dir()
    server = create_server('127.0.0.1', 0, data_dir=root, ui_dir=ui_dir())
    try:
        if not (server.senda_app.ui_dir / 'index.html').is_file():
            raise RuntimeError('ui/index.html no está disponible')
        if not server.senda_app.repo.path.is_file():
            raise RuntimeError('No se creó la base local')
        if not server.server_address[1]:
            raise RuntimeError('No se asignó puerto local')
        print(f'SENDA.V0 Desktop WebView OK {__version__} · UI={server.senda_app.ui_dir}')
        return 0
    finally:
        server.server_close()


def _close_smoke_window(window, delay: float = 2.0) -> None:
    time.sleep(delay)
    try:
        window.destroy()
    except Exception:
        pass


def run(data_dir=None, smoke_gui: bool = False) -> int:
    # Critical: remove Mark-of-the-Web from bundled native DLLs before
    # importing pywebview, which imports pythonnet/clr on Windows.
    remove_zone_identifiers()
    try:
        import webview
    except Exception as e:
        raise RuntimeError('El instalable requiere PyWebView/Edge WebView2. Use el build oficial de GitHub Actions.') from e

    root = Path(data_dir) if data_dir else default_data_dir()
    server = create_server('127.0.0.1', 0, data_dir=root, ui_dir=ui_dir())
    thread = threading.Thread(target=server.serve_forever, name='SENDA-local-server', daemon=True)
    thread.start()
    url = f'http://127.0.0.1:{server.server_address[1]}/'
    try:
        window = webview.create_window(
            f'SENDA.V0 {__version__} · Registro Inmobiliario',
            url,
            width=1500,
            height=900,
            min_size=(1100, 700),
            resizable=True,
            text_select=True,
        )
        if smoke_gui:
            webview.start(_close_smoke_window, args=(window,), gui='edgechromium', debug=False)
        else:
            webview.start(gui='edgechromium', debug=False)
        return 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument('--check', action='store_true')
    p.add_argument('--smoke-gui', action='store_true')
    p.add_argument('--data-dir', default=None)
    args = p.parse_args(argv)
    if args.check:
        return check(args.data_dir)
    return run(args.data_dir, smoke_gui=args.smoke_gui)


if __name__ == '__main__':
    raise SystemExit(main())
