from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_official_ui_has_visible_update_from_github_button_and_api_hook():
    html = (ROOT / 'ui' / 'index.html').read_text(encoding='utf-8')
    js = (ROOT / 'ui' / 'app.js').read_text(encoding='utf-8')
    server = (ROOT / 'app' / 'server.py').read_text(encoding='utf-8')
    assert 'ACTUALIZAR DESDE GITHUB' in html
    assert 'updateFromGitHub' in html + js
    assert '/api/update-from-github' in js + server
    assert 'install_from_github.ps1' in server


def test_release_bundle_contains_github_updater_files():
    workflow = (ROOT / '.github' / 'workflows' / 'build-windows-desktop.yml').read_text(encoding='utf-8').lower()
    assert 'scripts/install_from_github.ps1' in workflow
    assert 'instalar_desde_github.bat' in workflow


def test_github_updater_stops_running_desktop_before_install_and_preserves_data():
    script = (ROOT / 'scripts' / 'install_from_github.ps1').read_text(encoding='utf-8').lower()
    assert "get-process -name 'senda.v0'" in script
    assert 'stop-process' in script
    assert "join-path $env:localappdata 'senda.v0'" in script
    assert 'remove-item $dataroot' not in script
