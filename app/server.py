from __future__ import annotations
import json, mimetypes, os, re, shutil, subprocess, sys, tempfile, threading, traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse, unquote

from . import __version__
from .config import ensure_data_dirs
from .repository import Repository
from .importers.engine import ImportEngine
from .services.exports import export_json, export_csv, export_xlsx, export_management_case_json, export_management_case_xlsx
from .services.sync_transfer import detect_sync_file, import_sync_file, export_sync_json, export_sync_xlsx

class SendaApp:
    def __init__(self,data_dir,ui_dir):
        self.root,self.dirs=ensure_data_dirs(Path(data_dir))
        base=Path(__file__).resolve().parents[1]
        requested=Path(ui_dir) if ui_dir is not None else (base/'ui')
        fallbacks=(requested, base/'ui')
        self.ui_dir=None
        for candidate in fallbacks:
            candidate=Path(candidate)
            if (candidate/'index.html').is_file():
                self.ui_dir=candidate
                break
        if self.ui_dir is None:
            # Keep the requested location for diagnostics; GET / will return a clear 404.
            self.ui_dir=requested
        self.repo=Repository(self.dirs['database']/'senda_v0.sqlite')
        self.importer=ImportEngine(self.repo)

    def update_script(self) -> Path:
        # En el EXE one-dir de PyInstaller los scripts de mantenimiento están
        # junto a SENDA.V0.exe; en ejecución desde fuente están en la raíz.
        root=Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1]
        return root/'scripts'/'install_from_github.ps1'

    def schedule_update_from_github(self) -> dict:
        if os.name!='nt':
            raise RuntimeError('La actualización automática desde GitHub está disponible en Windows.')
        script=self.update_script()
        if not script.is_file():
            raise RuntimeError(f'No se encontró el actualizador: {script}')
        powershell=shutil.which('powershell') or shutil.which('pwsh')
        if not powershell:
            raise RuntimeError('PowerShell no está disponible para ejecutar la actualización.')
        def launch():
            flags=getattr(subprocess,'CREATE_NEW_PROCESS_GROUP',0) | getattr(subprocess,'DETACHED_PROCESS',0)
            try:
                subprocess.Popen([powershell,'-NoProfile','-ExecutionPolicy','Bypass','-File',str(script)],cwd=str(script.parent.parent),creationflags=flags,close_fds=True)
            except Exception:
                traceback.print_exc()
        threading.Timer(1.2,launch).start()
        return {'ok':True,'message':'Actualizador iniciado. SENDA se cerrará y volverá a abrir con la última Release.'}

def _filters(qs):
    def one(k,default=''):return qs.get(k,[default])[0]
    return {'year':one('year'),'quarter':one('quarter'),'month':one('month'),'district':one('district'),'alarm':one('alarm'),'source':one('source'),'movement_type':one('movement_type'),'tramite_year':one('tramite_year'),'cedula':one('cedula'),'cedula_juridica':one('cedula_juridica'),'search':one('search')}

