from __future__ import annotations
import hashlib, json, sqlite3
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path

from .domain import parse_date, quarter_for_month, normalize_district, alarm_level
from .importers.engine import movement_category

CATEGORIES=('FINCAS','HIPOTECAS','GRAVÁMENES','SEGREGACIONES','ANOTACIONES','HISTÓRICOS','CERRADAS','OTROS')
PAGE_SIZES=(25,50,100)
CASE_STATUSES=('INFORMACION','EN CONTROL','GESTION')

SCHEMA='''
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
CREATE TABLE IF NOT EXISTS movements(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 folio TEXT, finca TEXT DEFAULT '', derecho_numero TEXT DEFAULT '', derecho TEXT, plano TEXT, fecha TEXT, codigo TEXT, operacion TEXT, enlace TEXT DEFAULT '',
 tipo TEXT, fuente TEXT, categoria TEXT, cedula TEXT, tipo_ident TEXT DEFAULT '', titular TEXT,
 tramite TEXT DEFAULT '', anio_tramite INTEGER DEFAULT 0,
 anio INTEGER, mes INTEGER, trimestre TEXT, distrito TEXT,
 archivo_origen TEXT, import_id INTEGER, raw_json TEXT,
 UNIQUE(folio, derecho, plano, fecha, codigo, fuente, distrito, archivo_origen)
);
CREATE INDEX IF NOT EXISTS ix_mov_period ON movements(anio,trimestre,mes,distrito);
CREATE INDEX IF NOT EXISTS ix_mov_folio ON movements(folio);
CREATE INDEX IF NOT EXISTS ix_mov_plano ON movements(plano);
CREATE INDEX IF NOT EXISTS ix_mov_fecha ON movements(fecha);
CREATE TABLE IF NOT EXISTS imports(
 id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
 anio INTEGER, trimestre TEXT, distrito TEXT, source_name TEXT, source_hash TEXT,
 records INTEGER DEFAULT 0, skipped INTEGER DEFAULT 0, errors INTEGER DEFAULT 0, status TEXT DEFAULT 'PROCESSING'
);
CREATE INDEX IF NOT EXISTS ix_import_hash_status ON imports(source_hash,status);
CREATE TABLE IF NOT EXISTS movement_signatures(
 signature TEXT PRIMARY KEY, movement_id INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS catalogs(
 kind TEXT NOT NULL, code TEXT NOT NULL, class_code TEXT NOT NULL DEFAULT '', description TEXT,
 source_file TEXT, PRIMARY KEY(kind,code,class_code)
);
CREATE TABLE IF NOT EXISTS case_files(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 folio TEXT, plano TEXT, distrito TEXT,
 status TEXT DEFAULT 'INFORMACION', responsable TEXT DEFAULT '', prioridad TEXT DEFAULT 'NORMAL',
 note TEXT, control_started_at TEXT, finalized_at TEXT, management_started_at TEXT, management_state TEXT DEFAULT 'PENDIENTE',
 created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_case_status ON case_files(status);
CREATE INDEX IF NOT EXISTS ix_case_folio ON case_files(folio);
CREATE TABLE IF NOT EXISTS case_audit(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 case_id INTEGER NOT NULL, action TEXT NOT NULL,
 previous_status TEXT, new_status TEXT, note TEXT, payload_json TEXT,
 created_at TEXT DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY(case_id) REFERENCES case_files(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_case_audit_case ON case_audit(case_id,id);
CREATE TABLE IF NOT EXISTS case_attachments(
 id INTEGER PRIMARY KEY AUTOINCREMENT, case_id INTEGER NOT NULL, filename TEXT, stored_path TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY(case_id) REFERENCES case_files(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS case_movement_selection(
 case_id INTEGER NOT NULL, movement_id INTEGER NOT NULL, selected_at TEXT DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(case_id,movement_id),
 FOREIGN KEY(case_id) REFERENCES case_files(id) ON DELETE CASCADE,
 FOREIGN KEY(movement_id) REFERENCES movements(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_case_movement_selection_case ON case_movement_selection(case_id);
CREATE TABLE IF NOT EXISTS legal_entities(
 cedula_juridica TEXT PRIMARY KEY, razon_social TEXT, domicilio TEXT, fecha_inicio TEXT, fecha_vence TEXT, source_file TEXT, updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS legal_representatives(
 cedula_juridica TEXT NOT NULL, numero_identificacion TEXT NOT NULL DEFAULT '', nombre TEXT, apellido_1 TEXT, apellido_2 TEXT, cargo TEXT, representacion TEXT, source_file TEXT,
 PRIMARY KEY(cedula_juridica,numero_identificacion,cargo,representacion),
 FOREIGN KEY(cedula_juridica) REFERENCES legal_entities(cedula_juridica) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_legal_entity_name ON legal_entities(razon_social);
CREATE INDEX IF NOT EXISTS ix_legal_rep_id ON legal_representatives(numero_identificacion);
CREATE TABLE IF NOT EXISTS registry_references(
 id INTEGER PRIMARY KEY AUTOINCREMENT, reference_hash TEXT UNIQUE, kind TEXT, district TEXT, finca TEXT DEFAULT '', plan_key TEXT DEFAULT '', source_file TEXT, raw_json TEXT, updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_registry_ref_finca ON registry_references(finca);
CREATE INDEX IF NOT EXISTS ix_registry_ref_plan ON registry_references(plan_key);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
'''


def _clean(v): return str(v or '').strip()

def _sanitize_movement_payload(row):
    blocked={'enlace','link','url','hipervinculo','vinculo','direccion_web'}
    return {k:v for k,v in dict(row).items() if str(k).strip().lower() not in blocked}

def _public_movement(row):
    out=dict(row)
    out.pop('enlace',None)
    return out


def _movement_signature(values):
    """Firma lógica independiente del nombre de archivo/importación.

    Evita que el mismo movimiento vuelva a insertarse si llega en un archivo
    renombrado, otro ZIP/RAR o una nueva carga del mismo corte.
    """
    payload='|'.join(_clean(v).upper() for v in values)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()

def _canonical_status(v):
    s=_clean(v).upper().replace('_',' ')
    return {
        'PENDIENTE':'INFORMACION','INFORMACIÓN':'INFORMACION','INFORMACION':'INFORMACION','REGRESADO':'INFORMACION',
        'EN REVISION':'EN CONTROL','EN REVISIÓN':'EN CONTROL','EN CONTROL':'EN CONTROL',
        'FINALIZADO':'GESTION','GESTIÓN':'GESTION','GESTION':'GESTION'
    }.get(s,'INFORMACION')


