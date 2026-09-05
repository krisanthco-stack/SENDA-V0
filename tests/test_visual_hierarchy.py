from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_official_html_ui_is_compact_and_keeps_requested_visual_hierarchy():
    css = (ROOT / 'ui' / 'app.css').read_text(encoding='utf-8')
    html = (ROOT / 'ui' / 'index.html').read_text(encoding='utf-8')
    for token in (
        'font:12px/1.35 "Segoe UI"',
        '.brand b{display:block;font-size:22px}',
        '.kpis b{font-size:20px',
        '.btn{height:30px',
        'grid-template-columns:repeat(5,1fr)',
    ):
        assert token in css
    assert html.index('LEYENDA DE ESTADO') < html.index('🏷 CÓDIGOS')