def make_handler(app:SendaApp):
    class Handler(BaseHTTPRequestHandler):
        server_version='SENDA.V0'
        def log_message(self,fmt,*args):
            print('[SENDA.V0] '+fmt%args)
        def _json(self,payload,status=200):
            raw=json.dumps(payload,ensure_ascii=False,default=str).encode('utf-8')
            self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        def _error(self,e,status=500):
            self._json({'ok':False,'error':str(e),'type':type(e).__name__},status)
        def _send_path(self,path:Path,content_type=None,download_name=None):
            size=path.stat().st_size; self.send_response(200);self.send_header('Content-Type',content_type or mimetypes.guess_type(path.name)[0] or 'application/octet-stream');self.send_header('Content-Length',str(size))
            if download_name:self.send_header('Content-Disposition',f'attachment; filename="{download_name}"')
            self.end_headers()
            with path.open('rb') as f:
                while True:
                    chunk=f.read(1024*1024)
                    if not chunk:break
                    self.wfile.write(chunk)
        def _json_body(self,max_bytes=1024*1024):
            length=int(self.headers.get('Content-Length') or '0')
            if length<=0 or length>max_bytes:raise ValueError('Solicitud JSON inválida')
            return json.loads(self.rfile.read(length).decode('utf-8'))
        def do_GET(self):
            try:
                u=urlparse(self.path);qs=parse_qs(u.query);path=u.path
                if path=='/api/health':return self._json({'ok':True,'version':'SENDA.V0','engine_version':__version__,'data_dir':str(app.root)})
                if path=='/api/dashboard':return self._json(app.repo.dashboard(_filters(qs)))
                if path=='/api/movements':
                    limit=min(max(int(qs.get('limit',['200'])[0]),1),5000);offset=max(int(qs.get('offset',['0'])[0]),0)
                    return self._json({'ok':True,'rows':app.repo.list_movements(_filters(qs),limit=limit,offset=offset),'limit':limit,'offset':offset})
                if path=='/api/information':
                    page_size=int(qs.get('page_size',['25'])[0]);offset=max(int(qs.get('offset',['0'])[0]),0)
                    result=app.repo.list_information(_filters(qs),limit=page_size,offset=offset);result.update({'ok':True,'page_size':page_size});return self._json(result)
                if path=='/api/information/movements':
                    page_size=int(qs.get('page_size',['25'])[0]);offset=max(int(qs.get('offset',['0'])[0]),0)
                    result=app.repo.entity_movements(qs.get('folio',[''])[0],qs.get('plano',[''])[0],qs.get('movement_type',['TODOS'])[0],page_size,offset);result['ok']=True;return self._json(result)
                if path=='/api/control':return self._json({'ok':True,'rows':app.repo.list_control(qs.get('search',[''])[0])})
                if path=='/api/management':return self._json({'ok':True,'rows':app.repo.list_management(qs.get('search',[''])[0])})
                if path=='/api/management/statistics':
                    result=app.repo.management_statistics(_filters(qs));result['ok']=True;return self._json(result)
                m=re.fullmatch(r'/api/cases/(\d+)/movements',path)
                if m:
                    page_size=int(qs.get('page_size',['25'])[0]);offset=max(int(qs.get('offset',['0'])[0]),0);category=qs.get('movement_type',['TODOS'])[0]
                    selected_only=qs.get('selected_only',['0'])[0] in ('1','true','TRUE','yes');result=app.repo.case_movements(int(m.group(1)),category=category,limit=page_size,offset=offset,selected_only=selected_only);result['ok']=True;return self._json(result)
                m=re.fullmatch(r'/api/cases/(\d+)/audit',path)
                if m:return self._json({'ok':True,'rows':app.repo.case_audit(int(m.group(1)))})
                m=re.fullmatch(r'/api/cases/(\d+)',path)
                if m:
                    result=app.repo.case_detail(int(m.group(1)));result['ok']=True;return self._json(result)
                if path=='/api/catalogs':return self._json({'ok':True,'rows':app.repo.catalogs()})
                if path=='/api/imports':return self._json({'ok':True,'rows':app.repo.list_imports(min(max(int(qs.get('limit',['100'])[0]),1),1000))})
                if path=='/api/cases':return self._json({'ok':True,'rows':app.repo.list_cases(qs.get('search',[''])[0],min(max(int(qs.get('limit',['200'])[0]),1),1000))})
                if path=='/api/legal-entities':return self._json({'ok':True,'rows':app.repo.search_legal_entities(qs.get('search',[''])[0],min(max(int(qs.get('limit',['100'])[0]),1),1000))})
                if path in ('/api/sync/export/json','/api/sync/export/xlsx'):
                    kind=path.rsplit('/',1)[-1];target=app.dirs['exports']/f'SENDA_V0_BASE_FUSIONABLE.{kind}'
                    if kind=='json':export_sync_json(app.repo,target);ctype='application/json'
                    else:export_sync_xlsx(app.repo,target);ctype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                    return self._send_path(target,ctype,target.name)
                m=re.fullmatch(r'/api/cases/(\d+)/export/(json|xlsx)',path)
                if m:
                    cid=int(m.group(1));kind=m.group(2);case=app.repo.get_case(cid);base=re.sub(r'[^A-Za-z0-9_-]+','_',case.get('folio') or case.get('plano') or str(cid))
                    target=app.dirs['exports']/f'SENDA_GESTION_{base}.{kind}'
                    if kind=='json':export_management_case_json(app.repo,cid,target);ctype='application/json'
                    else:export_management_case_xlsx(app.repo,cid,target);ctype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                    return self._send_path(target,ctype,target.name)
                if path.startswith('/api/export/'):
                    kind=path.rsplit('/',1)[-1]; filters=_filters(qs)
                    ext={'json':'json','csv':'csv','xlsx':'xlsx'}.get(kind)
                    if not ext:return self._json({'ok':False,'error':'Formato de exportación inválido'},400)
                    target=app.dirs['exports']/f'SENDA_V0_export.{ext}'
                    if kind=='json':export_json(app.repo,filters,target);ctype='application/json'
                    elif kind=='csv':export_csv(app.repo,filters,target);ctype='text/csv; charset=utf-8'
                    else:export_xlsx(app.repo,filters,target);ctype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                    return self._send_path(target,ctype,target.name)
                # static
                rel='index.html' if path in ('','/') else unquote(path.lstrip('/'))
                candidate=(app.ui_dir/rel).resolve()
                if not str(candidate).startswith(str(app.ui_dir.resolve())) or not candidate.is_file():return self._json({'ok':False,'error':'No encontrado'},404)
                return self._send_path(candidate)
            except Exception as e:
                traceback.print_exc(); return self._error(e)
        def do_PATCH(self):
            try:
                u=urlparse(self.path);m=re.fullmatch(r'/api/cases/(\d+)',u.path)
                if not m:return self._json({'ok':False,'error':'No encontrado'},404)
                payload=self._json_body();case=app.repo.update_case(int(m.group(1)),payload);return self._json({'ok':True,'case':case})
            except (ValueError,KeyError) as e:return self._error(e,400)
            except Exception as e:
                traceback.print_exc();return self._error(e,500)

        def do_POST(self):
            try:
                u=urlparse(self.path);qs=parse_qs(u.query)
                if u.path=='/api/update-from-github':
                    return self._json(app.schedule_update_from_github())
                if u.path=='/api/cases':
                    payload=self._json_body();case_id=app.repo.create_case(payload.get('folio',''),payload.get('district',''),payload.get('note',''),payload.get('status','INFORMACION'),plano=payload.get('plano',''),responsable=payload.get('responsable',''),prioridad=payload.get('prioridad','NORMAL'))
                    return self._json({'ok':True,'id':case_id},201)
                if u.path=='/api/control/select':
                    payload=self._json_body();items=payload.get('items') or []
                    if not isinstance(items,list) or not items:return self._json({'ok':False,'error':'Seleccione al menos un expediente'},400)
                    return self._json({'ok':True,'selected':app.repo.select_cases_for_control(items)})
                m=re.fullmatch(r'/api/cases/(\d+)/movements/select',u.path)
                if m:
                    payload=self._json_body();ids=payload.get('movement_ids') or []
                    if not isinstance(ids,list):return self._json({'ok':False,'error':'movement_ids debe ser una lista'},400)
                    result=app.repo.set_case_movement_selection(int(m.group(1)),ids);return self._json({'ok':True,**result})
                m=re.fullmatch(r'/api/cases/(\d+)/management-state',u.path)
                if m:
                    payload=self._json_body();case=app.repo.set_management_state(int(m.group(1)),payload.get('state',''));return self._json({'ok':True,'case':case})
                m=re.fullmatch(r'/api/cases/(\d+)/finalize',u.path)
                if m:
                    payload=self._json_body();case=app.repo.finalize_case(int(m.group(1)),payload.get('note',''));return self._json({'ok':True,'case':case})
                m=re.fullmatch(r'/api/cases/(\d+)/return',u.path)
                if m:
                    payload=self._json_body();case=app.repo.return_case_to_information(int(m.group(1)),payload.get('note',''));return self._json({'ok':True,'case':case})
                if u.path!='/api/upload':return self._json({'ok':False,'error':'No encontrado'},404)
                length=int(self.headers.get('Content-Length') or '0')
                if length<=0:return self._json({'ok':False,'error':'Archivo vacío o Content-Length ausente'},400)
                filename=Path(self.headers.get('X-Filename') or qs.get('filename',['archivo.bin'])[0]).name
                filename=re.sub(r'[^A-Za-z0-9_.() -]+','_',filename) or 'archivo.bin'
                year=int(qs.get('year',['0'])[0] or 0);quarter=qs.get('quarter',[''])[0];district=qs.get('district',[''])[0]
                if year<2000 or year>2100:return self._json({'ok':False,'error':'Año inválido'},400)
                temp_dir=Path(tempfile.mkdtemp(prefix='senda_v0_upload_',dir=app.dirs['tmp']))
                temp=temp_dir/filename
                remaining=length
                try:
                    with temp.open('wb') as f:
                        while remaining:
                            chunk=self.rfile.read(min(1024*1024,remaining))
                            if not chunk:raise ConnectionError('Carga interrumpida antes de completar el archivo')
                            f.write(chunk);remaining-=len(chunk)
                    if detect_sync_file(temp):
                        result=import_sync_file(app.repo,temp)
                    else:
                        result=app.importer.import_paths([temp],year=year,quarter=quarter,district=district)
                    result['ok']=True;result['filename']=filename;return self._json(result)
                finally:
                    import shutil
                    try:shutil.rmtree(temp_dir,ignore_errors=True)
                    except Exception:pass
            except ValueError as e:return self._error(e,400)
            except Exception as e:
                traceback.print_exc();return self._error(e,500)
    return Handler

def create_server(host='127.0.0.1',port=8765,*,data_dir=None,ui_dir=None):
    base=Path(__file__).resolve().parents[1]
    app=SendaApp(data_dir or (base/'SENDA_DATA'),ui_dir or (base/'ui'))
    server=ThreadingHTTPServer((host,int(port)),make_handler(app));server.senda_app=app
    return server

def main():
    import argparse, webbrowser
    p=argparse.ArgumentParser();p.add_argument('--host',default='127.0.0.1');p.add_argument('--port',type=int,default=int(os.environ.get('SENDA_PORT','8765')));p.add_argument('--data-dir',default=None);p.add_argument('--no-browser',action='store_true');args=p.parse_args()
    server=create_server(args.host,args.port,data_dir=args.data_dir)
    print(f'SENDA.V0 servidor activo en http://{args.host}:{server.server_address[1]}')
    if not args.no_browser:
        try:webbrowser.open(f'http://{args.host}:{server.server_address[1]}')
        except Exception:pass
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
if __name__=='__main__':main()
