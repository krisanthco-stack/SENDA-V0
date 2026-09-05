from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .config import ensure_data_dirs
from .repository import Repository
from .importers.engine import ImportEngine
from .services.exports import export_csv, export_json, export_xlsx
from .services.sync_transfer import detect_sync_file, import_sync_file, export_sync_json, export_sync_xlsx

MOVEMENT_CATEGORIES = (
    'TODOS','FINCAS','HIPOTECAS','GRAVÁMENES','SEGREGACIONES',
    'ANOTACIONES','HISTÓRICOS','CERRADAS','OTROS'
)
PAGE_SIZES = (25, 50, 100)
DISTRICTS = ('TODOS','PUERTO VIEJO','LA VIRGEN','HORQUETAS','LLANURAS DEL GASPAR','CUREÑA','SIN IDENTIFICAR')
ALARMS = ('TODAS','red','yellow','green')
QUARTERS = ('TODOS','T1','T2','T3','T4')
MONTHS = ('TODOS',) + tuple(str(i) for i in range(1,13))


ALARM_VISUALS = {
    'red': {'label': '🔴 ROJA', 'tag': 'alarm_red', 'background': '#fee2e2', 'foreground': '#991b1b'},
    'yellow': {'label': '🟡 AMARILLA', 'tag': 'alarm_yellow', 'background': '#fef9c3', 'foreground': '#854d0e'},
    'green': {'label': '🟢 VERDE', 'tag': 'alarm_green', 'background': '#dcfce7', 'foreground': '#166534'},
}


def alarm_visual(level: str) -> dict:
    key = str(level or 'green').strip().lower()
    return dict(ALARM_VISUALS.get(key, ALARM_VISUALS['green']))


def information_alarm_row(row: dict, checked: bool = False):
    visual = alarm_visual(row.get('alarma'))
    values = (
        '☑' if checked else '☐', row.get('folio',''), row.get('plano',''), row.get('distrito',''),
        row.get('status','INFORMACION'), row.get('movimientos',0), row.get('derechos',0), visual['label'],
        row.get('first_date') or '', row.get('last_date') or ''
    )
    return values, visual['tag']

@dataclass
class DesktopContext:
    data_root: Path
    dirs: dict
    repo: Repository
    importer: ImportEngine


def create_context(data_root: str | Path | None = None) -> DesktopContext:
    root, dirs = ensure_data_dirs(Path(data_root) if data_root else None)
    repo = Repository(dirs['database'] / 'senda_v0.sqlite')
    return DesktopContext(root, dirs, repo, ImportEngine(repo))


def filters_from_values(*, year='TODOS', quarter='TODOS', month='TODOS', district='TODOS', alarm='TODAS', movement='TODOS', search='') -> dict:
    out = {'search': str(search or '').strip()}
    if year not in (None,'','TODOS','ALL'): out['year'] = int(year)
    if quarter not in (None,'','TODOS','ALL'): out['quarter'] = quarter
    if month not in (None,'','TODOS','ALL'): out['month'] = int(month)
    if district not in (None,'','TODOS','ALL'): out['district'] = district
    if alarm not in (None,'','TODAS','ALL'): out['alarm'] = alarm
    if movement not in (None,'','TODOS','ALL'): out['movement_type'] = movement
    return out


def available_years(repo: Repository) -> list[str]:
    with repo.connection() as c:
        years = [str(r['anio']) for r in c.execute('SELECT DISTINCT anio FROM movements WHERE anio IS NOT NULL ORDER BY anio DESC')]
    return ['TODOS', *years]


def import_files(ctx: DesktopContext, paths: Iterable[str | Path], *, year: int, quarter: str, district: str):
    paths=[Path(p) for p in paths]
    sync_paths=[p for p in paths if detect_sync_file(p)]
    regular=[p for p in paths if p not in sync_paths]
    result={'inserted':0,'skipped':0,'duplicates':0,'errors':0,'files':[],'catalogs':0,'duplicate_import':False,'sync_files':[],'cases_inserted':0,'cases_updated':0,'audits_inserted':0}
    for p in sync_paths:
        merged=import_sync_file(ctx.repo,p)
        result['inserted']+=merged.get('movements_inserted',0);result['duplicates']+=merged.get('movements_duplicates',0)
        result['cases_inserted']+=merged.get('cases_inserted',0);result['cases_updated']+=merged.get('cases_updated',0);result['audits_inserted']+=merged.get('audits_inserted',0)
        result['files'].append(p.name);result['sync_files'].append(p.name)
    if regular:
        normal=ctx.importer.import_paths(regular,year=year,quarter=quarter,district=district)
        for key in ('inserted','skipped','duplicates','errors','catalogs'):result[key]+=int(normal.get(key,0))
        result['files'].extend(normal.get('files',[]));result['duplicate_import']=bool(normal.get('duplicate_import',False))
        if normal.get('import_id'):result['import_id']=normal['import_id']
    return result


def export_sync_database(ctx: DesktopContext, fmt: str, target: str | Path):
    fmt=str(fmt).lower();target=Path(target)
    if fmt in ('xlsx','excel'):return export_sync_xlsx(ctx.repo,target)
    if fmt=='json':return export_sync_json(ctx.repo,target)
    raise ValueError('La base SENDA fusionable se exporta en Excel o JSON')


def export_movements(ctx: DesktopContext, fmt: str, target: str | Path, filters: dict | None = None):
    target = Path(target)
    fmt = fmt.lower()
    if fmt == 'json': return export_json(ctx.repo, filters or {}, target)
    if fmt == 'csv': return export_csv(ctx.repo, filters or {}, target)
    if fmt in ('xlsx','excel'): return export_xlsx(ctx.repo, filters or {}, target)
    raise ValueError('Formato de exportación no soportado')
