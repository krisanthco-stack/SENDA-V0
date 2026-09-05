import subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT=Path(__file__).parents[1]

class StartupRegressionTests(unittest.TestCase):
    def test_desktop_check_mode_validates_database_and_official_ui_without_display(self):
        with tempfile.TemporaryDirectory() as td:
            cp=subprocess.run([sys.executable,'-m','app.desktop','--check','--data-dir',td],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(cp.returncode,0,cp.stderr)
            self.assertIn('Desktop WebView OK',cp.stdout)
            self.assertTrue((Path(td)/'database'/'senda_v0.sqlite').exists())

    def test_windows_launcher_targets_desktop_exe_and_has_no_external_browser(self):
        bat=(ROOT/'INICIAR_SENDA_V0.bat').read_text('utf-8',errors='replace').lower()
        self.assertIn('senda.v0.exe',bat)
        self.assertIn('pause',bat)
        for forbidden in ('app.launcher','chrome','edge','webbrowser'):
            self.assertNotIn(forbidden,bat)

    def test_legacy_desktop_module_delegates_to_webview_and_has_no_tkinter_ui(self):
        text=(ROOT/'app'/'desktop.py').read_text('utf-8',errors='replace').lower()
        self.assertIn('desktop_webview',text)
        self.assertNotIn('tkinter',text)

    def test_existing_database_is_reopened_not_recreated(self):
        from app.desktop_model import create_context
        with tempfile.TemporaryDirectory() as td:
            ctx=create_context(td);cid=ctx.repo.create_case('4-101-001','HORQUETAS','persistir')
            ctx2=create_context(td)
            self.assertEqual(ctx2.repo.get_case(cid)['note'],'persistir')

if __name__=='__main__':unittest.main()
