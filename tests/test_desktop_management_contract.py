from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_management_ui_has_statistics_and_portable_export_actions():
    html = (ROOT / 'ui' / 'index.html').read_text(encoding='utf-8')
    js = (ROOT / 'ui' / 'app.js').read_text(encoding='utf-8')
    server = (ROOT / 'app' / 'server.py').read_text(encoding='utf-8')
    assert 'TRÁMITES REALIZADOS POR MES' in html
    assert 'managementMonthBars' in html + js
    assert '/api/management/statistics' in js + server
    assert 'data-kind="xlsx"' in js
    assert 'data-kind="json"' in js
    assert '/api/cases/' in js and '/export/' in js
