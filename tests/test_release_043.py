from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def test_release_contract_is_044_and_keeps_updater_sync_webview_and_dependencies():
    entry = (ROOT / 'SENDA_V0_DESKTOP.pyw').read_text(encoding='utf-8')
    webview = (ROOT / 'app' / 'desktop_webview.py').read_text(encoding='utf-8')
    with (ROOT / 'pyproject.toml').open('rb') as fh:
        version = tomllib.load(fh)['project']['version']
    workflow = (ROOT / '.github' / 'workflows' / 'build-windows-desktop.yml').read_text(encoding='utf-8').lower()
    assert version == '0.4.6'
    assert 'app.desktop_webview' in entry
    assert '__version__' in webview
    assert 'tomllib' in workflow and 'pyproject.toml' in workflow
    assert 'asset = "senda.v0_${version}_windows_desktop.zip"' in workflow
    assert 'artifact = "senda.v0-${version}-windows-desktop"' in workflow
    assert workflow.count('0.4.4') == 0
    assert 'install_from_github.ps1' in workflow
    assert 'extract_installer_from_github.ps1' in workflow
    assert 'extraer_instalador_github.bat' in workflow
    assert 'openpyxl==3.1.5' in workflow and 'xlsxwriter==3.2.9' in workflow
    assert '--collect-all webview' in workflow
