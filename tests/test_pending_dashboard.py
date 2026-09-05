from app.repository import Repository


def test_dashboard_pending_is_filtered_entities_minus_control_and_management(tmp_path):
    repo = Repository(tmp_path / 'db.sqlite')
    repo.insert_movements([
        {'folio':'4-100-001','fecha':'2026-01-10','distrito':'HORQUETAS','fuente':'FINCAS','operacion':'FINCA'},
        {'folio':'4-200-001','fecha':'2026-01-11','distrito':'HORQUETAS','fuente':'FINCAS','operacion':'FINCA'},
        {'folio':'4-300-001','fecha':'2026-01-12','distrito':'HORQUETAS','fuente':'FINCAS','operacion':'FINCA'},
        {'folio':'4-900-001','fecha':'2026-04-12','distrito':'LA VIRGEN','fuente':'FINCAS','operacion':'FINCA'},
    ], import_id=1)
    repo.select_cases_for_control([{'folio':'4-200-001'}])
    repo.select_cases_for_control([{'folio':'4-300-001'}])
    cid = next(r['id'] for r in repo.list_control() if r['folio'] == '4-300-001')
    repo.set_case_movement_selection(cid,[r['id'] for r in repo.case_movements(cid,limit=25)['rows']])
    repo.finalize_case(cid)

    d = repo.dashboard({'year':2026,'quarter':'T1'})
    assert d['folios'] == 3
    assert d['tramites_pendientes'] == 1
