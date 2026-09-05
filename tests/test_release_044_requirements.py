import json, tempfile, unittest
from pathlib import Path

from app.repository import Repository
from app.importers.engine import ImportEngine

class Release044Requirements(unittest.TestCase):
    def setUp(self):
        self.td=tempfile.TemporaryDirectory(); self.root=Path(self.td.name)
        self.repo=Repository(self.root/'senda.sqlite')
    def tearDown(self): self.td.cleanup()

    def _case_with_two_movements(self):
        self.repo.insert_movements([
            {'folio':'4-140302','fecha':'2026-03-01','distrito':'HORQUETAS','fuente':'FINCAS','codigo':'PE1','operacion':'COMPRAVENTA','archivo_origen':'a.xls'},
            {'folio':'4-140302','fecha':'2026-03-02','distrito':'HORQUETAS','fuente':'GRAVAMENES','codigo':'IA2','operacion':'HIPOTECA','archivo_origen':'b.xls'},
        ],1)
        self.repo.select_cases_for_control([{'folio':'4-140302','plano':''}])
        return self.repo.list_control()[0]['id']

    def test_control_requires_selected_movements_and_management_only_returns_selected(self):
        cid=self._case_with_two_movements()
        with self.assertRaisesRegex(ValueError,'seleccione al menos un movimiento'):
            self.repo.finalize_case(cid)
        rows=self.repo.case_movements(cid,limit=25)['rows']
        self.repo.set_case_movement_selection(cid,[rows[1]['id']])
        self.repo.finalize_case(cid)
        selected=self.repo.case_movements(cid,limit=25,selected_only=True)
        self.assertEqual(selected['total'],1)
        self.assertEqual(selected['rows'][0]['codigo'],'IA2')
        self.assertEqual(self.repo.get_case(cid)['management_state'],'PENDIENTE')

    def test_management_state_accepts_three_states_only(self):
        cid=self._case_with_two_movements(); rows=self.repo.case_movements(cid,limit=25)['rows']
        self.repo.set_case_movement_selection(cid,[rows[0]['id']]); self.repo.finalize_case(cid)
        self.assertEqual(self.repo.set_management_state(cid,'NOTIFICADO')['management_state'],'NOTIFICADO')
        self.assertEqual(self.repo.set_management_state(cid,'REGISTRADO')['management_state'],'REGISTRADO')
        with self.assertRaises(ValueError): self.repo.set_management_state(cid,'OTRO')

    def test_excel_links_are_ignored_and_not_exposed(self):
        p=self.root/'Fincas.csv'
        p.write_text('PROVINCIA;NUMERO;DERECHO;FECHA_ULT_ACT;ENLACE\n4;141174;1;01/03/2026;https://example.test/141174\n',encoding='utf-8')
        result=ImportEngine(self.repo).import_paths([p],year=2026,quarter='T1',district='HORQUETAS')
        self.assertEqual(result['inserted'],1)
        row=self.repo.list_movements()[0]
        self.assertNotIn('enlace',row)

    def test_ced_juridicas_are_reference_metadata_not_movements(self):
        p=self.root/'Ced_Juridicas_SARAPIQUI_02.03.2026.xls'
        p.write_text('CEDULAJURIDICA\tRAZONSOCIAL\tNUMERO_IDENTIFICACION\tNOMBRE\tAPELLIDO_1\tAPELLIDO_2\tCARGO\tREPRESENTACION\n3-101-1\tEMPRESA SA\t101\tANA\tMORA\tSOLIS\tPRESIDENTE\tD\n',encoding='utf-8')
        r=ImportEngine(self.repo).import_paths([p],year=2026,quarter='T1',district='HORQUETAS')
        self.assertEqual(r['inserted'],0)
        self.assertEqual(r['metadata'],1)
        self.assertEqual(len(self.repo.list_movements()),0)
        refs=self.repo.search_legal_entities('3-101-1')
        self.assertEqual(refs[0]['razon_social'],'EMPRESA SA')

    def test_numero_groups_all_rights_under_one_finca_and_preserves_right_number(self):
        p=self.root/'Fincas_SARAPIQUI_02.03.2026.xls'
        p.write_text('PROVINCIA\tDISTRITO\tNUMERO\tDERECHO\tCOD_DERECHO\tCOD_OPERACION\tFECHA_ULT_ACT\tSTATUS\n4\t3\t140302\t1\tD\tPE1\t2026-03-01\t\n4\t3\t140302\t2\tD\tIA2\t2026-03-02\t\n',encoding='utf-8')
        r=ImportEngine(self.repo).import_paths([p],year=2026,quarter='T1',district='HORQUETAS')
        self.assertEqual(r['inserted'],2)
        moves=self.repo.list_movements({'search':'140302'},limit=25)
        self.assertEqual({m['finca'] for m in moves},{'4-140302'})
        self.assertEqual({m['derecho_numero'] for m in moves},{'001','002'})
        info=self.repo.list_information({'search':'140302'},limit=25,offset=0)
        self.assertEqual(info['total'],1)
        self.assertEqual(info['rows'][0]['folio'],'4-140302')
        self.assertEqual(info['rows'][0]['movimientos'],2)
        self.repo.select_cases_for_control([{'folio':'4-140302','plano':''}])
        cid=self.repo.list_control()[0]['id']
        self.assertEqual(self.repo.case_movements(cid,limit=25)['total'],2)

    def test_archive_auxiliary_is_ignored_not_error(self):
        import zipfile
        z=self.root/'lote.zip'
        with zipfile.ZipFile(z,'w') as w:
            w.writestr('README.pdf',b'%PDF-1.4 fake')
            w.writestr('Fincas.csv','PROVINCIA;NUMERO;DERECHO;STATUS\n4;140302;0;\n')
        r=ImportEngine(self.repo).import_paths([z],year=2026,quarter='T1',district='HORQUETAS')
        self.assertEqual(r['errors'],0)
        self.assertEqual(r['ignored'],1)
        self.assertEqual(r['inserted'],1)
        self.assertEqual(self.repo.list_movements()[0]['folio'],'4-140302')