class Repository:
    def __init__(self,path:str|Path):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True); self._init()

    def connect(self):
        c=sqlite3.connect(self.path); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON'); return c

    @contextmanager
    def connection(self):
        c=self.connect()
        try:
            with c: yield c
        finally:c.close()

    def _init(self):
        with self.connection() as c:
            # First create every table possible on a new database.
            c.executescript(SCHEMA)
            self._migrate(c)

    def _columns(self,c,table): return {r['name'] for r in c.execute(f'PRAGMA table_info({table})')}

    def _migrate(self,c):
        # Additive migration only. Existing loaded data is never dropped/recreated.
        mov=self._columns(c,'movements')
        if 'categoria' not in mov:c.execute("ALTER TABLE movements ADD COLUMN categoria TEXT DEFAULT ''")
        if 'enlace' not in mov:c.execute("ALTER TABLE movements ADD COLUMN enlace TEXT DEFAULT ''")
        if 'finca' not in mov:c.execute("ALTER TABLE movements ADD COLUMN finca TEXT DEFAULT ''")
        if 'derecho_numero' not in mov:c.execute("ALTER TABLE movements ADD COLUMN derecho_numero TEXT DEFAULT ''")
        if 'tipo_ident' not in mov:c.execute("ALTER TABLE movements ADD COLUMN tipo_ident TEXT DEFAULT ''")
        if 'tramite' not in mov:c.execute("ALTER TABLE movements ADD COLUMN tramite TEXT DEFAULT ''")
        if 'anio_tramite' not in mov:c.execute("ALTER TABLE movements ADD COLUMN anio_tramite INTEGER DEFAULT 0")
        # Recupera FINCA/DERECHO de filas anteriores sin borrar ni duplicar datos.
        legacy=c.execute("SELECT id,folio,finca,derecho_numero FROM movements WHERE COALESCE(finca,'')='' OR COALESCE(derecho_numero,'')=''").fetchall()
        for r in legacy:
            fol=_clean(r['folio']); finca=_clean(r['finca']); dnum=_clean(r['derecho_numero'])
            m=__import__('re').match(r'^\s*(\d+)\s*-\s*(\d+)(?:\s*-\s*(\d{1,3}))?\s*$',fol)
            if m:
                if not finca:finca=f'{int(m.group(1))}-{int(m.group(2))}'
                if not dnum and m.group(3):dnum=f'{int(m.group(3)):03d}'
            if finca or dnum:c.execute('UPDATE movements SET finca=?,derecho_numero=? WHERE id=?',(finca,dnum,r['id']))
        c.execute("CREATE INDEX IF NOT EXISTS ix_mov_finca ON movements(finca)")
        cases=self._columns(c,'case_files')
        additions={
            'plano':"TEXT DEFAULT ''",'responsable':"TEXT DEFAULT ''",'prioridad':"TEXT DEFAULT 'NORMAL'",
            'control_started_at':'TEXT','finalized_at':'TEXT','management_started_at':'TEXT',
            'management_state':"TEXT DEFAULT 'PENDIENTE'"
        }
        for col,typ in additions.items():
            if col not in cases:c.execute(f'ALTER TABLE case_files ADD COLUMN {col} {typ}')
        c.executescript('''
        CREATE INDEX IF NOT EXISTS ix_mov_plano ON movements(plano);
                CREATE INDEX IF NOT EXISTS ix_case_status ON case_files(status);
        CREATE INDEX IF NOT EXISTS ix_case_folio ON case_files(folio);
                CREATE TABLE IF NOT EXISTS case_audit(
         id INTEGER PRIMARY KEY AUTOINCREMENT,case_id INTEGER NOT NULL,action TEXT NOT NULL,
         previous_status TEXT,new_status TEXT,note TEXT,payload_json TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP,
         FOREIGN KEY(case_id) REFERENCES case_files(id) ON DELETE CASCADE);
        CREATE INDEX IF NOT EXISTS ix_case_audit_case ON case_audit(case_id,id);
        ''')
        c.executescript('''
        CREATE INDEX IF NOT EXISTS ix_import_hash_status ON imports(source_hash,status);
        CREATE TABLE IF NOT EXISTS movement_signatures(
         signature TEXT PRIMARY KEY,movement_id INTEGER,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        ''')
        c.executescript('''
        CREATE TABLE IF NOT EXISTS case_movement_selection(
         case_id INTEGER NOT NULL,movement_id INTEGER NOT NULL,selected_at TEXT DEFAULT CURRENT_TIMESTAMP,
         PRIMARY KEY(case_id,movement_id),
         FOREIGN KEY(case_id) REFERENCES case_files(id) ON DELETE CASCADE,
         FOREIGN KEY(movement_id) REFERENCES movements(id) ON DELETE CASCADE);
        CREATE INDEX IF NOT EXISTS ix_case_movement_selection_case ON case_movement_selection(case_id);
        CREATE TABLE IF NOT EXISTS legal_entities(
         cedula_juridica TEXT PRIMARY KEY,razon_social TEXT,domicilio TEXT,fecha_inicio TEXT,fecha_vence TEXT,source_file TEXT,updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS legal_representatives(
         cedula_juridica TEXT NOT NULL,numero_identificacion TEXT NOT NULL DEFAULT '',nombre TEXT,apellido_1 TEXT,apellido_2 TEXT,cargo TEXT,representacion TEXT,source_file TEXT,
         PRIMARY KEY(cedula_juridica,numero_identificacion,cargo,representacion),
         FOREIGN KEY(cedula_juridica) REFERENCES legal_entities(cedula_juridica) ON DELETE CASCADE);
        CREATE INDEX IF NOT EXISTS ix_legal_entity_name ON legal_entities(razon_social);
        CREATE INDEX IF NOT EXISTS ix_legal_rep_id ON legal_representatives(numero_identificacion);
        CREATE TABLE IF NOT EXISTS registry_references(
         id INTEGER PRIMARY KEY AUTOINCREMENT,reference_hash TEXT UNIQUE,kind TEXT,district TEXT,finca TEXT DEFAULT '',plan_key TEXT DEFAULT '',source_file TEXT,raw_json TEXT,updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE INDEX IF NOT EXISTS ix_registry_ref_finca ON registry_references(finca);
        CREATE INDEX IF NOT EXISTS ix_registry_ref_plan ON registry_references(plan_key);
        ''')
        c.execute("UPDATE case_files SET management_state='PENDIENTE' WHERE COALESCE(management_state,'')=''")
        # 0.4.4: rebuild the signature index using normalized business fields,
        # including PRESENTACION/TRAMITE when available.
        # 0.4.2 stored exact source-row fingerprints, so auxiliary column changes
        # could make the same registry movement look different across exports.
        sig_version=c.execute("SELECT value FROM settings WHERE key='movement_signature_version'").fetchone()
        if not sig_version or sig_version['value']!='4':
            c.execute('DELETE FROM movement_signatures')
            rows=c.execute('''SELECT id,folio,finca,derecho_numero,derecho,plano,fecha,codigo,operacion,fuente,cedula,titular,tramite
                              FROM movements ORDER BY id''').fetchall()
            for r in rows:
                signature=_movement_signature((r['finca'] or r['folio'],r['derecho_numero'],r['derecho'],r['plano'],r['fecha'],r['codigo'],r['operacion'],r['fuente'],r['cedula'],r['titular'],r['tramite']))
                c.execute('INSERT OR IGNORE INTO movement_signatures(signature,movement_id) VALUES(?,?)',(signature,r['id']))
            c.execute("INSERT INTO settings(key,value) VALUES('movement_signature_version','4') ON CONFLICT(key) DO UPDATE SET value=excluded.value")
        # No destructive movement cleanup: legacy rows remain intact. The rebuilt
        # signature index only prevents future re-insertion of the same logical movement.
        # Preserve old cases while translating their workflow state.
        for old,new in (('PENDIENTE','INFORMACION'),('EN REVISION','EN CONTROL'),('FINALIZADO','GESTION'),('REGRESADO','INFORMACION')):
            c.execute('UPDATE case_files SET status=? WHERE UPPER(status)=?',(new,old))
        # Classify legacy rows in one SQL pass. New inserts use the Python classifier below.
        c.execute('''UPDATE movements SET categoria=CASE
            WHEN UPPER(COALESCE(operacion,'')||' '||COALESCE(fuente,'')) LIKE '%HIPOTECA%' THEN 'HIPOTECAS'
            WHEN UPPER(COALESCE(operacion,'')||' '||COALESCE(fuente,'')) LIKE '%SEGREG%' THEN 'SEGREGACIONES'
            WHEN UPPER(COALESCE(operacion,'')||' '||COALESCE(fuente,'')) LIKE '%ANOT%' THEN 'ANOTACIONES'
            WHEN UPPER(COALESCE(operacion,'')||' '||COALESCE(fuente,'')) LIKE '%GRAVAM%'
              OR UPPER(COALESCE(operacion,'')) LIKE '%SERVIDUM%'
              OR UPPER(COALESCE(operacion,'')) LIKE '%EMBARGO%'
              OR UPPER(COALESCE(operacion,'')) LIKE '%LIMITACION%'
              OR UPPER(COALESCE(operacion,'')) LIKE '%DEMANDA%' THEN 'GRAVÁMENES'
            WHEN UPPER(COALESCE(operacion,'')||' '||COALESCE(fuente,'')) LIKE '%CIERRE%'
              OR UPPER(COALESCE(operacion,'')||' '||COALESCE(fuente,'')) LIKE '%CERRAD%' THEN 'CERRADAS'
            WHEN UPPER(COALESCE(fuente,'')) LIKE 'FINCAS%' THEN 'FINCAS'
            WHEN UPPER(COALESCE(fuente,'')) LIKE '%HISTOR%' THEN 'HISTÓRICOS'
            ELSE 'OTROS' END
            WHERE COALESCE(categoria,'')='' ''')

    # ---------- imports / movements ----------
    def has_completed_import_hash(self,source_hash:str) -> bool:
        if not source_hash:return False
        with self.connection() as c:
            return c.execute("SELECT 1 FROM imports WHERE source_hash=? AND status='COMPLETED' LIMIT 1",(source_hash,)).fetchone() is not None

    def create_import(self,*,year=None,quarter=None,district='',source_name='',source_hash='')->int:
        with self.connection() as c:
            cur=c.execute('INSERT INTO imports(anio,trimestre,distrito,source_name,source_hash) VALUES(?,?,?,?,?)',(year,quarter,normalize_district(district),source_name,source_hash));return cur.lastrowid

    def finish_import(self,import_id:int,records:int,skipped:int=0,errors:int=0,status='COMPLETED'):
        with self.connection() as c:c.execute('UPDATE imports SET records=?,skipped=?,errors=?,status=? WHERE id=?',(records,skipped,errors,status,import_id))

    def insert_movements(self,rows,import_id:int,batch_size:int=1000):
        sql='''INSERT OR IGNORE INTO movements(folio,finca,derecho_numero,derecho,plano,fecha,codigo,operacion,enlace,tipo,fuente,categoria,cedula,tipo_ident,titular,tramite,anio_tramite,anio,mes,trimestre,distrito,archivo_origen,import_id,raw_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'''
        inserted=0;duplicates=0
        with self.connection() as c:
            for r in rows:
                d=parse_date(r.get('fecha'));year=int(r.get('anio') or (d.year if d else date.today().year));month=int(r.get('mes') or (d.month if d else 0) or 0);q=str(r.get('trimestre') or (quarter_for_month(month) if month else ''))
                op=_clean(r.get('operacion'));src=_clean(r.get('fuente') or r.get('tipo'));cat=_clean(r.get('categoria')) or movement_category(op,src)
                folio=_clean(r.get('folio'));finca=_clean(r.get('finca'));derecho_numero=_clean(r.get('derecho_numero'));derecho=_clean(r.get('derecho'));plano=_clean(r.get('plano'));fecha=d.isoformat() if d else '';codigo=_clean(r.get('codigo'));cedula=_clean(r.get('cedula'));tipo_ident=_clean(r.get('tipo_ident'));titular=_clean(r.get('titular'));tramite=_clean(r.get('tramite'));anio_tramite=int(r.get('anio_tramite') or 0)
                if not finca:
                    m=__import__('re').match(r'^\s*(\d+)\s*-\s*(\d+)(?:\s*-\s*(\d{1,3}))?\s*$',folio)
                    if m:
                        finca=f'{int(m.group(1))}-{int(m.group(2))}'
                        if not derecho_numero and m.group(3):derecho_numero=f'{int(m.group(3)):03d}'
                signature=_movement_signature((finca or folio,derecho_numero,derecho,plano,fecha,codigo,op,src,cedula,titular,tramite))
                before=c.total_changes
                c.execute('INSERT OR IGNORE INTO movement_signatures(signature) VALUES(?)',(signature,))
                if c.total_changes==before:
                    duplicates+=1
                    continue
                vals=(folio,finca,derecho_numero,derecho,plano,fecha,codigo,op,'',_clean(r.get('tipo')),src,cat,cedula,tipo_ident,titular,tramite,anio_tramite,year,month,q,normalize_district(r.get('distrito')),_clean(r.get('archivo_origen')),import_id,json.dumps(_sanitize_movement_payload(r),ensure_ascii=False,default=str))
                cur=c.execute(sql,vals)
                if cur.rowcount:
                    inserted+=1
                    c.execute('UPDATE movement_signatures SET movement_id=? WHERE signature=?',(cur.lastrowid,signature))
                else:
                    # Defensive rollback of the signature marker if the legacy UNIQUE
                    # constraint rejected the movement for an unexpected reason.
                    c.execute('DELETE FROM movement_signatures WHERE signature=? AND movement_id IS NULL',(signature,))
                    duplicates+=1
        self._last_insert_duplicates=duplicates
        return inserted

    @property
    def last_insert_duplicates(self):
        return int(getattr(self,'_last_insert_duplicates',0))

    def _where(self,filters,alias=''):
        filters=filters or {};p=(alias+'.') if alias else '';clauses=[];args=[]
        mapping={'year':('anio',int),'quarter':('trimestre',str),'month':('mes',int),'district':('distrito',normalize_district),'source':('fuente',str),'movement_type':('categoria',str),'tramite_year':('anio_tramite',int)}
        for key,(col,conv) in mapping.items():
            val=filters.get(key)
            if val not in (None,'','ALL','TODOS','Todas','TODAS'):
                clauses.append(f'{p}{col}=?');args.append(conv(val))
        cedula=_clean(filters.get('cedula'))
        if cedula:
            compact=''.join(ch for ch in cedula if ch.isalnum())
            clauses.append(f"REPLACE(REPLACE({p}cedula,'-',''),' ','') LIKE ?");args.append(f'%{compact}%')
        juridica=_clean(filters.get('cedula_juridica'))
        if juridica:
            compact=''.join(ch for ch in juridica if ch.isalnum())
            clauses.append(f"({p}tipo_ident='2' AND REPLACE(REPLACE({p}cedula,'-',''),' ','') LIKE ?)");args.append(f'%{compact}%')
        search=_clean(filters.get('search'))
        if search:
            q=f'%{search}%';clauses.append(f'({p}folio LIKE ? OR {p}finca LIKE ? OR {p}plano LIKE ? OR {p}titular LIKE ? OR {p}cedula LIKE ? OR {p}tramite LIKE ? OR {p}operacion LIKE ?)');args.extend([q]*7)
        return (' WHERE '+' AND '.join(clauses)) if clauses else '',args

    def _alarm_filter(self,filters,last_col='latest_date'):
        alarm=_clean((filters or {}).get('alarm')).lower();cut90=(date.today()-timedelta(days=90)).isoformat();cut60=(date.today()-timedelta(days=60)).isoformat()
        if alarm=='red':return f'{last_col} IS NOT NULL AND {last_col}<=?',[cut90]
        if alarm=='yellow':return f'{last_col}>? AND {last_col}<?',[cut90,cut60]
        if alarm=='green':return f'({last_col} IS NULL OR {last_col}>=?)',[cut60]
        return '1=1',[]

    def _case_map(self):
        with self.connection() as c:rows=[dict(r) for r in c.execute('SELECT * FROM case_files ORDER BY id DESC')]
        out={}
        for r in rows:
            if r['folio']:out.setdefault(('folio',r['folio']),r)
            if r.get('plano'):out.setdefault(('plano',r['plano']),r)
        return out

    def _attach_workflow(self,rows):
        cmap=self._case_map()
        for r in rows:
            case=cmap.get(('folio',r.get('finca') or '')) or cmap.get(('folio',r.get('folio') or '')) or cmap.get(('plano',r.get('plano') or ''))
            r['case_id']=case['id'] if case else None;r['estado_expediente']=case['status'] if case else 'INFORMACION';r['en_control']=bool(case and case['status']=='EN CONTROL');r['en_gestion']=bool(case and case['status']=='GESTION')
        return rows

    def list_movements(self,filters=None,limit=1000,offset=0,order='desc'):
        filters=filters or {};where,args=self._where(filters);condition,extra=self._alarm_filter(filters)
        direction='ASC' if str(order).lower()=='asc' else 'DESC'
        sql=f'''WITH filtered AS (
            SELECT movements.*,MAX(NULLIF(fecha,'')) OVER (PARTITION BY COALESCE(NULLIF(finca,''),NULLIF(folio,''),'@'||NULLIF(plano,''))) latest_date
            FROM movements{where}
        ) SELECT * FROM filtered WHERE {condition} ORDER BY CASE WHEN fecha='' THEN 1 ELSE 0 END,fecha {direction},id {direction} LIMIT ? OFFSET ?'''
        with self.connection() as c:rows=[_public_movement(r) for r in c.execute(sql,(*args,*extra,int(limit),int(offset)))]
        for r in rows:r['alarma']=alarm_level(parse_date(r.pop('latest_date',None)))
        return self._attach_workflow(rows)

    # ---------- information / dashboard ----------
    def list_information(self,filters=None,limit=25,offset=0):
        if int(limit) not in PAGE_SIZES:raise ValueError('Tamaño de página permitido: 25, 50 o 100')
        filters=filters or {};where,args=self._where(filters,'m');condition,extra=self._alarm_filter(filters,'last_date')
        no_mov_filter=not any(filters.get(k) not in (None,'','TODOS','TODAS','ALL') for k in ('year','quarter','month','movement_type','alarm','source'))
        manual_clauses=["cf.status<>'GESTION'","NOT EXISTS(SELECT 1 FROM movements mx WHERE (cf.folio<>'' AND (mx.finca=cf.folio OR mx.folio=cf.folio)) OR (cf.folio='' AND cf.plano<>'' AND mx.plano=cf.plano))"]
        manual_args=[]
        if not no_mov_filter:manual_clauses.append('0=1')
        q=_clean(filters.get('search'))
        if q:manual_clauses.append('(cf.folio LIKE ? OR cf.plano LIKE ? OR cf.note LIKE ? OR cf.responsable LIKE ?)');manual_args.extend([f'%{q}%']*4)
        dist=filters.get('district')
        if dist not in (None,'','TODOS','TODAS','ALL'):manual_clauses.append('cf.distrito=?');manual_args.append(normalize_district(dist))
        manual_where=' AND '.join(manual_clauses)
        cte=f'''WITH selected AS (
          SELECT m.* FROM movements m{where}
        ), grouped AS (
          SELECT COALESCE(NULLIF(finca,''),NULLIF(folio,''),'@PLANO:'||plano) entity_key,
                 COALESCE(MAX(NULLIF(finca,'')),MAX(folio)) folio,MAX(NULLIF(finca,'')) finca,MAX(plano) plano,MAX(distrito) distrito,
                 MIN(NULLIF(fecha,'')) first_date,MAX(NULLIF(fecha,'')) last_date,
                 COUNT(*) movimientos,COUNT(DISTINCT (COALESCE(NULLIF(derecho_numero,''),'')||'|'||COALESCE(NULLIF(derecho,''),''))) derechos,
                 SUM(categoria='FINCAS') c_fincas,SUM(categoria='HIPOTECAS') c_hipotecas,SUM(categoria='GRAVÁMENES') c_gravamenes,
                 SUM(categoria='SEGREGACIONES') c_segregaciones,SUM(categoria='ANOTACIONES') c_anotaciones,
                 SUM(categoria='HISTÓRICOS') c_historicos,SUM(categoria='CERRADAS') c_cerradas,SUM(categoria='OTROS') c_otros
          FROM selected
          WHERE COALESCE(NULLIF(folio,''),NULLIF(plano,'')) IS NOT NULL
          GROUP BY entity_key
        ), visible_mov AS (
          SELECT * FROM grouped g WHERE {condition}
          AND NOT EXISTS(SELECT 1 FROM case_files cf WHERE cf.status='GESTION' AND ((g.folio<>'' AND cf.folio=g.folio) OR (g.finca<>'' AND cf.folio=g.finca) OR (g.folio='' AND g.plano<>'' AND cf.plano=g.plano)))
        ), manual AS (
          SELECT 'MANUAL:'||cf.id entity_key,cf.folio folio,'' finca,cf.plano plano,cf.distrito distrito,
                 NULL first_date,NULL last_date,0 movimientos,0 derechos,
                 0 c_fincas,0 c_hipotecas,0 c_gravamenes,0 c_segregaciones,0 c_anotaciones,0 c_historicos,0 c_cerradas,0 c_otros
          FROM case_files cf WHERE {manual_where}
        ), entities AS (
          SELECT * FROM visible_mov UNION ALL SELECT * FROM manual
        )'''
        params=(*args,*extra,*manual_args)
        with self.connection() as c:
            total=c.execute(cte+' SELECT COUNT(*) n FROM entities',params).fetchone()['n']
            rows=[dict(r) for r in c.execute(cte+''' SELECT * FROM entities
                ORDER BY CASE WHEN first_date IS NULL THEN 1 ELSE 0 END,first_date ASC,entity_key ASC LIMIT ? OFFSET ?''',(*params,int(limit),int(offset)))]
        cmap=self._case_map();out=[]
        for r in rows:
            case=cmap.get(('folio',r.get('finca') or '')) or cmap.get(('folio',r['folio'])) or cmap.get(('plano',r['plano']))
            cats={'FINCAS':r.pop('c_fincas'),'HIPOTECAS':r.pop('c_hipotecas'),'GRAVÁMENES':r.pop('c_gravamenes'),'SEGREGACIONES':r.pop('c_segregaciones'),'ANOTACIONES':r.pop('c_anotaciones'),'HISTÓRICOS':r.pop('c_historicos'),'CERRADAS':r.pop('c_cerradas'),'OTROS':r.pop('c_otros')}
            r['categorias']=cats;r['case_id']=case['id'] if case else None;r['status']=case['status'] if case else 'INFORMACION';r['responsable']=case.get('responsable','') if case else '';r['prioridad']=case.get('prioridad','NORMAL') if case else 'NORMAL';r['alarma']=alarm_level(parse_date(r['last_date']))
            out.append(r)
        return {'rows':out,'total':total,'limit':int(limit),'offset':int(offset)}

    def entity_movements(self,folio='',plano='',category='TODOS',limit=25,offset=0):
        if int(limit) not in PAGE_SIZES:raise ValueError('Tamaño de página permitido: 25, 50 o 100')
        folio=_clean(folio);plano=_clean(plano)
        if not folio and not plano:raise ValueError('Folio o plano requerido')
        clauses=[];args=[]
        if folio:clauses.append('(finca=? OR folio=?)');args.extend([folio,folio])
        else:clauses.append('plano=?');args.append(plano)
        if category not in (None,'','TODOS','TODAS','ALL'):clauses.append('categoria=?');args.append(category)
        where=' WHERE '+' AND '.join(clauses)
        with self.connection() as c:
            total=c.execute('SELECT COUNT(*) n FROM movements'+where,args).fetchone()['n']
            rows=[_public_movement(r) for r in c.execute('SELECT * FROM movements'+where+" ORDER BY CASE WHEN fecha='' THEN 1 ELSE 0 END,fecha ASC,id ASC LIMIT ? OFFSET ?",(*args,int(limit),int(offset)))]
            rights=[dict(r) for r in c.execute("SELECT COALESCE(NULLIF(derecho_numero,''),NULLIF(derecho,''),'GENERAL') derecho_numero,COALESCE(NULLIF(derecho,''),'GENERAL') derecho,COUNT(*) movimientos FROM movements"+where+" GROUP BY COALESCE(NULLIF(derecho_numero,''),NULLIF(derecho,''),'GENERAL'),COALESCE(NULLIF(derecho,''),'GENERAL') ORDER BY derecho_numero,derecho",args)]
        return {'rows':rows,'rights':rights,'references':self.list_registry_references(folio),'total':total,'limit':int(limit),'offset':int(offset)}

    def dashboard(self,filters=None):
        filters=filters or {};where,args=self._where(filters);condition,extra=self._alarm_filter(filters)
        cte=("WITH filtered AS ( SELECT movements.*,MAX(NULLIF(fecha,'')) OVER (PARTITION BY COALESCE(NULLIF(finca,''),NULLIF(folio,''),'@'||NULLIF(plano,''))) latest_date FROM movements"+where+
             "), selected AS ( SELECT * FROM filtered WHERE "+condition+") ")
        params=(*args,*extra);cut90=(date.today()-timedelta(days=90)).isoformat();cut60=(date.today()-timedelta(days=60)).isoformat()
        with self.connection() as c:
            summary=c.execute(cte+"SELECT COUNT(*) movimientos,COUNT(DISTINCT COALESCE(NULLIF(finca,''),NULLIF(folio,''),'@'||NULLIF(plano,''))) folios FROM selected",params).fetchone()
            by_source={r['fuente']:r['n'] for r in c.execute(cte+'SELECT fuente,COUNT(*) n FROM selected GROUP BY fuente ORDER BY n DESC',params)}
            by_district={r['distrito']:r['n'] for r in c.execute(cte+'SELECT distrito,COUNT(*) n FROM selected GROUP BY distrito ORDER BY n DESC',params)}
            by_category={r['categoria']:r['n'] for r in c.execute(cte+'SELECT categoria,COUNT(*) n FROM selected GROUP BY categoria ORDER BY n DESC',params)}
            by_month={int(r['mes']):r['n'] for r in c.execute(cte+'SELECT mes,COUNT(*) n FROM selected WHERE mes IS NOT NULL GROUP BY mes ORDER BY mes',params)}
            recent=[dict(r) for r in c.execute(cte+'''SELECT fecha,COALESCE(NULLIF(finca,''),folio) folio,finca,derecho_numero,plano,categoria,codigo,operacion,distrito
                FROM selected ORDER BY CASE WHEN fecha='' THEN 1 ELSE 0 END,fecha DESC,id DESC LIMIT 12''',params)]
            tramite=c.execute(cte+'''SELECT COUNT(*) n FROM selected s WHERE EXISTS(
                SELECT 1 FROM case_files cf WHERE cf.status IN ('EN CONTROL','GESTION') AND ((cf.folio<>'' AND (cf.folio=s.finca OR cf.folio=s.folio)) OR (cf.folio='' AND cf.plano<>'' AND cf.plano=s.plano)))''',params).fetchone()['n']
            pendientes=c.execute(cte+'''SELECT COUNT(DISTINCT COALESCE(NULLIF(s.finca,''),NULLIF(s.folio,''),'@'||NULLIF(s.plano,''))) n
                FROM selected s WHERE COALESCE(NULLIF(s.finca,''),NULLIF(s.folio,''),NULLIF(s.plano,'')) IS NOT NULL AND NOT EXISTS(
                SELECT 1 FROM case_files cf WHERE cf.status IN ('EN CONTROL','GESTION') AND ((cf.folio<>'' AND (cf.folio=s.finca OR cf.folio=s.folio)) OR (cf.folio='' AND cf.plano<>'' AND cf.plano=s.plano)))''',params).fetchone()['n']
            cases={r['status']:r['n'] for r in c.execute("SELECT status,COUNT(*) n FROM case_files GROUP BY status")}
            alarm_sql=cte+'''SELECT CASE WHEN latest_date IS NULL OR latest_date>=? THEN 'green' WHEN latest_date<=? THEN 'red' ELSE 'yellow' END level,COUNT(DISTINCT COALESCE(NULLIF(finca,''),NULLIF(folio,''),'@'||NULLIF(plano,''))) n FROM selected GROUP BY level'''
            alarms={'red':0,'yellow':0,'green':0}
            for r in c.execute(alarm_sql,(*params,cut60,cut90)):alarms[r['level']]=r['n']
        return {'movimientos':summary['movimientos'],'folios':summary['folios'],'movimientos_tramite':tramite,'tramites_pendientes':pendientes,'casos_control':cases.get('EN CONTROL',0),'casos_gestion':cases.get('GESTION',0),'alarmas':alarms,'por_fuente':by_source,'por_distrito':by_district,'por_categoria':by_category,'por_mes':by_month,'recientes':recent}

    # ---------- catalogs ----------
    def upsert_catalog(self,kind,code,class_code,description,source_file=''):
        with self.connection() as c:c.execute('INSERT INTO catalogs(kind,code,class_code,description,source_file) VALUES(?,?,?,?,?) ON CONFLICT(kind,code,class_code) DO UPDATE SET description=excluded.description,source_file=excluded.source_file',(kind,code,class_code,description,source_file))
    def catalogs(self):
        with self.connection() as c:return [dict(r) for r in c.execute('SELECT * FROM catalogs ORDER BY kind,code,class_code')]
    def list_imports(self,limit=100):
        with self.connection() as c:return [dict(r) for r in c.execute('SELECT * FROM imports ORDER BY id DESC LIMIT ?',(int(limit),))]

    # ---------- referencias de cédulas jurídicas ----------
    def upsert_legal_reference(self,row:dict,source_file=''):
        ced=_clean(row.get('CEDULAJURIDICA') or row.get('CEDULA_JURIDICA') or row.get('CEDULA'))
        if not ced:return 0
        razon=_clean(row.get('RAZONSOCIAL') or row.get('RAZON_SOCIAL'))
        domicilio=_clean(row.get('DOMICILIO') or row.get('DIRECCION'))
        inicio=_clean(row.get('FECHA_INICIO') or row.get('FECHAINICIO'))
        vence=_clean(row.get('FECHA_VENCE') or row.get('FECHAVENCE'))
        rid=_clean(row.get('NUMERO_IDENTIFICACION') or row.get('NUMERO_IDENT') or row.get('CEDULA_REPRESENTANTE'))
        nombre=_clean(row.get('NOMBRE'));a1=_clean(row.get('APELLIDO_1') or row.get('APELLIDO1'));a2=_clean(row.get('APELLIDO_2') or row.get('APELLIDO2'))
        cargo=_clean(row.get('CARGO'));rep=_clean(row.get('REPRESENTACION'))
        with self.connection() as c:
            c.execute('''INSERT INTO legal_entities(cedula_juridica,razon_social,domicilio,fecha_inicio,fecha_vence,source_file) VALUES(?,?,?,?,?,?)
                ON CONFLICT(cedula_juridica) DO UPDATE SET razon_social=CASE WHEN excluded.razon_social<>'' THEN excluded.razon_social ELSE legal_entities.razon_social END,domicilio=CASE WHEN excluded.domicilio<>'' THEN excluded.domicilio ELSE legal_entities.domicilio END,fecha_inicio=CASE WHEN excluded.fecha_inicio<>'' THEN excluded.fecha_inicio ELSE legal_entities.fecha_inicio END,fecha_vence=CASE WHEN excluded.fecha_vence<>'' THEN excluded.fecha_vence ELSE legal_entities.fecha_vence END,source_file=excluded.source_file,updated_at=CURRENT_TIMESTAMP''',(ced,razon,domicilio,inicio,vence,_clean(source_file)))
            c.execute('''INSERT INTO legal_representatives(cedula_juridica,numero_identificacion,nombre,apellido_1,apellido_2,cargo,representacion,source_file) VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(cedula_juridica,numero_identificacion,cargo,representacion) DO UPDATE SET nombre=excluded.nombre,apellido_1=excluded.apellido_1,apellido_2=excluded.apellido_2,source_file=excluded.source_file''',(ced,rid,nombre,a1,a2,cargo,rep,_clean(source_file)))
        return 1

    def search_legal_entities(self,search='',limit=100):
        q=f'%{_clean(search)}%'
        with self.connection() as c:
            return [dict(r) for r in c.execute('''SELECT e.*,COUNT(r.numero_identificacion) representantes FROM legal_entities e LEFT JOIN legal_representatives r ON r.cedula_juridica=e.cedula_juridica WHERE e.cedula_juridica LIKE ? OR e.razon_social LIKE ? GROUP BY e.cedula_juridica ORDER BY e.razon_social,e.cedula_juridica LIMIT ?''',(q,q,int(limit)))]

    # ---------- referencias registrales/catastrales (ZIP/RAR) ----------
    @staticmethod
    def _registry_reference_values(row:dict,kind='',district='',source_file=''):
        r={str(k).upper():v for k,v in (row or {}).items()}
        def val(*names):
            for name in names:
                x=_clean(r.get(name))
                if x and 'NO EXISTEN REGISTROS' not in x.upper():return x
            return ''
        prov=val('PROVINCIA_FINCA','CODIGO_PROVINCIA')
        num=val('NUMERO_FINCA')
        finca=''
        if prov.isdigit() and num.isdigit():finca=f'{int(prov)}-{int(num)}'
        pprov=val('PROVINCIA_INSC','PROVINCIA_INSCRIPCION')
        pnum=val('NUMERO_INSC','NUMERO_INSCRIPCION')
        pyear=val('ANO_INSC','ANNO_INSCRIPCION')
        plan_key='-'.join(x for x in (pprov,pnum,pyear) if x) if pnum else ''
        raw=json.dumps(r,ensure_ascii=False,sort_keys=True,default=str)
        signature=hashlib.sha256('|'.join((_clean(kind).upper(),normalize_district(district),finca,plan_key,raw)).encode('utf-8')).hexdigest()
        return signature,_clean(kind).upper(),normalize_district(district),finca,plan_key,_clean(source_file),raw

    def upsert_registry_reference(self,row:dict,kind='',district='',source_file=''):
        values=self._registry_reference_values(row,kind,district,source_file)
        with self.connection() as c:
            existing=c.execute('SELECT id FROM registry_references WHERE reference_hash=?',(values[0],)).fetchone()
            if existing:
                c.execute('UPDATE registry_references SET source_file=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(values[5],existing['id']))
                return 0
            c.execute('INSERT INTO registry_references(reference_hash,kind,district,finca,plan_key,source_file,raw_json) VALUES(?,?,?,?,?,?,?)',values)
            return 1

    def list_registry_references(self,folio='',limit=250):
        finca=_clean(folio)
        import re as _re
        m=_re.match(r'^\s*(\d+)\s*-\s*(\d+)(?:\s*-\s*\d{1,3})?\s*$',finca)
        if m:finca=f'{int(m.group(1))}-{int(m.group(2))}'
        if not finca:return []
        with self.connection() as c:
            rows=c.execute("SELECT * FROM registry_references r WHERE r.finca=? OR (r.plan_key<>'' AND r.plan_key IN (SELECT plan_key FROM registry_references WHERE finca=? AND plan_key<>'')) ORDER BY kind,plan_key,id LIMIT ?",(finca,finca,int(limit))).fetchall()
        return [dict(r) for r in rows]

    def export_registry_reference_rows(self):
        with self.connection() as c:
            return [dict(r) for r in c.execute('SELECT kind,district,finca,plan_key,source_file,raw_json FROM registry_references ORDER BY id ASC')]

    def export_legal_entity_rows(self):
        with self.connection() as c:return [dict(r) for r in c.execute('SELECT cedula_juridica,razon_social,domicilio,fecha_inicio,fecha_vence,source_file FROM legal_entities ORDER BY cedula_juridica')]

    def export_legal_representative_rows(self):
        with self.connection() as c:return [dict(r) for r in c.execute('SELECT cedula_juridica,numero_identificacion,nombre,apellido_1,apellido_2,cargo,representacion,source_file FROM legal_representatives ORDER BY cedula_juridica,numero_identificacion')]

    # ---------- portable SENDA transfer ----------
    def export_case_rows(self):
        with self.connection() as c:
            return [dict(r) for r in c.execute('SELECT * FROM case_files ORDER BY id ASC')]

    def export_selection_rows(self):
        with self.connection() as c:
            rows=c.execute('''SELECT cf.folio case_folio,cf.plano case_plano,m.* FROM case_movement_selection s JOIN case_files cf ON cf.id=s.case_id JOIN movements m ON m.id=s.movement_id ORDER BY cf.id,m.id''').fetchall()
        out=[]
        for r0 in rows:
            r=dict(r0);sig=_movement_signature((r.get('finca') or r.get('folio'),r.get('derecho_numero'),r.get('derecho'),r.get('plano'),r.get('fecha'),r.get('codigo'),r.get('operacion'),r.get('fuente'),r.get('cedula'),r.get('titular'),r.get('tramite')))
            out.append({'folio':r.get('case_folio',''),'plano':r.get('case_plano',''),'signature':sig})
        return out

    def export_audit_rows(self):
        with self.connection() as c:
            return [dict(r) for r in c.execute('''SELECT cf.folio,cf.plano,ca.action,ca.previous_status,ca.new_status,
                ca.note,ca.payload_json,ca.created_at FROM case_audit ca
                JOIN case_files cf ON cf.id=ca.case_id ORDER BY ca.id ASC''')]

    def merge_sync_payload(self,payload:dict,source_name='SENDA_TRANSFER'):
        if str(payload.get('formato',''))!='SENDA_TRANSFER':raise ValueError('Formato SENDA de intercambio inválido')
        movements=payload.get('movimientos') or [];cases=payload.get('expedientes') or [];audits=payload.get('auditoria') or [];references=payload.get('referencias_registrales') or [];legal_entities=payload.get('cedulas_juridicas') or [];legal_reps=payload.get('representantes') or []
        inserted=duplicates=cases_inserted=cases_updated=cases_older=audits_inserted=audits_duplicates=0
        with self.connection() as c:
            cur=c.execute("INSERT INTO imports(anio,trimestre,distrito,source_name,source_hash,status) VALUES(NULL,NULL,'SIN IDENTIFICAR',?,'','PROCESSING')",(_clean(source_name),));import_id=cur.lastrowid
            sql='''INSERT OR IGNORE INTO movements(folio,finca,derecho_numero,derecho,plano,fecha,codigo,operacion,enlace,tipo,fuente,categoria,cedula,tipo_ident,titular,tramite,anio_tramite,anio,mes,trimestre,distrito,archivo_origen,import_id,raw_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'''
            for r in movements:
                d=parse_date(r.get('fecha'));year=int(r.get('anio') or (d.year if d else date.today().year));month=int(r.get('mes') or (d.month if d else 0) or 0);q=str(r.get('trimestre') or (quarter_for_month(month) if month else ''))
                op=_clean(r.get('operacion'));src=_clean(r.get('fuente') or r.get('tipo'));cat=_clean(r.get('categoria')) or movement_category(op,src)
                folio=_clean(r.get('folio'));finca=_clean(r.get('finca'));derecho_numero=_clean(r.get('derecho_numero'));derecho=_clean(r.get('derecho'));plano=_clean(r.get('plano'));fecha=d.isoformat() if d else '';codigo=_clean(r.get('codigo'));cedula=_clean(r.get('cedula'));tipo_ident=_clean(r.get('tipo_ident'));titular=_clean(r.get('titular'));tramite=_clean(r.get('tramite'));anio_tramite=int(r.get('anio_tramite') or 0)
                if not finca:
                    m=__import__('re').match(r'^\s*(\d+)\s*-\s*(\d+)(?:\s*-\s*(\d{1,3}))?\s*$',folio)
                    if m:
                        finca=f'{int(m.group(1))}-{int(m.group(2))}'
                        if not derecho_numero and m.group(3):derecho_numero=f'{int(m.group(3)):03d}'
                signature=_movement_signature((finca or folio,derecho_numero,derecho,plano,fecha,codigo,op,src,cedula,titular,tramite))
                before=c.total_changes;c.execute('INSERT OR IGNORE INTO movement_signatures(signature) VALUES(?)',(signature,))
                if c.total_changes==before:duplicates+=1;continue
                vals=(folio,finca,derecho_numero,derecho,plano,fecha,codigo,op,'',_clean(r.get('tipo')),src,cat,cedula,tipo_ident,titular,tramite,anio_tramite,year,month,q,normalize_district(r.get('distrito')),_clean(r.get('archivo_origen') or source_name),import_id,json.dumps(_sanitize_movement_payload(r),ensure_ascii=False,default=str))
                curm=c.execute(sql,vals)
                if curm.rowcount:
                    inserted+=1;c.execute('UPDATE movement_signatures SET movement_id=? WHERE signature=?',(curm.lastrowid,signature))
                else:
                    c.execute('DELETE FROM movement_signatures WHERE signature=? AND movement_id IS NULL',(signature,));duplicates+=1

            allowed=('folio','plano','distrito','status','responsable','prioridad','note','control_started_at','finalized_at','management_started_at','management_state','created_at','updated_at')
            for inc in cases:
                folio=_clean(inc.get('folio'));plano=_clean(inc.get('plano'))
                if not folio and not plano:continue
                existing=self._find_case(c,folio,plano)
                normalized={
                    'folio':folio,'plano':plano,'distrito':normalize_district(inc.get('distrito')),
                    'status':_canonical_status(inc.get('status')),'responsable':_clean(inc.get('responsable')),
                    'prioridad':_clean(inc.get('prioridad')).upper() or 'NORMAL','note':_clean(inc.get('note')),
                    'control_started_at':_clean(inc.get('control_started_at')) or None,'finalized_at':_clean(inc.get('finalized_at')) or None,
                    'management_started_at':_clean(inc.get('management_started_at')) or None,
                    'management_state':(_clean(inc.get('management_state')).upper() if _clean(inc.get('management_state')).upper() in ('PENDIENTE','NOTIFICADO','REGISTRADO') else 'PENDIENTE'),
                    'created_at':_clean(inc.get('created_at')) or None,'updated_at':_clean(inc.get('updated_at')) or None,
                }
                if not existing:
                    c.execute('''INSERT INTO case_files(folio,plano,distrito,status,responsable,prioridad,note,control_started_at,finalized_at,management_started_at,management_state,created_at,updated_at)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,COALESCE(?,CURRENT_TIMESTAMP),COALESCE(?,CURRENT_TIMESTAMP))''',tuple(normalized[k] for k in allowed))
                    cases_inserted+=1;continue
                incoming_ts=normalized['updated_at'] or '';local_ts=_clean(existing.get('updated_at'))
                if incoming_ts and local_ts and incoming_ts<local_ts:
                    cases_older+=1;continue
                compare=('folio','plano','distrito','status','responsable','prioridad','note','control_started_at','finalized_at','management_started_at','management_state')
                changed=any((_clean(existing.get(k)) if k!='status' else _canonical_status(existing.get(k))) != (_clean(normalized.get(k)) if k!='status' else normalized['status']) for k in compare)
                if not changed:continue
                previous=existing['status'];c.execute('''UPDATE case_files SET folio=?,plano=?,distrito=?,status=?,responsable=?,prioridad=?,note=?,control_started_at=?,finalized_at=?,management_started_at=?,management_state=?,updated_at=COALESCE(?,updated_at) WHERE id=?''',
                    (normalized['folio'],normalized['plano'],normalized['distrito'],normalized['status'],normalized['responsable'],normalized['prioridad'],normalized['note'],normalized['control_started_at'],normalized['finalized_at'],normalized['management_started_at'],normalized['management_state'],normalized['updated_at'],existing['id']))
                self._audit(c,existing['id'],'SINCRONIZAR DESDE ARCHIVO',previous,normalized['status'],'',{ 'source':source_name })
                cases_updated+=1

            for a in audits:
                folio=_clean(a.get('folio'));plano=_clean(a.get('plano'));case=self._find_case(c,folio,plano)
                if not case:continue
                action=_clean(a.get('action'));prev=_clean(a.get('previous_status'));new=_clean(a.get('new_status'));note=_clean(a.get('note'));created=_clean(a.get('created_at'))
                payload_json=a.get('payload_json')
                if isinstance(payload_json,(dict,list)):payload_json=json.dumps(payload_json,ensure_ascii=False,sort_keys=True,default=str)
                payload_json=_clean(payload_json) or '{}'
                exists=c.execute('''SELECT 1 FROM case_audit WHERE case_id=? AND action=? AND COALESCE(previous_status,'')=? AND COALESCE(new_status,'')=? AND COALESCE(note,'')=? AND COALESCE(payload_json,'')=? AND COALESCE(created_at,'')=? LIMIT 1''',
                    (case['id'],action,prev,new,note,payload_json,created)).fetchone()
                if exists:audits_duplicates+=1;continue
                c.execute('''INSERT INTO case_audit(case_id,action,previous_status,new_status,note,payload_json,created_at) VALUES(?,?,?,?,?,?,COALESCE(?,CURRENT_TIMESTAMP))''',(case['id'],action,prev,new,note,payload_json,created or None));audits_inserted+=1
            for sel in payload.get('selecciones') or []:
                case=self._find_case(c,_clean(sel.get('folio')),_clean(sel.get('plano')))
                if not case:continue
                signature=_clean(sel.get('signature'))
                if not signature:continue
                found=c.execute('SELECT movement_id FROM movement_signatures WHERE signature=?',(signature,)).fetchone()
                if found and found['movement_id']:
                    c.execute('INSERT OR IGNORE INTO case_movement_selection(case_id,movement_id) VALUES(?,?)',(case['id'],int(found['movement_id'])))
            c.execute("UPDATE imports SET records=?,skipped=?,errors=0,status='COMPLETED' WHERE id=?",(inserted,duplicates,import_id))
        references_merged=0
        for rr in references:
            raw=rr.get('raw_json') if isinstance(rr,dict) else None
            if isinstance(raw,str):
                try:raw=json.loads(raw)
                except Exception:raw={}
            if not isinstance(raw,dict):raw={}
            references_merged += self.upsert_registry_reference(raw,rr.get('kind',''),rr.get('district',''),rr.get('source_file') or source_name)
        legal_merged=0
        for e in legal_entities:
            row={'CEDULAJURIDICA':e.get('cedula_juridica',''),'RAZONSOCIAL':e.get('razon_social',''),'DOMICILIO':e.get('domicilio',''),'FECHA_INICIO':e.get('fecha_inicio',''),'FECHA_VENCE':e.get('fecha_vence','')}
            legal_merged += self.upsert_legal_reference(row,e.get('source_file') or source_name)
        for r in legal_reps:
            row={'CEDULAJURIDICA':r.get('cedula_juridica',''),'NUMERO_IDENTIFICACION':r.get('numero_identificacion',''),'NOMBRE':r.get('nombre',''),'APELLIDO_1':r.get('apellido_1',''),'APELLIDO_2':r.get('apellido_2',''),'CARGO':r.get('cargo',''),'REPRESENTACION':r.get('representacion','')}
            legal_merged += self.upsert_legal_reference(row,r.get('source_file') or source_name)
        return {'import_id':import_id,'movements_inserted':inserted,'movements_duplicates':duplicates,'cases_inserted':cases_inserted,'cases_updated':cases_updated,'cases_older_skipped':cases_older,'audits_inserted':audits_inserted,'audits_duplicates':audits_duplicates,'references_merged':references_merged,'legal_metadata_merged':legal_merged}

    # ---------- cases / workflow ----------
    def _find_case(self,c,folio='',plano=''):
        folio=_clean(folio);plano=_clean(plano)
        if folio:
            row=c.execute('SELECT * FROM case_files WHERE folio=? ORDER BY id DESC LIMIT 1',(folio,)).fetchone()
            if row:return dict(row)
        if plano:
            row=c.execute("SELECT * FROM case_files WHERE plano=? AND COALESCE(folio,'')='' ORDER BY id DESC LIMIT 1",(plano,)).fetchone()
            if row:return dict(row)
        return None

    def _audit(self,c,case_id,action,previous='',new='',note='',payload=None):
        c.execute('INSERT INTO case_audit(case_id,action,previous_status,new_status,note,payload_json) VALUES(?,?,?,?,?,?)',(int(case_id),action,previous,new,_clean(note),json.dumps(payload or {},ensure_ascii=False,default=str)))

    def create_case(self,folio,district,note='',status='INFORMACION',plano='',responsable='',prioridad='NORMAL'):
        folio=_clean(folio);plano=_clean(plano)
        if not folio and not plano:raise ValueError('El expediente requiere folio/finca o plano')
        status=_canonical_status(status);district=normalize_district(district);prioridad=_clean(prioridad).upper() or 'NORMAL'
        with self.connection() as c:
            existing=self._find_case(c,folio,plano)
            if existing:
                c.execute('UPDATE case_files SET plano=COALESCE(NULLIF(?,\'\'),plano),distrito=?,note=CASE WHEN ?<>\'\' THEN ? ELSE note END,responsable=CASE WHEN ?<>\'\' THEN ? ELSE responsable END,prioridad=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(plano,district,_clean(note),_clean(note),_clean(responsable),_clean(responsable),prioridad,existing['id']))
                return existing['id']
            cur=c.execute('INSERT INTO case_files(folio,plano,distrito,status,note,responsable,prioridad) VALUES(?,?,?,?,?,?,?)',(folio,plano,district,status,_clean(note),_clean(responsable),prioridad));cid=cur.lastrowid
            self._audit(c,cid,'CREAR EXPEDIENTE','',status,note,{'folio':folio,'plano':plano});return cid

    def get_case(self,case_id:int):
        with self.connection() as c:
            r=c.execute('SELECT * FROM case_files WHERE id=?',(int(case_id),)).fetchone()
            if not r:raise KeyError('Expediente no encontrado')
            return dict(r)

    def update_case(self,case_id:int,changes:dict):
        allowed=('folio','plano','distrito','responsable','prioridad','note');sets=[];args=[]
        with self.connection() as c:
            old=c.execute('SELECT * FROM case_files WHERE id=?',(int(case_id),)).fetchone()
            if not old:raise KeyError('Expediente no encontrado')
            for k in allowed:
                if k in changes:
                    val=normalize_district(changes[k]) if k=='distrito' else _clean(changes[k]);sets.append(f'{k}=?');args.append(val)
            if not sets:return dict(old)
            sets.append('updated_at=CURRENT_TIMESTAMP');c.execute('UPDATE case_files SET '+','.join(sets)+' WHERE id=?',(*args,int(case_id)))
            self._audit(c,case_id,'MODIFICAR EXPEDIENTE',old['status'],old['status'],changes.get('note',''),{k:changes[k] for k in changes if k in allowed})
        return self.get_case(case_id)

    def select_cases_for_control(self,items):
        selected=0
        with self.connection() as c:
            for item in items:
                folio=_clean(item.get('folio'));plano=_clean(item.get('plano'))
                if not folio and not plano:continue
                case=self._find_case(c,folio,plano)
                if case and case['status']=='GESTION':continue
                if not case:
                    src=c.execute('SELECT distrito,plano FROM movements WHERE (?<>\'\' AND (finca=? OR folio=?)) OR (?=\'\' AND ?<>\'\' AND plano=?) ORDER BY fecha DESC LIMIT 1',(folio,folio,folio,folio,plano,plano)).fetchone()
                    district=(src['distrito'] if src else 'SIN IDENTIFICAR');real_plano=plano or (src['plano'] if src else '')
                    cur=c.execute("INSERT INTO case_files(folio,plano,distrito,status,control_started_at) VALUES(?,?,?,'EN CONTROL',CURRENT_TIMESTAMP)",(folio,real_plano,district));cid=cur.lastrowid;previous='INFORMACION'
                else:
                    cid=case['id'];previous=case['status'];c.execute("UPDATE case_files SET status='EN CONTROL',control_started_at=COALESCE(control_started_at,CURRENT_TIMESTAMP),updated_at=CURRENT_TIMESTAMP WHERE id=?",(cid,))
                self._audit(c,cid,'PASAR A CONTROL',previous,'EN CONTROL','',{'folio':folio,'plano':plano});selected+=1
        return selected

    def list_cases(self,search='',limit=200,status=None):
        q=f'%{_clean(search)}%';clauses=['(folio LIKE ? OR plano LIKE ? OR note LIKE ? OR distrito LIKE ? OR responsable LIKE ?)'];args=[q]*5
        if status:clauses.append('status=?');args.append(_canonical_status(status))
        sql='SELECT * FROM case_files WHERE '+' AND '.join(clauses)+' ORDER BY updated_at DESC,id DESC LIMIT ?';args.append(int(limit))
        with self.connection() as c:return [dict(r) for r in c.execute(sql,args)]

    def list_control(self,search='',limit=500):return self.list_cases(search,limit,'EN CONTROL')
    def list_management(self,search='',limit=500):
        rows=self.list_cases(search,limit,'GESTION')
        with self.connection() as c:
            for r in rows:
                r['selected_count']=c.execute('SELECT COUNT(*) n FROM case_movement_selection WHERE case_id=?',(int(r['id']),)).fetchone()['n']
        return rows

    def management_statistics(self,filters=None):
        filters=filters or {};clauses=["status='GESTION'","finalized_at IS NOT NULL"];args=[]
        year=filters.get('year');month=filters.get('month');quarter=filters.get('quarter');district=filters.get('district')
        if year not in (None,'','TODOS','ALL'):
            clauses.append("CAST(strftime('%Y',finalized_at) AS INTEGER)=?");args.append(int(year))
        if month not in (None,'','TODOS','ALL'):
            clauses.append("CAST(strftime('%m',finalized_at) AS INTEGER)=?");args.append(int(month))
        if quarter not in (None,'','TODOS','ALL'):
            qmap={'T1':(1,3),'T2':(4,6),'T3':(7,9),'T4':(10,12)};lo,hi=qmap[str(quarter).upper()]
            clauses.append("CAST(strftime('%m',finalized_at) AS INTEGER) BETWEEN ? AND ?");args.extend([lo,hi])
        if district not in (None,'','TODOS','TODAS','ALL'):
            clauses.append('distrito=?');args.append(normalize_district(district))
        where=' WHERE '+' AND '.join(clauses)
        with self.connection() as c:
            total=c.execute('SELECT COUNT(*) n FROM case_files'+where,args).fetchone()['n']
            by_month={int(r['m']):r['n'] for r in c.execute("SELECT CAST(strftime('%m',finalized_at) AS INTEGER) m,COUNT(*) n FROM case_files"+where+" GROUP BY m ORDER BY m",args)}
            by_district={r['distrito']:r['n'] for r in c.execute('SELECT distrito,COUNT(*) n FROM case_files'+where+' GROUP BY distrito ORDER BY n DESC',args)}
        return {'total':total,'por_mes':by_month,'por_distrito':by_district}

    def _case_movement_where(self,case):
        if case['folio']:return '(finca=? OR folio=?)',[case['folio'],case['folio']]
        if case.get('plano'):return 'plano=?',[case['plano']]
        return '1=0',[]

    def selected_movement_ids(self,case_id:int):
        with self.connection() as c:return [int(r['movement_id']) for r in c.execute('SELECT movement_id FROM case_movement_selection WHERE case_id=? ORDER BY movement_id',(int(case_id),))]

    def set_case_movement_selection(self,case_id:int,movement_ids):
        case=self.get_case(case_id);where,args=self._case_movement_where(case)
        ids=sorted({int(x) for x in (movement_ids or [])})
        with self.connection() as c:
            if ids:
                marks=','.join('?' for _ in ids)
                valid={int(r['id']) for r in c.execute(f'SELECT id FROM movements WHERE ({where}) AND id IN ({marks})',(*args,*ids))}
                if valid!=set(ids):raise ValueError('La selección contiene movimientos que no pertenecen al expediente')
            c.execute('DELETE FROM case_movement_selection WHERE case_id=?',(int(case_id),))
            c.executemany('INSERT INTO case_movement_selection(case_id,movement_id) VALUES(?,?)',[(int(case_id),i) for i in ids])
            self._audit(c,case_id,'SELECCIONAR MOVIMIENTOS',case['status'],case['status'],'',{'movement_ids':ids,'count':len(ids)})
        return {'selected_ids':ids,'selected_count':len(ids)}

    def case_movements(self,case_id:int,category='TODOS',limit=25,offset=0,selected_only=False):
        if int(limit) not in PAGE_SIZES:raise ValueError('Tamaño de página permitido: 25, 50 o 100')
        case=self.get_case(case_id);where,args=self._case_movement_where(case);clauses=[where]
        if category not in (None,'','TODOS','TODAS','ALL'):clauses.append('m.categoria=?');args.append(category)
        def _alias_clause(x):
            return x.replace('finca=?','m.finca=?').replace('folio=?','m.folio=?').replace('plano=?','m.plano=?')
        base=' AND '.join(f'({_alias_clause(x)})' for x in clauses)
        if selected_only:base+=' AND EXISTS(SELECT 1 FROM case_movement_selection s WHERE s.case_id=? AND s.movement_id=m.id)';args.append(int(case_id))
        with self.connection() as c:
            total=c.execute('SELECT COUNT(*) n FROM movements m WHERE '+base,args).fetchone()['n']
            rows=[_public_movement(r) for r in c.execute('''SELECT m.*,EXISTS(SELECT 1 FROM case_movement_selection s WHERE s.case_id=? AND s.movement_id=m.id) selected FROM movements m WHERE '''+base+" ORDER BY CASE WHEN m.fecha='' THEN 1 ELSE 0 END,m.fecha ASC,m.id ASC LIMIT ? OFFSET ?",(int(case_id),*args,int(limit),int(offset)))]
            selected_count=c.execute('SELECT COUNT(*) n FROM case_movement_selection WHERE case_id=?',(int(case_id),)).fetchone()['n']
        for r in rows:r['alarma']=alarm_level(parse_date(r.get('fecha')));r['selected']=bool(r.get('selected'))
        return {'rows':rows,'total':total,'selected_count':selected_count,'selected_ids':self.selected_movement_ids(case_id),'limit':int(limit),'offset':int(offset)}

    def case_detail(self,case_id:int):
        case=self.get_case(case_id);where,args=self._case_movement_where(case)
        with self.connection() as c:
            total=c.execute('SELECT COUNT(*) n FROM movements WHERE '+where,args).fetchone()['n']
            rights=[dict(r) for r in c.execute("SELECT COALESCE(NULLIF(derecho_numero,''),NULLIF(derecho,''),'GENERAL') derecho_numero,COALESCE(NULLIF(derecho,''),'GENERAL') derecho,COUNT(*) movimientos,MIN(NULLIF(fecha,'')) primera_fecha,MAX(NULLIF(fecha,'')) ultima_fecha FROM movements WHERE "+where+" GROUP BY COALESCE(NULLIF(derecho_numero,''),NULLIF(derecho,''),'GENERAL'),COALESCE(NULLIF(derecho,''),'GENERAL') ORDER BY derecho_numero,derecho",args)]
            cats={r['categoria']:r['n'] for r in c.execute('SELECT categoria,COUNT(*) n FROM movements WHERE '+where+' GROUP BY categoria ORDER BY n DESC',args)}
        return {'case':case,'derechos':rights,'referencias':self.list_registry_references(case.get('folio','')),'movimientos_total':total,'movimientos_seleccionados':len(self.selected_movement_ids(case_id)),'categorias':cats,'audit':self.case_audit(case_id)}

    def finalize_case(self,case_id:int,note=''):
        with self.connection() as c:
            old=c.execute('SELECT * FROM case_files WHERE id=?',(int(case_id),)).fetchone()
            if not old:raise KeyError('Expediente no encontrado')
            if old['status']!='EN CONTROL':raise ValueError('Solo un trámite en Control puede finalizarse')
            selected=c.execute('SELECT COUNT(*) n FROM case_movement_selection WHERE case_id=?',(int(case_id),)).fetchone()['n']
            if not selected:raise ValueError('Para finalizar, seleccione al menos un movimiento del expediente')
            c.execute("UPDATE case_files SET status='GESTION',management_state='PENDIENTE',finalized_at=CURRENT_TIMESTAMP,management_started_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE id=?",(int(case_id),))
            self._audit(c,case_id,'FINALIZAR CONTROL','EN CONTROL','GESTION',note,{'movimientos_seleccionados':selected})
        return self.get_case(case_id)

    def set_management_state(self,case_id:int,state:str):
        state=_clean(state).upper()
        if state not in ('PENDIENTE','NOTIFICADO','REGISTRADO'):raise ValueError('Estado de Gestión inválido')
        with self.connection() as c:
            old=c.execute('SELECT * FROM case_files WHERE id=?',(int(case_id),)).fetchone()
            if not old:raise KeyError('Expediente no encontrado')
            if old['status']!='GESTION':raise ValueError('Solo un trámite en Gestión puede cambiar este estado')
            previous=_clean(old['management_state']) or 'PENDIENTE'
            c.execute('UPDATE case_files SET management_state=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(state,int(case_id)))
            self._audit(c,case_id,'CAMBIAR ESTADO GESTION',previous,state,'')
        return self.get_case(case_id)

    def return_case_to_information(self,case_id:int,note=''):
        with self.connection() as c:
            old=c.execute('SELECT * FROM case_files WHERE id=?',(int(case_id),)).fetchone()
            if not old:raise KeyError('Expediente no encontrado')
            if old['status']!='GESTION':raise ValueError('Solo un trámite en Gestión puede regresar')
            c.execute("UPDATE case_files SET status='INFORMACION',management_state='PENDIENTE',control_started_at=NULL,finalized_at=NULL,management_started_at=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=?",(int(case_id),));c.execute('DELETE FROM case_movement_selection WHERE case_id=?',(int(case_id),))
            self._audit(c,case_id,'REGRESAR A INFORMACION SENDA','GESTION','INFORMACION',note)
        return self.get_case(case_id)

    def case_audit(self,case_id:int):
        with self.connection() as c:return [dict(r) for r in c.execute('SELECT * FROM case_audit WHERE case_id=? ORDER BY id ASC',(int(case_id),))]

    def add_case_attachment(self,case_id:int,filename:str,stored_path:str):
        with self.connection() as c:
            cur=c.execute('INSERT INTO case_attachments(case_id,filename,stored_path) VALUES(?,?,?)',(int(case_id),filename,stored_path));return cur.lastrowid
    def list_case_attachments(self,case_id:int):
        with self.connection() as c:return [dict(r) for r in c.execute('SELECT * FROM case_attachments WHERE case_id=? ORDER BY id DESC',(int(case_id),))]
