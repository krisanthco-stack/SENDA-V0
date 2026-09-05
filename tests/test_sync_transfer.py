import json
from pathlib import Path

from app.repository import Repository
from app.services.sync_transfer import export_sync_json, export_sync_xlsx, import_sync_file


def _seed_source(repo):
    repo.insert_movements([
        {'folio':'4-100-001','derecho':'DOMINIO','plano':'H-1','fecha':'2026-01-10','codigo':'PE','operacion':'COMPRAVENTA','distrito':'HORQUETAS','fuente':'FINCAS'},
        {'folio':'4-100-001','derecho':'DOMINIO','plano':'H-1','fecha':'2026-02-10','codigo':'HI','operacion':'HIPOTECA','distrito':'HORQUETAS','fuente':'GRAVAMENES'},
        {'folio':'4-200-001','derecho':'DOMINIO','plano':'H-2','fecha':'2026-02-20','codigo':'AN','operacion':'ANOTACION','distrito':'LA VIRGEN','fuente':'ANOTACIONES'},
    ], import_id=1)
    repo.select_cases_for_control([{'folio':'4-100-001','plano':'H-1'}])
    cid = repo.list_control()[0]['id']
    repo.update_case(cid, {'responsable':'Ana','prioridad':'ALTA','note':'Revisado en equipo A'})
    repo.set_case_movement_selection(cid,[r['id'] for r in repo.case_movements(cid,limit=25)['rows']])
    repo.finalize_case(cid, 'Listo para gestión')
    repo.select_cases_for_control([{'folio':'4-200-001','plano':'H-2'}])
    return cid


def _assert_merged(target):
    assert len(target.list_movements({}, limit=100)) == 3
    management = target.list_management()
    assert len(management) == 1
    control = target.list_control()
    assert len(control) == 1 and control[0]['folio'] == '4-200-001'
    assert management[0]['folio'] == '4-100-001'
    assert management[0]['responsable'] == 'Ana'
    assert management[0]['status'] == 'GESTION'
    assert any(a['action'] == 'FINALIZAR CONTROL' for a in target.case_audit(management[0]['id']))
    d = target.dashboard({'year':2026,'quarter':'T1'})
    assert d['casos_gestion'] == 1
    assert d['casos_control'] == 1
    assert d['movimientos_tramite'] == 3


def test_json_sync_round_trip_and_second_import_is_idempotent(tmp_path):
    source = Repository(tmp_path / 'source.sqlite')
    _seed_source(source)
    package = tmp_path / 'base_senda.json'
    export_sync_json(source, package)
    raw = json.loads(package.read_text('utf-8'))
    assert raw['formato'] == 'SENDA_TRANSFER'
    assert raw['version_formato'] == 2
    assert raw['selecciones']
    assert raw['expedientes'] and raw['auditoria'] and raw['movimientos']

    target = Repository(tmp_path / 'target.sqlite')
    first = import_sync_file(target, package)
    assert first['sync'] is True
    assert first['movements_inserted'] == 3
    _assert_merged(target)
    second = import_sync_file(target, package)
    assert second['movements_inserted'] == 0
    assert second['movements_duplicates'] == 3
    _assert_merged(target)


def test_xlsx_sync_round_trip_updates_other_computer(tmp_path):
    source = Repository(tmp_path / 'source.xlsx.sqlite')
    _seed_source(source)
    package = tmp_path / 'base_senda.xlsx'
    export_sync_xlsx(source, package)
    target = Repository(tmp_path / 'target.xlsx.sqlite')
    result = import_sync_file(target, package)
    assert result['sync'] is True
    _assert_merged(target)

def test_sync_does_not_overwrite_a_newer_local_case(tmp_path):
    source = Repository(tmp_path / 'older.sqlite')
    _seed_source(source)
    package = tmp_path / 'older.json'
    export_sync_json(source, package)

    target = Repository(tmp_path / 'newer.sqlite')
    target.insert_movements([
        {'folio':'4-100-001','plano':'H-1','fecha':'2026-01-10','operacion':'COMPRAVENTA','fuente':'FINCAS','distrito':'HORQUETAS'}
    ], import_id=1)
    target.select_cases_for_control([{'folio':'4-100-001','plano':'H-1'}])
    local = target.list_control()[0]
    target.update_case(local['id'], {'responsable':'Trabajo local más reciente','note':'No reemplazar'})
    with target.connection() as c:
        c.execute("UPDATE case_files SET updated_at='2099-01-01 00:00:00' WHERE id=?", (local['id'],))

    result = import_sync_file(target, package)
    current = target.get_case(local['id'])
    assert result['cases_older_skipped'] >= 1
    assert current['responsable'] == 'Trabajo local más reciente'
    assert current['status'] == 'EN CONTROL'

def test_desktop_loader_recognizes_sync_json_without_treating_it_as_normal_movement_json(tmp_path):
    from app.desktop_model import create_context, import_files
    source = Repository(tmp_path / 'source-loader.sqlite')
    _seed_source(source)
    package = tmp_path / 'transfer-loader.json'
    export_sync_json(source, package)
    ctx = create_context(tmp_path / 'other-computer')
    result = import_files(ctx, [package], year=2026, quarter='T1', district='SIN IDENTIFICAR')
    assert result['sync_files'] == [package.name]
    assert ctx.repo.list_management()[0]['folio'] == '4-100-001'
    assert ctx.repo.list_control()[0]['folio'] == '4-200-001'


def test_sync_includes_registry_references_and_legal_metadata(tmp_path):
    source=Repository(tmp_path/'meta-source.sqlite')
    source.upsert_registry_reference({
        'PROVINCIA_INSC':'4','NUMERO_INSC':'10690','ANO_INSC':'2026',
        'CODIGO_PROVINCIA':'4','NUMERO_FINCA':'281407','SUBMATRICULA':'1'
    },'FINCAS','HORQUETAS','Fincas.csv')
    source.upsert_legal_reference({
        'CEDULAJURIDICA':'3-101-999','RAZONSOCIAL':'EMPRESA PRUEBA SA',
        'NUMERO_IDENTIFICACION':'101010101','NOMBRE':'ANA','APELLIDO_1':'MORA',
        'CARGO':'PRESIDENTE','REPRESENTACION':'D'
    },'Ced_Juridicas.xls')
    package=tmp_path/'meta.json'
    export_sync_json(source,package)
    raw=json.loads(package.read_text('utf-8'))
    assert raw['referencias_registrales'] and raw['cedulas_juridicas'] and raw['representantes']
    target=Repository(tmp_path/'meta-target.sqlite')
    result=import_sync_file(target,package)
    assert result['references_merged']==1
    assert target.list_registry_references('4-281407')
    assert target.search_legal_entities('3-101-999')[0]['razon_social']=='EMPRESA PRUEBA SA'
