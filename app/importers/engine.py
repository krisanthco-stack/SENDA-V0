from __future__ import annotations
import csv, ctypes, ctypes.util, hashlib, io, itertools, json, os, re, shutil, stat, subprocess, sys, tempfile, unicodedata, zipfile
from contextlib import ExitStack
from pathlib import Path
from typing import Iterable, Iterator

from app.domain import normalize_district, parse_date, quarter_for_month

OLE_MAGIC=bytes.fromhex('D0CF11E0A1B11AE1')
ZIP_MAGIC=b'PK\x03\x04'
RAR4_MAGIC=b'Rar!\x1a\x07\x00'
RAR5_MAGIC=b'Rar!\x1a\x07\x01\x00'
SUPPORTED_IMPORT_FORMATS=('XLS','XLSX','CSV','JSON','TXT','ZIP','RAR')

SOURCE_NAMES={
 'FINCAS_GENERADAS':'FINCAS GENERADAS','FINCAS':'FINCAS','SEGREGACIONES':'SEGREGACIONES','HISTORICOS':'HISTORICOS',
 'GRAVAMENES':'GRAVAMENES','CERRADAS':'CERRADAS','CED_JURIDICAS':'CEDULAS JURIDICAS','CEDULAS_JURIDICAS':'CEDULAS JURIDICAS',
 'ANOTACIONES':'ANOTACIONES','INDICES_PLANOS':'INDICES PLANOS','PLANOS_HIJO':'PLANOS HIJO','PLANOS_PADRE':'PLANOS PADRE'
}
RIGHT_TYPES={'D':'DOMINIO','H':'HABITACION','N':'NUDA','U':'USUFRUCTO','S':'USO','C':'USUFRUCTO CONJUNTO'}

def movement_category(operation, source='') -> str:
    """Clasifica movimientos con las reglas funcionales recuperadas de SENDA 02."""
    text=keynorm(f'{clean(operation)} {clean(source)}')
    if 'HIPOTECA' in text:return 'HIPOTECAS'
    if 'SEGREG' in text:return 'SEGREGACIONES'
    if 'ANOT' in text:return 'ANOTACIONES'
    if any(k in text for k in ('GRAVAM','SERVIDUM','EMBARGO','LIMITACION','DEMANDA')):return 'GRAVÁMENES'
    if 'CIERRE' in text or 'CERRAD' in text:return 'CERRADAS'
    src=keynorm(source)
    if src in ('FINCAS','FINCAS_GENERADAS'):return 'FINCAS'
    if 'HISTOR' in src:return 'HISTÓRICOS'
    if 'CERRAD' in src:return 'CERRADAS'
    return 'OTROS'


def clean(v):
    if v is None:return ''
    if isinstance(v,float) and v.is_integer(): return str(int(v))
    return re.sub(r'\s+',' ',str(v).strip())

def keynorm(v):
    s=unicodedata.normalize('NFKD',clean(v)).encode('ascii','ignore').decode('ascii').upper()
    return re.sub(r'[^A-Z0-9]+','_',s).strip('_')

def digits(v): return re.sub(r'\D','',clean(v))

def decode_sample(data:bytes):
    # BOMs are definitive encoding markers. Scoring them as CP1252 turns the
    # UTF-8 BOM (EF BB BF) into visible characters and corrupts the first
    # header (for example PROVINCIA -> IPROVINCIA after normalization).
    if data.startswith(b'\xef\xbb\xbf'):
        return (10**9,'utf-8-sig',data.decode('utf-8-sig',errors='replace'))
    if data.startswith((b'\xff\xfe',b'\xfe\xff')):
        return (10**9,'utf-16',data.decode('utf-16',errors='replace'))
    candidates=[]
    for enc in ('utf-8-sig','cp1252','latin-1','utf-16'):
        try:t=data.decode(enc)
        except Exception:continue
        printable=sum(ch.isprintable() or ch in '\r\n\t' for ch in t); bad=t.count('\ufffd'); seps=t.count(';')+t.count('\t')+t.count(',')
        candidates.append((printable+seps*6-bad*50,enc,t))
    return max(candidates,key=lambda x:x[0]) if candidates else (0,'utf-8','')

