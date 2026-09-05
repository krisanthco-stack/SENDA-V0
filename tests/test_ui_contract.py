import unittest
from pathlib import Path

class UiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root=Path(__file__).parents[1]
        cls.html=(root/'ui'/'index.html').read_text('utf-8')
        cls.js=(root/'ui'/'app.js').read_text('utf-8')
    def test_exactly_four_primary_modules_in_approved_order(self):
        self.assertEqual(self.html.count('data-module='),4)
        order=[self.html.index(x) for x in ('>INICIO<','>INFORMACIÓN SENDA<','>CONTROL<','>GESTIÓN<')]
        self.assertEqual(order,sorted(order))
    def test_information_has_movement_quickbar_and_page_sizes(self):
        for label in ('TODOS','FINCAS','HIPOTECAS','GRAVÁMENES','SEGREGACIONES','ANOTACIONES','HISTÓRICOS','CERRADAS','OTROS'):self.assertIn(label,self.html)
        self.assertIn('id="infoPageSize"',self.html)
        for n in ('25','50','100'):self.assertIn(f'value="{n}"',self.html)
    def test_control_finalize_button_is_in_control_and_disabled_initially(self):
        self.assertIn('id="controlFinalize"',self.html);self.assertIn('disabled',self.html)
        control=self.html[self.html.index('data-view="control"'):self.html.index('data-view="gestion"')]
        self.assertIn('FINALIZAR',control)
    def test_manual_case_creation_is_in_information(self):
        info=self.html[self.html.index('data-view="informacion"'):self.html.index('data-view="control"')]
        for field in ('manualFolio','manualPlano','manualDistrict','manualCaseCreate'):self.assertIn(field,info)
    def test_filters_and_real_formats_remain(self):
        for control in ('filterYear','filterQuarter','filterMonth','filterDistrict','filterAlarm'):self.assertIn(f'id="{control}"',self.html)
        for ext in ('.xls','.xlsx','.csv','.json','.txt','.zip','.rar'):self.assertIn(ext,self.html.lower())
    def test_previous_alarm_rules_remain(self):self.assertIn('90 días',self.html);self.assertIn('60 días',self.html)
    def test_right_context_sections_remain(self):
        for label in ('INFORMACIÓN SENDA','FOLIOS / FINCAS PENDIENTES','ALARMAS','CÓDIGOS','LEYENDA DE ESTADO'):self.assertIn(label,self.html)

if __name__=='__main__':unittest.main()
