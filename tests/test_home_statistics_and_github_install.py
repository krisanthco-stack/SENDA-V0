from pathlib import Path
from datetime import date, timedelta

from app.repository import Repository

ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_exposes_monthly_series_and_recent_movements(tmp_path):
    repo = Repository(tmp_path / 'db.sqlite')
    repo.insert_movements([
        {'folio':'4-100-001','fecha':'2026-01-10','distrito':'HORQUETAS','fuente':'HISTORICOS','operacion':'HIPOTECA'},
        {'folio':'4-100-001','fecha':'2026-02-15','distrito':'HORQUETAS','fuente':'GRAVAMENES','operacion':'SERVIDUMBRE'},
        {'folio':'4-200','fecha':'2026-02-20','distrito':'LA VIRGEN','fuente':'ANOTACIONES','operacion':'ANOTACION'},
    ], import_id=1)
    d = repo.dashboard({'year': 2026, 'quarter': 'T1'})
    assert d['por_mes'][1] == 1
    assert d['por_mes'][2] == 2
    assert [r['fecha'] for r in d['recientes']] == ['2026-02-20', '2026-02-15', '2026-01-10']
    assert d['recientes'][0]['folio'] == '4-200'


def test_official_ui_home_contains_visual_statistics_and_colored_alarms():
    html = (ROOT / 'ui' / 'index.html').read_text(encoding='utf-8')
    css = (ROOT / 'ui' / 'app.css').read_text(encoding='utf-8')
    assert 'MOVIMIENTOS POR CATEGORÍA' in html
    assert 'MOVIMIENTOS POR DISTRITO' in html
    assert 'MOVIMIENTOS RECIENTES' in html
    assert 'alarm-line red' in html and 'alarm-line yellow' in html and 'alarm-line green' in html
    assert '.dashboard-grid' in css and '.bars' in css


def test_repository_has_install_from_github_entrypoint():
    bat = ROOT / 'INSTALAR_DESDE_GITHUB.bat'
    ps1 = ROOT / 'scripts' / 'install_from_github.ps1'
    assert bat.is_file()
    assert ps1.is_file()
    bat_text = bat.read_text(encoding='utf-8', errors='ignore').lower()
    ps_text = ps1.read_text(encoding='utf-8', errors='ignore').lower()
    assert 'install_from_github.ps1' in bat_text
    assert 'api.github.com/repos/krisanthco-stack/senda-v0/releases/latest' in ps_text
    assert 'senda.v0' in ps_text and 'windows' in ps_text
    assert 'localappdata' not in ps_text or 'remove-item $dataroot' not in ps_text


def test_workflow_publishes_installable_release():
    text = (ROOT / '.github' / 'workflows' / 'build-windows-desktop.yml').read_text(encoding='utf-8').lower()
    assert 'contents: write' in text
    assert 'gh release' in text
    assert 'asset = "senda.v0_${version}_windows_desktop.zip"' in text


def test_official_ui_typography_has_clear_hierarchy():
    css = (ROOT / 'ui' / 'app.css').read_text(encoding='utf-8')
    assert 'font:12px/1.35 "Segoe UI"' in css
    assert '.brand b{display:block;font-size:22px}' in css
    assert '.kpis b{font-size:20px' in css
    assert '.panel h2{font-size:12px' in css

