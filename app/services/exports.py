from __future__ import annotations
import csv, json
from pathlib import Path

COLS=['folio','finca','derecho_numero','derecho','plano','fecha','codigo','operacion','categoria','tipo','fuente','cedula','tipo_ident','titular','tramite','anio_tramite','anio','mes','trimestre','distrito','archivo_origen','alarma','case_id','estado_expediente','en_control','en_gestion']

def iter_pages(repo,filters,page_size=5000):
    offset=0
    while True:
        rows=repo.list_movements(filters,limit=page_size,offset=offset)
        if not rows:break
        yield rows
        offset += len(rows)
        if len(rows)<page_size:break

def export_json(repo,filters,target:Path):
    with target.open('w',encoding='utf-8') as f:
        f.write('{"sistema":"SENDA.V0","movimientos":['); first=True
        for page in iter_pages(repo,filters):
            for row in page:
                if not first:f.write(',')
                json.dump({k:row.get(k,'') for k in COLS},f,ensure_ascii=False); first=False
        f.write(']}')
    return target

def export_csv(repo,filters,target:Path):
    with target.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=COLS,delimiter=';');w.writeheader()
        for page in iter_pages(repo,filters):
            for row in page:w.writerow({k:row.get(k,'') for k in COLS})
    return target

def _xlsxwriter():
    try:
        import xlsxwriter
    except Exception as e:
        raise RuntimeError('XLSX requiere xlsxwriter instalado por pip.') from e
    return xlsxwriter

def export_xlsx(repo,filters,target:Path):
    xlsxwriter=_xlsxwriter()
    wb=xlsxwriter.Workbook(str(target),{'constant_memory':True})
    ws=wb.add_worksheet('Movimientos'); hdr=wb.add_format({'bold':True,'bg_color':'#DCE6F1','border':1})
    for c,name in enumerate(COLS):ws.write(0,c,name.upper(),hdr)
    rix=1
    for page in iter_pages(repo,filters):
        for row in page:
            for c,name in enumerate(COLS):ws.write(rix,c,row.get(name,''))
            rix+=1
    ws.freeze_panes(1,0); ws.autofilter(0,0,max(0,rix-1),len(COLS)-1)
    ws.set_column(0,len(COLS)-1,16);ws.set_column(COLS.index('operacion'),COLS.index('operacion'),36)
    wb.close();return target

def _case_rows(repo,case_id):
    result=repo.case_movements(case_id,category='TODOS',limit=100,offset=0,selected_only=True)
    rows=list(result['rows']);offset=len(rows)
    while offset<result['total']:
        page=repo.case_movements(case_id,category='TODOS',limit=100,offset=offset,selected_only=True)
        rows.extend(page['rows']);offset+=len(page['rows'])
        if not page['rows']:break
    return rows

def export_management_case_json(repo,case_id:int,target:Path):
    case=repo.get_case(case_id)
    if case['status']!='GESTION':raise ValueError('El expediente no está en Gestión')
    rows=_case_rows(repo,case_id)
    with target.open('w',encoding='utf-8') as f:
        json.dump({'sistema':'SENDA.V0','tipo':'GESTION','expediente':case,'movimientos_seleccionados':[{k:r.get(k,'') for k in COLS} for r in rows]},f,ensure_ascii=False,indent=2,default=str)
    return target

def export_management_case_xlsx(repo,case_id:int,target:Path):
    case=repo.get_case(case_id)
    if case['status']!='GESTION':raise ValueError('El expediente no está en Gestión')
    rows=_case_rows(repo,case_id);xlsxwriter=_xlsxwriter();wb=xlsxwriter.Workbook(str(target),{'constant_memory':True})
    hdr=wb.add_format({'bold':True,'bg_color':'#DCE6F1','border':1})
    meta=wb.add_worksheet('GESTION');meta.write_row(0,0,['CAMPO','VALOR'],hdr)
    for i,k in enumerate(('folio','plano','distrito','responsable','prioridad','management_state','finalized_at','note'),start=1):meta.write_row(i,0,[k.upper(),case.get(k,'')])
    ws=wb.add_worksheet('MOVIMIENTOS SELECCIONADOS')
    for c,name in enumerate(COLS):ws.write(0,c,name.upper(),hdr)
    for rix,row in enumerate(rows,start=1):
        for c,name in enumerate(COLS):ws.write(rix,c,row.get(name,''))
    ws.freeze_panes(1,0);ws.set_column(0,len(COLS)-1,17);ws.set_column(COLS.index('operacion'),COLS.index('operacion'),38)
    wb.close();return target
