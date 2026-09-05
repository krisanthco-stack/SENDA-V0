from __future__ import annotations
from datetime import date, datetime
import re
import unicodedata

DISTRICTS = ('PUERTO VIEJO','LA VIRGEN','HORQUETAS','LLANURAS DEL GASPAR','CUREÑA')
DISTRICT_CODES = {'PUERTO VIEJO':'41001','LA VIRGEN':'41002','HORQUETAS':'41003','LLANURAS DEL GASPAR':'41004','CUREÑA':'41005'}

def _ascii(value: object) -> str:
    s = unicodedata.normalize('NFKD', str(value or '')).encode('ascii','ignore').decode('ascii')
    return re.sub(r'\s+', ' ', s).strip().upper()

def normalize_district(value: object) -> str:
    s=_ascii(value)
    aliases={
        '1':'PUERTO VIEJO','2':'LA VIRGEN','3':'HORQUETAS','4':'LLANURAS DEL GASPAR','5':'CUREÑA',
        '41001':'PUERTO VIEJO','41002':'LA VIRGEN','41003':'HORQUETAS','41004':'LLANURAS DEL GASPAR','41005':'CUREÑA',
        'LAS HORQUETAS':'HORQUETAS','HORQUETA':'HORQUETAS',
        'PUERTO VIEJO DE SARAPIQUI':'PUERTO VIEJO',
        'LLANURAS GASPAR':'LLANURAS DEL GASPAR','LLANURAS DEL GASPAR':'LLANURAS DEL GASPAR',
        'LA VIRGEN':'LA VIRGEN','CURENA':'CUREÑA','CUREÑA':'CUREÑA'
    }
    s=aliases.get(s,s)
    return s if s in DISTRICTS else 'SIN IDENTIFICAR'

def quarter_for_month(month: int) -> str:
    m=int(month)
    if not 1 <= m <= 12: raise ValueError('Mes inválido')
    return f'T{((m-1)//3)+1}'

def parse_date(value: object) -> date | None:
    if value in (None,''): return None
    if isinstance(value, datetime): return value.date()
    if isinstance(value, date): return value
    s=str(value).strip()[:19]
    for fmt in ('%Y-%m-%d','%d/%m/%Y','%d-%m-%Y','%Y/%m/%d','%d.%m.%Y'):
        try: return datetime.strptime(s[:10],fmt).date()
        except ValueError: pass
    m=re.search(r'(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})',s)
    if m:
        try:return date(int(m.group(1)),int(m.group(2)),int(m.group(3)))
        except ValueError:return None
    return None

def alarm_level(last_movement: date | None, reference: date | None=None) -> str:
    if not last_movement: return 'green'
    reference=reference or date.today()
    age=(reference-last_movement).days
    return 'red' if age>=90 else 'yellow' if age>60 else 'green'
