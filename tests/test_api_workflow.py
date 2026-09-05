import json, tempfile, threading, unittest, urllib.request
from pathlib import Path
from app.server import create_server

class ApiWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.td=tempfile.TemporaryDirectory(); cls.root=Path(cls.td.name)
        cls.server=create_server('127.0.0.1',0,data_dir=cls.root/'data',ui_dir=Path(__file__).parents[1]/'ui')
        cls.app=cls.server.senda_app; cls.port=cls.server.server_address[1]
        imp=cls.app.repo.create_import(year=2026,quarter='T1',district='HORQUETAS',source_name='seed')
        cls.app.repo.insert_movements([
            {'folio':'4-300-001','derecho':'DOMINIO','plano':'H-3','fecha':'2026-01-01','operacion':'HIPOTECA','fuente':'GRAVAMENES','tipo':'GRAVAMENES','distrito':'HORQUETAS'},
            {'folio':'4-300-001','derecho':'USUFRUCTO','plano':'H-3','fecha':'2026-02-01','operacion':'ANOTACION','fuente':'ANOTACIONES','tipo':'ANOTACIONES','distrito':'HORQUETAS'},
        ],imp)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close();cls.td.cleanup()
    def request(self,path,method='GET',payload=None):
        data=None if payload is None else json.dumps(payload).encode()
        req=urllib.request.Request(f'http://127.0.0.1:{self.port}{path}',data=data,method=method,headers={'Content-Type':'application/json'} if data else {})
        with urllib.request.urlopen(req,timeout=10) as r:return r.status,json.loads(r.read())

    def test_information_selection_control_finalize_and_management(self):
        status,info=self.request('/api/information?page_size=25&year=2026&quarter=T1')
        self.assertEqual(status,200);self.assertEqual(info['page_size'],25);self.assertTrue(info['rows'])
        _,selected=self.request('/api/control/select','POST',{'items':[{'folio':'4-300-001','plano':'H-3'}]})
        self.assertEqual(selected['selected'],1)
        _,control=self.request('/api/control');self.assertEqual(len(control['rows']),1)
        cid=control['rows'][0]['id']
        _,detail=self.request(f'/api/cases/{cid}');self.assertEqual(detail['case']['folio'],'4-300-001');self.assertEqual(detail['movimientos_total'],2)
        _,moves=self.request(f'/api/cases/{cid}/movements?page_size=25');self.assertEqual([x['fecha'] for x in moves['rows']],['2026-01-01','2026-02-01'])
        _,sel=self.request(f'/api/cases/{cid}/movements/select','POST',{'movement_ids':[x['id'] for x in moves['rows']]});self.assertEqual(sel['selected_count'],2)
        _,upd=self.request(f'/api/cases/{cid}','PATCH',{'responsable':'Ana','prioridad':'ALTA','note':'Lista'})
        self.assertTrue(upd['ok'])
        _,fin=self.request(f'/api/cases/{cid}/finalize','POST',{'note':'Finalizado'});self.assertTrue(fin['ok'])
        _,mgmt=self.request('/api/management');self.assertTrue(any(x['id']==cid for x in mgmt['rows']))

    def test_manual_case_endpoint_accepts_plano(self):
        _,created=self.request('/api/cases','POST',{'folio':'4-999-001','plano':'H-999','district':'LA VIRGEN','note':'Manual'})
        self.assertGreater(created['id'],0)

if __name__=='__main__':unittest.main()


def test_management_statistics_api_contract_source_exists():
    root=Path(__file__).parents[1]
    server=(root/'app/server.py').read_text('utf-8')
    assert "/api/management/statistics" in server