def detect_format(path: str|Path) -> str:
    p=Path(path)
    with p.open('rb') as f: head=f.read(16)
    if head.startswith(OLE_MAGIC): return 'xls'
    if head.startswith(ZIP_MAGIC):
        if p.suffix.lower()=='.xlsx': return 'xlsx'
        return 'zip'
    if head.startswith(RAR4_MAGIC) or head.startswith(RAR5_MAGIC): return 'rar'
    ext=p.suffix.lower()
    if ext=='.json': return 'json'
    if ext in ('.csv','.txt','.xls'):
        if is_catalog_name(p.name): return 'catalog'
        return 'delimited'
    if ext=='.xlsx': return 'xlsx'
    if ext=='.rar': return 'rar'
    return 'unknown'

def is_catalog_name(name): return 'CATALOGO_COD_' in keynorm(Path(name).name)

def catalog_kind(name):
    n=keynorm(Path(name).stem)
    for key,label in (('OPERACIONES','operaciones'),('DERECHOS','derechos'),('CLASE_RESP','clase_resp'),('STATUS','status'),('PROPORCIONES','proporciones'),('MONEDAS','monedas')):
        if key in n:return label
    return 'catalogo'

def detect_source(path: str|Path, headers: Iterable[str]=()) -> str:
    stem=keynorm(Path(path).stem)
    for key in sorted(SOURCE_NAMES,key=len,reverse=True):
        if key in stem:return SOURCE_NAMES[key]
    hs={keynorm(x) for x in headers}
    if {'CEDULAJURIDICA','RAZONSOCIAL'} & hs:return 'CEDULAS JURIDICAS'
    if {'PLANO_PADRE','PLANO_HIJO'} & hs:return 'PLANOS'
    if {'PROVINCIA','NUMERO','DERECHO'} <= hs:return 'FINCAS'
    return 'MOVIMIENTOS'

def is_registry_reference(source:str, headers:Iterable[str]) -> bool:
    hs={keynorm(x) for x in headers}
    src=keynorm(source)
    if src in {'INDICES_PLANOS','PLANOS_HIJO','PLANOS_PADRE','PLANOS','FINCAS_GENERADAS'}:
        return True
    if src=='FINCAS' and ('NUMERO_FINCA' in hs or 'NUMERO_INSC' in hs or 'NUMERO_INSCRIPCION' in hs):
        movement_markers={'COD_OPERACION','FECHA_ULT_ACT','PRESENTACION','STATUS','COD_STATUS'}
        if not (hs & movement_markers):return True
    return False

def _delimiter(first_line:str):
    return max(('\t',';',','), key=lambda d:first_line.count(d))

STATUS_FIELDS={'STATUS','COD_STATUS','ESTADO'}

def _source_cell_value(header, value):
    key=keynorm(header)
    # El exportador registral usa campo vacío para SQL NULL (ACTIVA) y un
    # espacio para BLANCO (OMITIR). No limpiar STATUS antes de clasificarlo.
    if key in STATUS_FIELDS:
        return value
    return clean(value)

def iter_delimited(path:Path) -> Iterator[dict]:
    with path.open('rb') as bf:
        sample=bf.read(65536); _,enc,text=decode_sample(sample); first=next((ln for ln in text.splitlines() if ln.strip()),''); delim=_delimiter(first); bf.seek(0)
        wrapper=io.TextIOWrapper(bf,encoding=enc,errors='replace',newline='')
        for row in csv.DictReader(wrapper,delimiter=delim):
            if row: yield {keynorm(k):_source_cell_value(k,v) for k,v in row.items() if k is not None}

def iter_xlsx(path:Path) -> Iterator[dict]:
    vendor=Path(__file__).resolve().parents[2]/'vendor'
    if vendor.exists(): sys.path.insert(0,str(vendor))
    try: from openpyxl import load_workbook
    except Exception as e: raise RuntimeError('XLSX reconocido pero openpyxl no está disponible.') from e
    wb=load_workbook(path,read_only=True,data_only=True)
    try:
        ws=wb[wb.sheetnames[0]]; it=ws.iter_rows(values_only=True)
        try: headers=[keynorm(v) for v in next(it)]
        except StopIteration:return
        for values in it:
            row={h:_source_cell_value(h,v) for h,v in zip(headers,values) if h}
            if any(row.values()):yield row
    finally: wb.close()

