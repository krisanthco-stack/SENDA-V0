import unittest
from datetime import date

from app.domain import quarter_for_month, normalize_district, alarm_level, parse_date

class DomainTests(unittest.TestCase):
    def test_quarter_mapping(self):
        expected={1:'T1',2:'T1',3:'T1',4:'T2',5:'T2',6:'T2',7:'T3',8:'T3',9:'T3',10:'T4',11:'T4',12:'T4'}
        self.assertEqual({m:quarter_for_month(m) for m in range(1,13)}, expected)

    def test_district_normalization(self):
        self.assertEqual(normalize_district('Horquetas'), 'HORQUETAS')
        self.assertEqual(normalize_district('Las Horquetas'), 'HORQUETAS')
        self.assertEqual(normalize_district('Puerto viejo'), 'PUERTO VIEJO')
        self.assertEqual(normalize_district('Llanuras del Gaspar'), 'LLANURAS DEL GASPAR')
        self.assertEqual(normalize_district(''), 'SIN IDENTIFICAR')
        self.assertEqual(normalize_district('1'), 'PUERTO VIEJO')
        self.assertEqual(normalize_district('2'), 'LA VIRGEN')
        self.assertEqual(normalize_district('3'), 'HORQUETAS')
        self.assertEqual(normalize_district('4'), 'LLANURAS DEL GASPAR')
        self.assertEqual(normalize_district('5'), 'CUREÑA')
        self.assertEqual(normalize_district('41003'), 'HORQUETAS')

    def test_alarm_thresholds_match_previous_senda(self):
        ref=date(2026, 9, 1)
        self.assertEqual(alarm_level(date(2026,6,3), ref), 'red')
        self.assertEqual(alarm_level(date(2026,7,2), ref), 'yellow')
        self.assertEqual(alarm_level(date(2026,7,3), ref), 'green')
        self.assertEqual(alarm_level(None, ref), 'green')

    def test_parse_date_common_formats(self):
        self.assertEqual(parse_date('01/06/2026'), date(2026,6,1))
        self.assertEqual(parse_date('2026-06-01'), date(2026,6,1))

if __name__=='__main__': unittest.main()
