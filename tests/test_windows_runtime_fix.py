from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def test_desktop_forces_edgechromium_and_has_gui_smoke_mode_and_unblock_preflight():
    text = (ROOT / 'app' / 'desktop_webview.py').read_text(encoding='utf-8')
    low = text.lower()
    assert "gui='edgechromium'" in low or 'gui="edgechromium"' in low
    assert '--smoke-gui' in text
    assert 'Zone.Identifier' in text
    assert 'remove_zone' in low or 'unblock' in low


def test_workflow_pins_current_windows_webview_stack_and_runs_real_gui_smoke_test():
    text = (ROOT / '.github' / 'workflows' / 'build-windows-desktop.yml').read_text(encoding='utf-8')
    low = text.lower()
    assert 'pywebview==6.2.1' in low
    assert 'pythonnet==3.1.0' in low
    assert 'clr-loader==0.3.1' in low
    assert 'import clr' in low
    assert '--smoke-gui' in low
    assert 'edgechromium' in low
    for stale in ('webview', 'pythonnet', 'clr_loader', 'clr.py'):
        assert stale in low
    assert 'se está importando desde el repositorio' in text


def test_installer_and_updater_unblock_downloaded_binaries_before_first_real_launch():
    install = (ROOT / 'scripts' / 'install_desktop.ps1').read_text(encoding='utf-8')
    update = (ROOT / 'scripts' / 'update_desktop.ps1').read_text(encoding='utf-8')
    assert 'Unblock-File' in install
    assert 'Unblock-File' in update
    assert install.find('Unblock-File') < install.find('& $TargetExe --check')
    assert update.find('Unblock-File') < update.find('& $TargetExe --check')


def test_release_version_is_046():
    with (ROOT / 'pyproject.toml').open('rb') as fh:
        version = tomllib.load(fh)['project']['version']
    assert version == '0.4.6'
    assert "__version__ = '0.4.6'" in (ROOT / 'app' / '__init__.py').read_text(encoding='utf-8')
    assert 'SENDA.V0 0.4.6' in (ROOT / 'scripts' / 'install_desktop.ps1').read_text(encoding='utf-8')


def test_zone_identifier_preflight_removes_python_runtime_mark(tmp_path, monkeypatch):
    import sys
    from app.desktop_webview import remove_zone_identifiers
    dll = tmp_path / 'Python.Runtime.dll'
    dll.write_bytes(b'fake')
    zone = Path(str(dll) + ':Zone.Identifier')
    zone.write_text('[ZoneTransfer]\nZoneId=3\n', encoding='utf-8')
    monkeypatch.setattr(sys, 'platform', 'win32')
    assert remove_zone_identifiers(tmp_path) == 1
    assert not zone.exists()
