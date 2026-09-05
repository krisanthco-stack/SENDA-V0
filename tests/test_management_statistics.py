from app.repository import Repository


def test_management_statistics_counts_finalized_cases_by_month_and_district(tmp_path):
    repo = Repository(tmp_path / 'db.sqlite')
    repo.insert_movements([{'folio':'4-1','fecha':'2026-01-01','distrito':'HORQUETAS','fuente':'FINCAS','operacion':'FINCA'},{'folio':'4-2','fecha':'2026-02-01','distrito':'LA VIRGEN','fuente':'FINCAS','operacion':'FINCA'}],1)
    repo.create_case('4-1','HORQUETAS')
    repo.create_case('4-2','LA VIRGEN')
    repo.select_cases_for_control([{'folio':'4-1'},{'folio':'4-2'}])
    ids = {r['folio']:r['id'] for r in repo.list_control()}
    for folio in ('4-1','4-2'):
        cid=ids[folio];repo.set_case_movement_selection(cid,[r['id'] for r in repo.case_movements(cid,limit=25)['rows']]);repo.finalize_case(cid)
    with repo.connection() as c:
        c.execute("UPDATE case_files SET finalized_at='2026-01-15 10:00:00', management_started_at='2026-01-15 10:00:00' WHERE folio='4-1'")
        c.execute("UPDATE case_files SET finalized_at='2026-02-20 10:00:00', management_started_at='2026-02-20 10:00:00' WHERE folio='4-2'")
    stats = repo.management_statistics({'year':2026,'quarter':'T1'})
    assert stats['total'] == 2
    assert stats['por_mes'] == {1:1, 2:1}
    assert stats['por_distrito']['HORQUETAS'] == 1
    assert stats['por_distrito']['LA VIRGEN'] == 1