class UiAndBuildContract044(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=Path(__file__).parents[1]
        cls.html=(cls.root/'ui/index.html').read_text('utf-8')
        cls.js=(cls.root/'ui/app.js').read_text('utf-8')
        cls.css=(cls.root/'ui/app.css').read_text('utf-8')
        cls.entry=(cls.root/'SENDA_V0_DESKTOP.pyw').read_text('utf-8')
        cls.workflow=(cls.root/'.github/workflows/build-windows-desktop.yml').read_text('utf-8')
    def test_desktop_uses_webview_ui_not_tkinter(self):
        self.assertIn('app.desktop_webview',self.entry)
        self.assertNotIn('app.desktop import',self.entry)
        self.assertTrue((self.root/'app/desktop_webview.py').exists())
    def test_github_pages_and_installed_app_share_ui_directory(self):
        pages=(self.root/'index.html').read_text('utf-8')
        self.assertIn('./ui/',pages)
        self.assertIn('GitHub Pages y Windows comparten ui/',self.workflow)
        self.assertIn('--add-data "ui;ui"',self.workflow)

    def test_ui_has_copy_and_movement_selection_controls(self):
        for token in ('controlSelectPage','controlClearSelection','controlSelectedCount','copyControlCase','copyInfoCase'):
            self.assertIn(token,self.html+self.js)
        self.assertIn('data-movement-id',self.js)
        self.assertIn('navigator.clipboard',self.js)
        self.assertIn('user-select:text',self.css.replace(' ',''))
    def test_management_has_states_exports_and_no_link_feature(self):
        for token in ('PENDIENTE','NOTIFICADO','REGISTRADO','management-export'):
            self.assertIn(token,self.html+self.js)
        combined=self.html+self.js
        for forbidden in ('https://metro.sarapiqui.go.cr/','FALLBACK_LINK','linkButton','>Enlace<','>ENLACE<'):
            self.assertNotIn(forbidden,combined)
    def test_workflow_packages_same_ui_and_forbids_shadow_packages(self):
        self.assertIn('ui;ui',self.workflow)
        self.assertIn('pywebview',self.workflow.lower())
        self.assertIn('openpyxl.compat',self.workflow)
        self.assertNotIn('--add-data "vendor;vendor"',self.workflow)
        for name in ('openpyxl','xlsxwriter','et_xmlfile'):
            self.assertIn(name,self.workflow)

if __name__=='__main__': unittest.main()


def test_user_reported_numero_examples_are_recognized_searchable_and_keep_tramite_year(tmp_path):
    repo=Repository(tmp_path/'db.sqlite')
    p=tmp_path/'Fincas_SARAPIQUI_01.06.2026.xls'
    rows=[
        ('281400','2','20260039683601','QE2','2026-05-19'),
        ('281407','3','20260042421401','PE2','2026-05-20'),
        ('281408','1','20260040000001','QL2','2026-05-20'),
        ('281413','3','20260037530701','PG2','2026-05-20'),
        ('281414','3','20250095408101','PG2','2026-05-20'),
    ]
    header='PROVINCIA\tCANTON\tDISTRITO\tNUMERO\tDERECHO\tCOD_DERECHO\tPRESENTACION\tTIPO_IDENT\tNUMERO_IDENT\tCOD_OPERACION\tFECHA_ULT_ACT\tSTATUS\n'
    body=''.join(f'4\t10\t{dist}\t{num}\t0\tD\t{tramite}\t1\t0110120652\t{op}\t{fecha}\t\n' for num,dist,tramite,op,fecha in rows)
    p.write_text(header+body,encoding='utf-8')
    result=ImportEngine(repo).import_paths([p],year=2026,quarter='T2',district='HORQUETAS')
    assert result['inserted']==5 and result['skipped']==0 and result['errors']==0
    for num,_,tramite,_,_ in rows:
        info=repo.list_information({'search':num},limit=25,offset=0)
        assert info['total']==1, num
        assert info['rows'][0]['folio']==f'4-{num}'
        moves=repo.list_movements({'search':num},limit=25)
        assert len(moves)==1 and moves[0]['finca']==f'4-{num}'
        assert moves[0]['tramite']==tramite
    y2025=repo.list_information({'tramite_year':2025,'search':'281414'},limit=25,offset=0)
    assert y2025['total']==1 and y2025['rows'][0]['folio']=='4-281414'
    y2026=repo.list_information({'tramite_year':2026,'search':'281414'},limit=25,offset=0)
    assert y2026['total']==0


def test_cedula_juridica_filter_uses_tipo_ident_2(tmp_path):
    repo=Repository(tmp_path/'db.sqlite')
    repo.insert_movements([{
        'folio':'4-281407','finca':'4-281407','fecha':'2026-05-20','distrito':'HORQUETAS',
        'fuente':'FINCAS','operacion':'COMPRAVENTA','tipo_ident':'2','cedula':'3102943969',
        'titular':'EMPRESA PRUEBA SA','tramite':'20260042421401','anio_tramite':2026,
    }],1)
    r=repo.list_information({'cedula_juridica':'3-102-943969'},limit=25,offset=0)
    assert r['total']==1 and r['rows'][0]['folio']=='4-281407'


def test_rar_reference_shaped_files_are_metadata_not_movements_and_link_to_finca(tmp_path):
    import zipfile
    repo=Repository(tmp_path/'refs.sqlite')
    z=tmp_path/'SARAPIQUI.zip'
    with zipfile.ZipFile(z,'w') as w:
        w.writestr('LAS HORQUETAS/Fincas.csv',
            'PROVINCIA_INSC,NUMERO_INSC,ANO_INSC,CODIGO_PROVINCIA,NUMERO_FINCA,DUPLICADO,MATRIZ_FILIAL,SUBMATRICULA\n'
            '4,10690,2026,4,281407,,,1\n')
        w.writestr('LAS HORQUETAS/Indices_Planos.csv',
            'PROVINCIA_INSCRIPCION,NUMERO_INSCRIPCION,ANNO_INSCRIPCION,AREA,CODIGO_PROVINCIA,CODIGO_DISTRITO,PROVINCIA_FINCA,NUMERO_FINCA,IDENTIFICACION,NOMBRE\n'
            '4,10690,2026,71983,4,3,4,281407,0502010710,ANA MARIA\n')
        w.writestr('LAS HORQUETAS/Planos_Padre.csv',
            'PROVINCIA_INSC,NUMERO_INSC,ANO_INSC,PROVINCIA_PADRE,NUMERO_PADRE,ANNO_PADRE\n'
            '4,10690,2026,4,2183541,2020\n')
    result=ImportEngine(repo).import_paths([z],year=2026,quarter='T2',district='HORQUETAS')
    assert result['inserted']==0
    assert result['metadata']==3
    assert len(repo.list_movements(limit=100))==0
    refs=repo.list_registry_references('4-281407')
    assert len(refs)==3
    assert {r['kind'] for r in refs}=={'FINCAS','INDICES PLANOS','PLANOS PADRE'}
    assert all(r['plan_key']=='4-10690-2026' for r in refs)


def test_standard_fincas_numero_file_remains_a_movement_not_rar_metadata(tmp_path):
    repo=Repository(tmp_path/'mov.sqlite')
    p=tmp_path/'Fincas_SARAPIQUI_01.06.2026.xls'
    p.write_text('PROVINCIA\tDISTRITO\tNUMERO\tDERECHO\tCOD_DERECHO\tPRESENTACION\tCOD_OPERACION\tFECHA_ULT_ACT\tSTATUS\n4\t3\t281407\t0\tD\t20260042421401\tPE2\t2026-05-20\t\n',encoding='utf-8')
    result=ImportEngine(repo).import_paths([p],year=2026,quarter='T2',district='HORQUETAS')
    assert result['inserted']==1
    assert result['metadata']==0
    assert repo.list_information({'search':'281407'},limit=25,offset=0)['total']==1
