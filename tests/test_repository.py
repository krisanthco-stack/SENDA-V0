import tempfile, unittest
from pathlib import Path
from app.repository import Repository

class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.td=tempfile.TemporaryDirectory(); self.db=Path(self.td.name)/'senda.sqlite'; self.repo=Repository(self.db)
    def tearDown(self): self.td.cleanup()

    def test_insert_and_filter_by_year_month_quarter_district_alarm(self):
        rows=[
            {'folio':'4-100-001','fecha':'2026-03-01','distrito':'Horquetas','fuente':'FINCAS','codigo':'PE1','operacion':'COMPRAVENTA','titular':'A'},
            {'folio':'4-200-001','fecha':'2026-04-15','distrito':'Puerto Viejo','fuente':'FINCAS','codigo':'PG1','operacion':'DONACION','titular':'B'},
        ]
        self.repo.insert_movements(rows, import_id=1)
        got=self.repo.list_movements({'year':'2026','quarter':'T1','month':'3','district':'HORQUETAS'})
        self.assertEqual(len(got),1); self.assertEqual(got[0]['folio'],'4-100-001')
        self.assertEqual(got[0]['trimestre'],'T1'); self.assertEqual(got[0]['mes'],3)

    def test_dashboard_counts_distinct_folios_and_sources(self):
        self.repo.insert_movements([
            {'folio':'4-100-001','fecha':'2026-03-01','distrito':'HORQUETAS','fuente':'FINCAS'},
            {'folio':'4-100-001','fecha':'2026-03-05','distrito':'HORQUETAS','fuente':'GRAVAMENES'},
        ], import_id=1)
        d=self.repo.dashboard({'year':'2026','quarter':'T1','district':'HORQUETAS'})
        self.assertEqual(d['movimientos'],2); self.assertEqual(d['folios'],1)
        self.assertEqual(d['por_fuente']['FINCAS'],1); self.assertEqual(d['por_fuente']['GRAVAMENES'],1)


    def test_dashboard_aggregates_in_sql_without_materializing_movements(self):
        self.repo.insert_movements([
            {'folio':'4-1-001','fecha':'2026-03-01','distrito':'HORQUETAS','fuente':'FINCAS'},
            {'folio':'4-2-001','fecha':'2026-03-02','distrito':'HORQUETAS','fuente':'GRAVAMENES'},
        ], import_id=1)
        original=self.repo.list_movements
        self.repo.list_movements=lambda *a,**k: (_ for _ in ()).throw(AssertionError('dashboard must not materialize rows'))
        try:
            d=self.repo.dashboard({'year':'2026','quarter':'T1','district':'HORQUETAS'})
        finally:
            self.repo.list_movements=original
        self.assertEqual(d['movimientos'],2)
        self.assertEqual(d['folios'],2)
        self.assertEqual(d['por_fuente'],{'FINCAS':1,'GRAVAMENES':1})

    def test_alarm_filter_uses_latest_movement_per_folio(self):
        from datetime import date, timedelta
        today=date.today()
        self.repo.insert_movements([
            {'folio':'4-OLDTHENNEW-001','fecha':(today-timedelta(days=120)).isoformat(),'distrito':'HORQUETAS','fuente':'HISTORICOS'},
            {'folio':'4-OLDTHENNEW-001','fecha':(today-timedelta(days=10)).isoformat(),'distrito':'HORQUETAS','fuente':'HISTORICOS'},
            {'folio':'4-OLDONLY-001','fecha':(today-timedelta(days=120)).isoformat(),'distrito':'HORQUETAS','fuente':'HISTORICOS'},
        ], import_id=1)
        red=self.repo.list_movements({'district':'HORQUETAS','alarm':'red'})
        self.assertEqual({r['folio'] for r in red},{'4-OLDONLY-001'})


    def test_migration_rebuilds_logical_signatures_for_existing_rows(self):
        row={'folio':'4-990-001','fecha':'2026-03-01','distrito':'HORQUETAS','fuente':'FINCAS','codigo':'PE1','operacion':'COMPRAVENTA','titular':'A','archivo_origen':'corte_a.csv'}
        self.repo.insert_movements([dict(row, _source_signature='firma-antigua')], import_id=1)
        with self.repo.connection() as c:
            c.execute('DELETE FROM movement_signatures')
            c.execute("INSERT INTO movement_signatures(signature,movement_id) VALUES('firma-antigua',1)")
            c.execute("DELETE FROM settings WHERE key='movement_signature_version'")
        # Reabrir simula actualizar una base 0.4.2 a 0.4.3.
        upgraded=Repository(self.db)
        inserted=upgraded.insert_movements([dict(row, archivo_origen='corte_b.csv')], import_id=2)
        self.assertEqual(inserted,0)
        self.assertEqual(upgraded.last_insert_duplicates,1)
        self.assertEqual(len(upgraded.list_movements({'district':'HORQUETAS'})),1)

if __name__=='__main__': unittest.main()
