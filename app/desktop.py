"""Compatibilidad de arranque para SENDA.V0.

Desde 0.4.4 no existe una segunda interfaz de escritorio separada. Este módulo se conserva
únicamente para accesos antiguos que ejecutaban ``python -m app.desktop`` y
delega a la misma WebView que usa SENDA_V0_DESKTOP.pyw.
"""
from __future__ import annotations

from .desktop_webview import check, main, run, ui_dir

__all__ = ['check', 'main', 'run', 'ui_dir']

if __name__ == '__main__':
    raise SystemExit(main())
