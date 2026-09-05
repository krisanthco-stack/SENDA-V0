from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_official_html_ui_uses_rounded_buttons_for_primary_actions_and_update():
    html = (ROOT / 'ui' / 'index.html').read_text(encoding='utf-8')
    css = (ROOT / 'ui' / 'app.css').read_text(encoding='utf-8')
    assert '↻ ACTUALIZAR DESDE GITHUB' in html
    assert '>FINALIZAR<' in html
    assert '>PASAR A CONTROL<' in html
    assert '.btn{height:30px' in css
    assert 'border-radius:5px' in css
