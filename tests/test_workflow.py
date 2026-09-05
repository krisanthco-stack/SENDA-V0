import tempfile, unittest
from pathlib import Path

from app.repository import Repository
from app.importers.engine import movement_category


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.td=tempfile.TemporaryDirectory(); self.repo=Repository(Path(self.td.name)/'db.sqlite')
        self.imp=self.repo.create_import(year=2026,quarter='T1',district='HORQUETAS',source_name='muestra.csv')

    def tearDown(self): self.td.cleanup()

    def seed(self):
        rows=[
            {'folio':'4-100-001','derecho':'DOMINIO','plano':'H-1','fecha':'2026-01-10','codigo':'IA2','operacion':'HIPOTECA','tipo':'GRAVAMENES','fuente':'GRAVAMENES','distrito':'HORQUETAS'},
            {'folio':'4-100-001','derecho':'USUFRUCTO','plano':'H-1','fecha':'2026-02-12','codigo':'O83','operacion':'SERVIDUMBRE','tipo':'GRAVAMENES','fuente':'GRAVAMENES','distrito':'HORQUETAS'},
            {'folio':'4-100-001','derecho':'DOMINIO','plano':'H-1','fecha':'2026-03-20','codigo':'QL2','operacion':'SEGREGACION DE LOTE','tipo':'HISTORICOS','fuente':'HISTORICOS','distrito':'HORQUETAS'},
            {'folio':'4-200-001','derecho':'DOMINIO','plano':'H-2','fecha':'2026-01-05','codigo':'HC1','operacion':'ANOTACION','tipo':'ANOTACIONES','fuente':'ANOTACIONES','distrito':'HORQUETAS'},
        ]
        self.repo.insert_movements(rows,self.imp)

    def test_previous_classification_rules_are_recovered(self):
        self.assertEqual(movement_category('HIPOTECA','GRAVAMENES'),'HIPOTECAS')
        self.assertEqual(movement_category('SEGREGACION DE LOTE','HISTORICOS'),'SEGREGACIONES')
        self.assertEqual(movement_category('SERVIDUMBRE','GRAVAMENES'),'GRAVÁMENES')
        self.assertEqual(movement_category('ANOTACION','ANOTACIONES'),'ANOTACIONES')
        self.assertEqual(movement_category('','FINCAS'),'FINCAS')

    def test_information_groups_by_folio_with_counts_and_oldest_first(self):
        self.seed()
        result=self.repo.list_information({'year':'2026','quarter':'T1'},limit=25,offset=0)
        self.assertEqual(result['total'],2)
        self.assertEqual([r['folio'] for r in result['rows']],['4-200','4-100'])
        row=next(r for r in result['rows'] if r['folio']=='4-100')
        self.assertEqual(row['movimientos'],3)
        self.assertEqual(row['derechos'],2)
        self.assertEqual(row['categorias']['HIPOTECAS'],1)
        self.assertEqual(row['categorias']['SEGREGACIONES'],1)

    def test_information_supports_category_filter_and_page_sizes(self):
        self.seed()
        r=self.repo.list_information({'movement_type':'HIPOTECAS'},limit=25,offset=0)
        self.assertEqual(r['total'],1); self.assertEqual(r['rows'][0]['folio'],'4-100')
        with self.assertRaises(ValueError): self.repo.list_information({},limit=30,offset=0)
        for size in (25,50,100): self.repo.list_information({},limit=size,offset=0)

    def test_manual_case_can_be_created_edited_selected_finalized_and_returned(self):
        self.seed()
        cid=self.repo.create_case('4-100-001','HORQUETAS','Revisar','INFORMACION',plano='H-1')
        self.repo.update_case(cid,{'responsable':'Ana','prioridad':'ALTA','note':'Revisión prioritaria'})
        self.repo.select_cases_for_control([{'folio':'4-100-001','plano':'H-1'}])
        case=self.repo.get_case(cid); self.assertEqual(case['status'],'EN CONTROL'); self.assertEqual(case['responsable'],'Ana')
        detail=self.repo.case_detail(cid); self.assertEqual(len(detail['derechos']),2); self.assertEqual(detail['movimientos_total'],3)
        page=self.repo.case_movements(cid,category='TODOS',limit=25,offset=0)
        self.assertEqual([r['fecha'] for r in page['rows']],sorted(r['fecha'] for r in page['rows']))
        self.repo.set_case_movement_selection(cid,[r['id'] for r in page['rows']])
        self.repo.finalize_case(cid,note='Revisión completa')
        self.assertEqual(self.repo.get_case(cid)['status'],'GESTION')
        info=self.repo.list_information({},limit=25,offset=0)
        self.assertNotIn('4-100-001',[r['folio'] for r in info['rows']])
        self.assertEqual(self.repo.list_management()[0]['folio'],'4-100-001')
        self.repo.return_case_to_information(cid,note='Revisar nuevamente')
        self.assertEqual(self.repo.get_case(cid)['status'],'INFORMACION')
        self.assertGreaterEqual(len(self.repo.case_audit(cid)),4)

    def test_dashboard_counts_total_and_movements_in_control_or_management(self):
        self.seed()
        self.repo.select_cases_for_control([{'folio':'4-100-001','plano':'H-1'}])
        d=self.repo.dashboard({'year':'2026','quarter':'T1'})
        self.assertEqual(d['movimientos'],4)
        self.assertEqual(d['movimientos_tramite'],3)
        self.assertEqual(d['por_categoria']['HIPOTECAS'],1)
        self.assertEqual(d['por_categoria']['SEGREGACIONES'],1)

    def test_legacy_020_database_is_migrated_without_losing_loaded_data(self):
        import sqlite3
        legacy=Path(self.td.name)/'legacy.sqlite'
        c=sqlite3.connect(legacy)
        c.executescript("""
        CREATE TABLE movements(id INTEGER PRIMARY KEY AUTOINCREMENT,folio TEXT,derecho TEXT,plano TEXT,fecha TEXT,codigo TEXT,operacion TEXT,tipo TEXT,fuente TEXT,cedula TEXT,titular TEXT,anio INTEGER,mes INTEGER,trimestre TEXT,distrito TEXT,archivo_origen TEXT,import_id INTEGER,raw_json TEXT);
        CREATE TABLE case_files(id INTEGER PRIMARY KEY AUTOINCREMENT,folio TEXT,distrito TEXT,status TEXT DEFAULT 'PENDIENTE',note TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE imports(id INTEGER PRIMARY KEY AUTOINCREMENT,created_at TEXT DEFAULT CURRENT_TIMESTAMP,anio INTEGER,trimestre TEXT,distrito TEXT,source_name TEXT,source_hash TEXT,records INTEGER DEFAULT 0,skipped INTEGER DEFAULT 0,errors INTEGER DEFAULT 0,status TEXT DEFAULT 'PROCESSING');
        CREATE TABLE catalogs(kind TEXT NOT NULL,code TEXT NOT NULL,class_code TEXT NOT NULL DEFAULT '',description TEXT,source_file TEXT,PRIMARY KEY(kind,code,class_code));
        CREATE TABLE case_attachments(id INTEGER PRIMARY KEY AUTOINCREMENT,case_id INTEGER NOT NULL,filename TEXT,stored_path TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT);
        INSERT INTO movements(folio,derecho,plano,fecha,operacion,fuente,anio,mes,trimestre,distrito) VALUES('4-777-001','DOMINIO','H-777','2026-01-01','HIPOTECA','GRAVAMENES',2026,1,'T1','HORQUETAS');
        INSERT INTO case_files(folio,distrito,status,note) VALUES('4-777-001','HORQUETAS','PENDIENTE','Existente');
        """);c.commit();c.close()
        migrated=Repository(legacy)
        rows=migrated.list_movements({'year':'2026'},limit=25)
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['categoria'],'HIPOTECAS')
        case=migrated.list_cases('777')[0];self.assertEqual(case['status'],'INFORMACION');self.assertEqual(case['note'],'Existente')

    def test_export_rows_include_category_and_workflow_state(self):
        from app.services.exports import export_json
        self.seed();self.repo.select_cases_for_control([{'folio':'4-100-001','plano':'H-1'}])
        target=Path(self.td.name)/'out.json';export_json(self.repo,{},target)
        payload=__import__('json').loads(target.read_text('utf-8'))
        row=next(x for x in payload['movimientos'] if x['folio']=='4-100-001' and x['categoria']=='HIPOTECAS')
        self.assertTrue(row['en_control']);self.assertEqual(row['estado_expediente'],'EN CONTROL')


if __name__=='__main__':unittest.main()
