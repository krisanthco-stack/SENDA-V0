from app.desktop_model import alarm_visual, information_alarm_row


def test_alarm_visual_maps_levels_to_visible_badges_and_soft_colors():
    red = alarm_visual('red')
    yellow = alarm_visual('yellow')
    green = alarm_visual('green')

    assert red['label'].startswith('🔴')
    assert red['tag'] == 'alarm_red'
    assert red['background'] == '#fee2e2'

    assert yellow['label'].startswith('🟡')
    assert yellow['tag'] == 'alarm_yellow'
    assert yellow['background'] == '#fef9c3'

    assert green['label'].startswith('🟢')
    assert green['tag'] == 'alarm_green'
    assert green['background'] == '#dcfce7'


def test_information_alarm_row_returns_visible_alarm_and_tree_tag():
    row = {
        'entity_key': '4-123', 'folio': '4-123', 'plano': 'H-001',
        'distrito': 'HORQUETAS', 'status': 'INFORMACION', 'movimientos': 7,
        'derechos': 2, 'alarma': 'red', 'first_date': '2025-01-01', 'last_date': '2025-02-01'
    }
    values, tag = information_alarm_row(row, checked=True)

    assert values[0] == '☑'
    assert values[7] == '🔴 ROJA'
    assert tag == 'alarm_red'
