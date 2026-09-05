import tempfile, unittest
from pathlib import Path
from app.repository import Repository

class CaseTests(unittest.TestCase):
    def setUp(self):self.td=tempfile.TemporaryDirectory();self.repo=Repository(Path(self.td.name)/'db.sqlite')
    def tearDown(self):self.td.cleanup()
    def test_create_and_search_case(self):
        cid=self.repo.create_case('4-200103-001','Horquetas','Revisar gravamen','PENDIENTE')
        rows=self.repo.list_cases('200103')
        self.assertEqual(rows[0]['id'],cid);self.assertEqual(rows[0]['distrito'],'HORQUETAS');self.assertEqual(rows[0]['status'],'INFORMACION')

if __name__=='__main__':unittest.main()
