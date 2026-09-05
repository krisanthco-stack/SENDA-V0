import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]


class GitHubPagesContractTests(unittest.TestCase):
    def test_repository_root_has_pages_entrypoint(self):
        index = ROOT / 'index.html'
        self.assertTrue(index.is_file(), 'GitHub Pages necesita index.html en la raíz del repositorio')
        html = index.read_text('utf-8').lower()
        self.assertIn('./ui/', html)
        self.assertNotIn('# senda.v0', html)

    def test_jekyll_is_disabled_for_static_application(self):
        self.assertTrue((ROOT / '.nojekyll').is_file())

    def test_pages_preview_does_not_call_nonexistent_github_api(self):
        js = (ROOT / 'ui' / 'app.js').read_text('utf-8')
        self.assertIn('isGitHubPages', js)
        self.assertIn('Vista web', js)
        self.assertIn('INICIAR_SENDA_V0.bat', js)


if __name__ == '__main__':
    unittest.main()