def _convert_xls_to_csv(path:Path, outdir:Path) -> Path:
    # Prefer the xlrd copy vendored with SENDA so .xls does not depend on Excel/LibreOffice.
    vendor=Path(__file__).resolve().parents[2]/'vendor'
    if vendor.exists() and str(vendor) not in sys.path: sys.path.insert(0,str(vendor))
    try:
        import xlrd  # type: ignore
        book=xlrd.open_workbook(str(path),on_demand=True,ignore_workbook_corruption=True)
        sh=book.sheet_by_index(0); out=outdir/(path.stem+'.csv')
        with out.open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.writer(f,delimiter=';')
            for rx in range(sh.nrows):
                vals=[]
                for cx in range(sh.ncols):
                    cell=sh.cell(rx,cx); v=cell.value
                    if cell.ctype==getattr(xlrd,'XL_CELL_DATE',3):
                        try:v=xlrd.xldate_as_datetime(v,book.datemode).strftime('%Y-%m-%d')
                        except Exception:pass
                    if isinstance(v,float) and v.is_integer():v=str(int(v))
                    elif v is None:v=''
                    elif not isinstance(v,str):v=str(v)
                    vals.append(v)
                w.writerow(vals)
        try:book.release_resources()
        except Exception:pass
        return out
    except Exception: pass
    office=shutil.which('libreoffice') or shutil.which('soffice')
    if office:
        cp=subprocess.run([office,'--headless','--convert-to','csv','--outdir',str(outdir),str(path)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=300)
        out=outdir/(path.stem+'.csv')
        if cp.returncode==0 and out.exists():return out
    if os.name=='nt':
        ps=shutil.which('powershell') or shutil.which('pwsh')
        if ps:
            out=outdir/(path.stem+'.csv')
            script=("$ErrorActionPreference='Stop';$src=$args[0];$dst=$args[1];$xl=New-Object -ComObject Excel.Application;"
                    "$xl.Visible=$false;$xl.DisplayAlerts=$false;try{$wb=$xl.Workbooks.Open($src);$wb.Worksheets.Item(1).Activate();"
                    "$wb.SaveAs($dst,62);$wb.Close($false)}finally{$xl.Quit()}")
            cp=subprocess.run([ps,'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-Command',script,str(path),str(out)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=300)
            if cp.returncode==0 and out.exists():return out
    raise RuntimeError('XLS binario reconocido. Para leerlo se requiere el motor BIFF incluido/opcional (xlrd), Microsoft Excel o LibreOffice. SENDA no tratará el XLS como texto.')

def iter_xls(path:Path) -> Iterator[dict]:
    with tempfile.TemporaryDirectory(prefix='senda_v0_xls_') as td:
        csvp=_convert_xls_to_csv(path,Path(td))
        yield from iter_delimited(csvp)

def iter_json_array_stream(path:Path) -> Iterator[object]:
    dec=json.JSONDecoder()
    with path.open('r',encoding='utf-8-sig',errors='replace') as f:
        buf=''; pos=0; started=False; done=False
        while not done:
            chunk=f.read(1024*1024)
            if chunk: buf=buf[pos:]+chunk; pos=0
            elif pos>=len(buf):break
            while True:
                while pos<len(buf) and buf[pos].isspace():pos+=1
                if not started:
                    if pos>=len(buf):break
                    if buf[pos]!='[':raise ValueError('JSON no es una lista')
                    started=True;pos+=1;continue
                while pos<len(buf) and (buf[pos].isspace() or buf[pos]==','):pos+=1
                if pos<len(buf) and buf[pos]==']':done=True;pos+=1;break
                if pos>=len(buf):break
                try:item,end=dec.raw_decode(buf,pos)
                except json.JSONDecodeError:
                    if chunk:break
                    raise
                pos=end;yield item
            if not chunk and not done:break

def iter_json(path:Path) -> Iterator[dict]:
    with path.open('r',encoding='utf-8-sig',errors='replace') as f:
        first=''
        while not first:
            ch=f.read(1)
            if not ch:return
            if not ch.isspace():first=ch
    if first=='[':
        for obj in iter_json_array_stream(path):
            if isinstance(obj,dict):yield {keynorm(k):v for k,v in obj.items()}
        return
    if first=='{':
        with path.open('r',encoding='utf-8-sig',errors='replace') as f: obj=json.load(f)
        seq=next((obj.get(k) for k in ('movimientos','MOVIMIENTOS','data','records') if isinstance(obj.get(k),list)),None)
        if seq is None: seq=[obj]
        for row in seq:
            if isinstance(row,dict):yield {keynorm(k):v for k,v in row.items()}
        return
    with path.open('r',encoding='utf-8-sig',errors='replace') as f:
        for line in f:
            line=line.strip()
            if line:
                row=json.loads(line)
                if isinstance(row,dict):yield {keynorm(k):v for k,v in row.items()}

def iter_rows(path:Path) -> Iterator[dict]:
    fmt=detect_format(path)
    if fmt in ('delimited','catalog'):yield from iter_delimited(path)
    elif fmt=='xls':yield from iter_xls(path)
    elif fmt=='xlsx':yield from iter_xlsx(path)
    elif fmt=='json':yield from iter_json(path)
    else: raise RuntimeError(f'Formato no tabular: {fmt}')

def parse_catalog(path:Path) -> list[dict]:
    kind=catalog_kind(path.name); data=path.read_bytes(); _,_,text=decode_sample(data); out=[]
    for raw in text.splitlines():
        line=raw.strip()
        if not line:continue
        vals=[clean(v) for v in next(csv.reader([line],delimiter=';',quotechar='"'),[])]
        if kind=='operaciones' and len(vals)>=3 and vals[0]:out.append({'kind':kind,'code':vals[0],'class_code':vals[1],'description':vals[2]})
        elif kind in ('derechos','proporciones','monedas','clase_resp') and len(vals)>=2:out.append({'kind':kind,'code':vals[0],'class_code':'','description':vals[1]})
        elif kind=='status':
            u=keynorm(line)
            if 'VALOR_D' in u and 'CERRAD' in u:out.append({'kind':kind,'code':'D','class_code':'','description':'CERRADA'})
            if 'VALOR_NULL' in u and 'ACTIV' in u:out.append({'kind':kind,'code':'NULL','class_code':'','description':'ACTIVA'})
            if 'VALOR_B' in u and 'OMIT' in u:
                out.extend([{'kind':kind,'code':'B','class_code':'','description':'OMITIR'},{'kind':kind,'code':'BLANCO','class_code':'','description':'OMITIR'}])
    return out

CR_PROVINCE_CODES={
    'SAN_JOSE':'1','ALAJUELA':'2','CARTAGO':'3','HEREDIA':'4',
    'GUANACASTE':'5','PUNTARENAS':'6','LIMON':'7',
}

def _province_code(value):
    raw=clean(value)
    d=digits(raw)
    if d:
        try:
            n=int(d)
            if 1 <= n <= 7:return str(n)
        except ValueError:
            pass
    return CR_PROVINCE_CODES.get(keynorm(raw),'')

def _folio_number(row):
    # Regla SENDA: NUMERO es la finca/folio autoritativa cuando existe.
    # Los alias cubren variantes habituales de encabezados de Excel.
    for key in ('NUMERO','NUMERO_DE_FINCA','NUMERO_FINCA','NRO_FINCA','NRO','FINCA','NUM_FINCA','MATRICULA'):
        raw=clean(row.get(key))
        if not raw:continue
        full=re.match(r'^\s*(\d+)\s*-\s*(\d+)(?:\s*-\s*(\d+))?\s*$',raw)
        if full:return str(int(full.group(2)))
        d=digits(raw)
        if d:return str(int(d))
    return ''

def _folio_components(row):
    """Devuelve (folio completo, finca base, número de derecho).

    NUMERO es la identidad autoritativa de la finca. DERECHO distingue derechos
    registrales dentro de esa misma finca, pero nunca puede hacer que SENDA
    pierda o cambie el NUMERO.
    """
    existing=clean(row.get('FOLIO_REAL') or row.get('FOLIO'))
    existing_match=re.match(r'^\s*(\d+)\s*-\s*(\d+)(?:\s*-\s*(\d{1,3}))?\s*$',existing)
    num=_folio_number(row)
    if num:
        prov=_province_code(row.get('PROVINCIA') or row.get('PROV'))
        raw_right=digits(row.get('DERECHO') or row.get('CONSEC_DERECHO'))
        if existing_match and str(int(existing_match.group(2)))==num:
            if not prov:prov=str(int(existing_match.group(1)))
            if not raw_right and existing_match.group(3):raw_right=existing_match.group(3)
        right_num=f'{int(raw_right):03d}' if raw_right and int(raw_right)!=0 else ''
        if prov:
            finca=f'{int(prov)}-{int(num)}'
            folio=f'{finca}-{right_num}' if right_num and int(right_num)!=0 else finca
            return folio,finca,right_num
        finca=str(int(num))
        folio=f'{finca}-{right_num}' if right_num and int(right_num)!=0 else finca
        return folio,finca,right_num
    if existing_match:
        prov,num0,right0=existing_match.groups();finca=f'{int(prov)}-{int(num0)}'
        right_num=f'{int(right0):03d}' if right0 else ''
        folio=f'{finca}-{right_num}' if right_num and int(right_num)!=0 else finca
        return folio,finca,right_num
    return existing,existing,''

def _folio(row):
    return _folio_components(row)[0]

def _owner(row):
    direct=clean(row.get('TITULAR') or row.get('RAZON_SOCIAL') or row.get('RAZONSOCIAL'))
    if direct:return direct
    return ' '.join(clean(row.get(k)) for k in ('NOMBRE','APELLIDO_1','APELLIDO1','APELLIDO_2','APELLIDO2') if clean(row.get(k)))

def _date(row):
    for k in ('FECHA_PROCESO','FECHA_INICIA','FECHAPR','FECHA_ULT_ACT','FECHA','FECHA_MOVIMIENTO'):
        d=parse_date(row.get(k))
        if d:return d
    return None

def _link(row):
    for k in ('ENLACE','LINK','URL','HIPERVINCULO','VINCULO','DIRECCION_WEB'):
        v=clean(row.get(k))
        if v:return v
    candidate=clean(row.get('ID'))
    if re.match(r'^https?://',candidate,re.I):return candidate
    return ''

def district_from_path(path: Path, fallback: str = '') -> str:
    # Archives supplied by SENDA commonly group files by district folder.
    # Prefer the closest recognizable path component over the import-wide fallback.
    parts = list(path.parts[:-1])
    for part in reversed(parts):
        d = normalize_district(part)
        if d != 'SIN IDENTIFICAR':
            return d
    d = normalize_district(fallback)
    return d


def catalog_context(repo):
    ctx={'operations':{},'rights':dict(RIGHT_TYPES),'omit_status':{'B','BLANCO'},'omit_class_resp':{'9'}}
    for e in repo.catalogs():
        kind=e['kind']; code=clean(e['code']); cl=clean(e['class_code']); desc=clean(e['description'])
        if kind=='operaciones':
            if cl:ctx['operations'][code+cl]=desc
            ctx['operations'].setdefault(code,desc)
        elif kind=='derechos':ctx['rights'][keynorm(code)]=desc
        elif kind=='status' and keynorm(desc)=='OMITIR':ctx['omit_status'].add('BLANCO' if keynorm(code)=='BLANCO' else keynorm(code))
        elif kind=='clase_resp' and 'OMIT' in keynorm(desc):ctx['omit_class_resp'].add(keynorm(code))
    return ctx

def normalize_row(row:dict, *, source:str, year:int, quarter:str, district:str, source_file:str, ctx:dict):
    r={keynorm(k):v for k,v in row.items()}
    status_key=next((k for k in ('STATUS','COD_STATUS','ESTADO') if k in r),None)
    if status_key is not None:
        raw_status=r.get(status_key)
        # En los TXT/XLS registrales: campo vacío = NULL/ACTIVA; un campo con
        # solo espacios = BLANCO/OMITIR. Esta distinción se pierde si se hace
        # clean() antes de evaluar el estado.
        if raw_status is None or raw_status=='':status='NULL'
        elif isinstance(raw_status,str) and raw_status.strip()=='':status='BLANCO'
        else:status=keynorm(raw_status)
        if status in ctx['omit_status']:return None
    resp=next((r.get(k) for k in ('CLASE_RESP','COD_CLASE_RESP','CLASE_RESPONSABILIDAD') if k in r),None)
    if resp is not None and keynorm(resp) in ctx['omit_class_resp']:return None
    code=clean(r.get('COD_OPERACION') or r.get('COD_OPER') or r.get('CODIGO'))
    cl=clean(r.get('CLASE_CODIGO') or r.get('CLASE_OPERACION') or r.get('CLASE'))
    full=code+cl if code and cl and not code.endswith(cl) else code
    op=clean(r.get('DESCRIP_OPER') or r.get('OPERACION')) or ctx['operations'].get(full) or ctx['operations'].get(code) or full or source
    d=_date(r); row_year=d.year if d else int(year); month=d.month if d else 0; row_quarter=quarter_for_month(month) if month else quarter
    row_district=normalize_district(r.get('DISTRITO') or r.get('NOMBRE_DISTRITO') or district)
    right=ctx['rights'].get(keynorm(r.get('COD_DERECHO')),'') or clean(r.get('TIPO_DERECHO'))
    # La identidad del movimiento se calcula después de normalizarlo en Repository.
    # Columnas auxiliares del archivo no deben convertir un mismo movimiento lógico
    # en uno nuevo cuando el corte llega renombrado o dentro de otro ZIP/RAR.
    folio,finca,derecho_numero=_folio_components(r)
    tramite=clean(r.get('PRESENTACION') or r.get('NUM_TRAMITE') or r.get('NUMERO_TRAMITE') or r.get('TRAMITE'))
    tramite_digits=digits(tramite)
    tramite_year=0
    if len(tramite_digits)>=4:
        try:
            candidate=int(tramite_digits[:4])
            if 1900 <= candidate <= 2100:tramite_year=candidate
        except ValueError:
            pass
    return {'folio':folio,'finca':finca,'derecho_numero':derecho_numero,'derecho':right,'plano':clean(r.get('NUM_PLANO') or r.get('PLANO')),'fecha':d.isoformat() if d else '',
            'codigo':full,'operacion':op,'tipo':source,'fuente':source,'categoria':movement_category(op,source),'cedula':clean(r.get('NUMERO_IDENT') or r.get('CEDULA') or r.get('CEDULAJURIDICA')),
            'tipo_ident':clean(r.get('TIPO_IDENT') or r.get('TIPO_IDENTIFICACION')),'tramite':tramite,'anio_tramite':tramite_year,
            'titular':_owner(r),'anio':row_year,'mes':month,'trimestre':row_quarter,'distrito':row_district,'archivo_origen':source_file}

def safe_extract_zip(path:Path, target:Path):
    with zipfile.ZipFile(path) as z:
        for info in z.infolist():
            if info.is_dir():continue
            root=target.resolve()
            dest=(target/info.filename).resolve()
            try:
                dest.relative_to(root)
            except ValueError:
                raise RuntimeError('ZIP contiene ruta insegura')
            dest.parent.mkdir(parents=True,exist_ok=True)
            with z.open(info) as src,dest.open('wb') as dst:shutil.copyfileobj(src,dst,length=1024*1024)

def _safe_archive_destination(target:Path, name:str) -> Path:
    root=target.resolve(); dest=(target/name).resolve()
    try:dest.relative_to(root)
    except ValueError:raise RuntimeError('Archivo comprimido contiene ruta insegura')
    return dest

def _extract_with_libarchive(path:Path,target:Path) -> bool:
    """Fallback nativo para plataformas donde libarchive está disponible."""
    libname=ctypes.util.find_library('archive')
    if not libname:return False
    try:lib=ctypes.CDLL(libname)
    except OSError:return False
    c_void_p=ctypes.c_void_p
    lib.archive_read_new.restype=c_void_p
    lib.archive_read_support_filter_all.argtypes=[c_void_p]
    lib.archive_read_support_format_all.argtypes=[c_void_p]
    lib.archive_read_open_filename.argtypes=[c_void_p,ctypes.c_char_p,ctypes.c_size_t]
    lib.archive_read_open_filename.restype=ctypes.c_int
    lib.archive_read_next_header.argtypes=[c_void_p,ctypes.POINTER(c_void_p)]
    lib.archive_read_next_header.restype=ctypes.c_int
    lib.archive_entry_pathname.argtypes=[c_void_p]; lib.archive_entry_pathname.restype=ctypes.c_char_p
    lib.archive_entry_filetype.argtypes=[c_void_p]; lib.archive_entry_filetype.restype=ctypes.c_uint
    lib.archive_read_data_block.argtypes=[c_void_p,ctypes.POINTER(c_void_p),ctypes.POINTER(ctypes.c_size_t),ctypes.POINTER(ctypes.c_longlong)]
    lib.archive_read_data_block.restype=ctypes.c_int
    lib.archive_read_close.argtypes=[c_void_p]; lib.archive_read_free.argtypes=[c_void_p]
    a=lib.archive_read_new()
    if not a:return False
    try:
        lib.archive_read_support_filter_all(a);lib.archive_read_support_format_all(a)
        if lib.archive_read_open_filename(a,os.fsencode(path),10240)!=0:return False
        entry=c_void_p()
        while True:
            rc=lib.archive_read_next_header(a,ctypes.byref(entry))
            if rc==1:break  # ARCHIVE_EOF
            if rc<0:return False
            raw=lib.archive_entry_pathname(entry)
            if not raw:continue
            name=os.fsdecode(raw);dest=_safe_archive_destination(target,name)
            ftype=lib.archive_entry_filetype(entry)
            if ftype==stat.S_IFDIR or name.endswith('/'):
                dest.mkdir(parents=True,exist_ok=True);continue
            if ftype not in (0,stat.S_IFREG):
                continue
            dest.parent.mkdir(parents=True,exist_ok=True)
            with dest.open('wb') as out:
                while True:
                    buff=c_void_p();size=ctypes.c_size_t();offset=ctypes.c_longlong()
                    drc=lib.archive_read_data_block(a,ctypes.byref(buff),ctypes.byref(size),ctypes.byref(offset))
                    if drc==1:break
                    if drc<0:return False
                    if size.value:
                        out.seek(offset.value);out.write(ctypes.string_at(buff,size.value))
        return True
    finally:
        try:lib.archive_read_close(a)
        finally:lib.archive_read_free(a)

def _archive_tool_candidates():
    root=Path(__file__).resolve().parents[2]
    bundled=[root/'tools'/'7zip'/'7z.exe',root/'tools'/'7zip'/'7za.exe',root/'tools'/'unrar'/'unrar.exe']
    for p in bundled:
        if p.is_file():yield str(p)
    for name in ('7z','7za','unrar','bsdtar','tar'):
        exe=shutil.which(name)
        if exe:yield exe

def extract_rar(path:Path,target:Path):
    vendor=Path(__file__).resolve().parents[2]/'vendor'
    if vendor.exists() and str(vendor) not in sys.path:sys.path.insert(0,str(vendor))
    first=None
    try:
        import rarfile
        with rarfile.RarFile(path) as rf:rf.extractall(target)
        return
    except Exception as exc:first=exc
    for exe in _archive_tool_candidates():
        name=Path(exe).name.lower()
        if name.startswith('7z'):
            args=[exe,'x','-y',f'-o{target}',str(path)]
        elif name.startswith('unrar'):
            args=[exe,'x','-o+',str(path),str(target)]
        else:
            args=[exe,'-xf',str(path),'-C',str(target)]
        try:cp=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=600)
        except Exception:continue
        if cp.returncode==0:return
    if _extract_with_libarchive(path,target):return
    raise RuntimeError('RAR reconocido, pero no hay extractor RAR disponible. El paquete Windows oficial incluye 7-Zip; SENDA también intenta tar/libarchive.') from first

def sha256_file(path:Path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

class ImportEngine:
    def __init__(self, repo):self.repo=repo
    def _expand(self, paths:list[Path], stack:ExitStack) -> list[Path]:
        out=[]
        for p in paths:
            fmt=detect_format(p)
            if fmt in ('zip','rar'):
                td=Path(stack.enter_context(tempfile.TemporaryDirectory(prefix='senda_v0_arc_')))
                safe_extract_zip(p,td) if fmt=='zip' else extract_rar(p,td)
                out.extend(self._expand([x for x in td.rglob('*') if x.is_file()],stack))
            else:out.append(p)
        return out
    def import_paths(self, paths:Iterable[str|Path], *, year:int, quarter:str, district:str):
        if quarter not in ('T1','T2','T3','T4'):raise ValueError('Trimestre inválido')
        district=normalize_district(district); original=[Path(p) for p in paths]
        if not original:return {'inserted':0,'skipped':0,'duplicates':0,'errors':0,'ignored':0,'files':[],'catalogs':0,'metadata':0}
        # Order and filename independent hash: the same payload selected again is a duplicate import.
        original_hashes=sorted(sha256_file(p) for p in original)
        combined=hashlib.sha256(''.join(original_hashes).encode()).hexdigest()
        if self.repo.has_completed_import_hash(combined):
            return {'inserted':0,'skipped':0,'duplicates':0,'errors':0,'files':[],
                    'catalogs':0,'metadata':0,'ignored':0,'duplicate_import':True,'duplicate_files':[p.name for p in original]}
        import_id=self.repo.create_import(year=year,quarter=quarter,district=district,source_name=', '.join(p.name for p in original),source_hash=combined)
        skipped=0; duplicates=0; errors=0; ignored=0; inserted=0; catalogs_count=0; metadata_count=0; accepted=[]
        try:
            with ExitStack() as stack:
                expanded=self._expand(original,stack)
                for p in expanded:
                    if is_catalog_name(p.name):
                        for e in parse_catalog(p):self.repo.upsert_catalog(e['kind'],e['code'],e['class_code'],e['description'],p.name);catalogs_count+=1
                ctx=catalog_context(self.repo)
                for p in expanded:
                    if is_catalog_name(p.name):accepted.append(p.name);continue
                    fmt=detect_format(p)
                    if fmt not in ('delimited','xls','xlsx','json'):ignored+=1;continue
                    try:
                        it=iter_rows(p); first=next(it,None)
                        if first is None:accepted.append(p.name);continue
                        source=detect_source(p,first.keys()); file_district=district_from_path(p,district)
                        if is_registry_reference(source,first.keys()):
                            for raw in itertools.chain((first,),it):
                                metadata_count += self.repo.upsert_registry_reference({keynorm(k):v for k,v in raw.items()},source,file_district,p.name)
                            accepted.append(p.name)
                            continue
                        if source=='CEDULAS JURIDICAS':
                            for raw in itertools.chain((first,),it):
                                metadata_count += self.repo.upsert_legal_reference({keynorm(k):v for k,v in raw.items()},p.name)
                            accepted.append(p.name)
                            continue
                        def normalized():
                            nonlocal skipped
                            for raw in itertools.chain((first,),it):
                                x=normalize_row(raw,source=source,year=year,quarter=quarter,district=file_district,source_file=p.name,ctx=ctx)
                                if x is None:skipped+=1
                                else:yield x
                        inserted += self.repo.insert_movements(normalized(),import_id)
                        duplicates += self.repo.last_insert_duplicates
                        accepted.append(p.name)
                    except Exception:
                        errors+=1
                        raise
            self.repo.finish_import(import_id,inserted,skipped,errors,'COMPLETED')
            return {'import_id':import_id,'inserted':inserted,'skipped':skipped,'duplicates':duplicates,'errors':errors,
                    'files':accepted,'catalogs':catalogs_count,'metadata':metadata_count,'ignored':ignored,'duplicate_import':False}
        except Exception:
            self.repo.finish_import(import_id,inserted,skipped,errors+1,'FAILED')
            raise
