import json, tempfile, threading, unittest, urllib.request
from pathlib import Path
from app.server import create_server

class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.td=tempfile.TemporaryDirectory(); cls.root=Path(cls.td.name)
        cls.server=create_server('127.0.0.1',0,data_dir=cls.root/'data',ui_dir=Path(__file__).parents[1]/'ui')
        cls.port=cls.server.server_address[1]
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True); cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.td.cleanup()
    def get(self,path):
        with urllib.request.urlopen(f'http://127.0.0.1:{self.port}{path}',timeout=10) as r:return r.status,r.headers,r.read()

    def test_health(self):
        status,_,body=self.get('/api/health'); payload=json.loads(body)
        self.assertEqual(status,200); self.assertTrue(payload['ok']); self.assertEqual(payload['version'],'SENDA.V0')

    def test_stream_upload_and_filtered_dashboard(self):
        body=b'PROVINCIA;NUMERO;DERECHO;FECHA_ULT_ACT\n4;900;1;01/03/2026\n'
        url=f'http://127.0.0.1:{self.port}/api/upload?year=2026&quarter=T1&district=Horquetas'
        req=urllib.request.Request(url,data=body,method='POST',headers={'Content-Type':'application/octet-stream','X-Filename':'Fincas.csv'})
        with urllib.request.urlopen(req,timeout=20) as r:result=json.loads(r.read())
        self.assertEqual(result['inserted'],1)
        _,_,raw=self.get('/api/dashboard?year=2026&quarter=T1&month=3&district=HORQUETAS')
        d=json.loads(raw); self.assertGreaterEqual(d['movimientos'],1); self.assertGreaterEqual(d['folios'],1)


    def test_zip_upload_via_http_imports_internal_files(self):
        import io, zipfile
        buf=io.BytesIO()
        with zipfile.ZipFile(buf,'w',compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr('Fincas_HORQUETAS.csv','PROVINCIA;NUMERO;DERECHO;FECHA_ULT_ACT\n4;99001;1;15/03/2026\n')
        url=f'http://127.0.0.1:{self.port}/api/upload?year=2026&quarter=T1&district=Horquetas'
        req=urllib.request.Request(url,data=buf.getvalue(),method='POST',headers={'Content-Type':'application/octet-stream','X-Filename':'HORQUETAS_T1.zip'})
        with urllib.request.urlopen(req,timeout=20) as r: result=json.loads(r.read())
        self.assertEqual(result['inserted'],1)
        self.assertIn('Fincas_HORQUETAS.csv',result['files'])

    def test_json_csv_and_xlsx_exports(self):
        for path,ctype in [('/api/export/json','application/json'),('/api/export/csv','text/csv'),('/api/export/xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')]:
            status,headers,body=self.get(path)
            self.assertEqual(status,200); self.assertIn(ctype,headers.get('Content-Type','')); self.assertGreater(len(body),20)
        _,_,xlsx=self.get('/api/export/xlsx')
        self.assertTrue(xlsx.startswith(b'PK'))

    def test_import_history_and_cases_api(self):
        _,_,raw=self.get('/api/imports'); history=json.loads(raw); self.assertIn('rows',history)
        url=f'http://127.0.0.1:{self.port}/api/cases'
        req=urllib.request.Request(url,data=json.dumps({'folio':'4-200103-001','district':'Horquetas','note':'Revisión'}).encode(),method='POST',headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=10) as r:created=json.loads(r.read())
        self.assertTrue(created['ok']); self.assertGreater(created['id'],0)
        _,_,raw=self.get('/api/cases?search=200103'); cases=json.loads(raw); self.assertTrue(any(x['folio']=='4-200103-001' for x in cases['rows']))

    def test_root_serves_horizontal_ui(self):
        status,headers,body=self.get('/')
        self.assertEqual(status,200); self.assertIn(b'SENDA.V0',body); self.assertIn('text/html',headers.get('Content-Type',''))

if __name__=='__main__':unittest.main()
