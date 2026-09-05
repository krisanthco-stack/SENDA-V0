from __future__ import annotations

import argparse
import errno
import logging
import sys
import threading
import time
import traceback
import urllib.request
import webbrowser
from pathlib import Path

from .config import ensure_data_dirs
from .server import create_server

LOG_NAME = 'senda_v0.log'
HEALTH_PATH = '/api/health'
ROOT_MARKER = b'SENDA.V0'


def _address_in_use(exc: OSError) -> bool:
    return exc.errno == errno.EADDRINUSE or getattr(exc, 'winerror', None) == 10048


def create_resilient_server(host='127.0.0.1', preferred_port=8765, *, data_dir=None, ui_dir=None):
    try:
        server = create_server(host, int(preferred_port), data_dir=data_dir, ui_dir=ui_dir)
        return server, int(server.server_address[1])
    except OSError as exc:
        if int(preferred_port) == 0 or not _address_in_use(exc):
            raise
        server = create_server(host, 0, data_dir=data_dir, ui_dir=ui_dir)
        return server, int(server.server_address[1])


def _logger(log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger('senda.v0.launcher')
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass
    fmt = logging.Formatter('%(asctime)s | %(levelname)s | %(message)s')
    file_handler = logging.FileHandler(log_path, encoding='utf-8')
    file_handler.setFormatter(fmt)
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    logger.addHandler(file_handler)
    logger.addHandler(console)
    return logger


def _wait_for_health(url: str, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url + HEALTH_PATH, timeout=1.5) as response:
                if response.status != 200:
                    raise RuntimeError(f'/api/health respondió HTTP {response.status}')
            with urllib.request.urlopen(url + '/', timeout=1.5) as response:
                content_type = response.headers.get('Content-Type', '')
                body = response.read(256 * 1024)
                if response.status == 200 and 'text/html' in content_type.lower() and ROOT_MARKER in body:
                    return
                raise RuntimeError('La interfaz principal de SENDA no está disponible en /.')
        except Exception as exc:
            last_error = exc
        time.sleep(0.15)
    raise RuntimeError(f'El servidor no superó la verificación completa (API + interfaz): {last_error}')


def run(host='127.0.0.1', port=8765, *, data_dir=None, ui_dir=None, no_browser=False, check_only=False) -> int:
    server = None
    thread = None
    logger = None
    log_path = None
    try:
        root, dirs = ensure_data_dirs(Path(data_dir) if data_dir else None)
        log_path = dirs['logs'] / LOG_NAME
        logger = _logger(log_path)
        logger.info('Iniciando SENDA.V0')
        logger.info('Datos: %s', root)
        server, used_port = create_resilient_server(host, port, data_dir=root, ui_dir=ui_dir)
        if used_port != int(port):
            logger.warning('Puerto %s ocupado; SENDA.V0 usará el puerto %s.', port, used_port)
        thread = threading.Thread(target=server.serve_forever, name='SENDA.V0 HTTP', daemon=True)
        thread.start()
        url = f'http://{host}:{used_port}'
        _wait_for_health(url)
        logger.info('Servidor verificado: API + interfaz en %s', url)
        if check_only:
            logger.info('Autodiagnóstico completado correctamente.')
            return 0
        print(f'\nSENDA.V0 CONECTADO: {url}', flush=True)
        print(f'LOG: {log_path}\n', flush=True)
        if not no_browser:
            webbrowser.open(url)
        while thread.is_alive():
            thread.join(timeout=1.0)
        return 0
    except KeyboardInterrupt:
        if logger:
            logger.info('Cierre solicitado por el usuario.')
        return 0
    except Exception:
        detail = traceback.format_exc()
        if logger:
            logger.error('Fallo de arranque.\n%s', detail)
        else:
            print(detail, file=sys.stderr, flush=True)
        destination = str(log_path) if log_path else 'No fue posible crear el archivo de log.'
        print(f'\nERROR: SENDA.V0 no pudo iniciar.\nLOG: {destination}\n', flush=True)
        return 1
    finally:
        if server is not None:
            try:
                server.shutdown()
            except Exception:
                pass
            try:
                server.server_close()
            except Exception:
                pass


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--data-dir', default=None)
    parser.add_argument('--ui-dir', default=None)
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--check', action='store_true', help='Comprueba API + interfaz y termina.')
    args = parser.parse_args(argv)
    return run(args.host, args.port, data_dir=args.data_dir, ui_dir=args.ui_dir, no_browser=args.no_browser, check_only=args.check)


if __name__ == '__main__':
    raise SystemExit(main())
