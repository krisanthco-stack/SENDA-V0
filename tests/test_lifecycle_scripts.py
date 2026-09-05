import unittest
from pathlib import Path

ROOT=Path(__file__).parents[1]

class LifecycleScriptTests(unittest.TestCase):
    def test_batch_entrypoints_exist_and_pause_on_error(self):
        for name,ps in (
            ('INSTALAR_SENDA_V0.bat','install_desktop.ps1'),
            ('ACTUALIZAR_SENDA_V0.bat','update_desktop.ps1'),
            ('DESINSTALAR_SENDA_V0.bat','uninstall_desktop.ps1'),
        ):
            p=ROOT/name; self.assertTrue(p.is_file(),name)
            text=p.read_text('utf-8',errors='replace').lower()
            self.assertIn(ps.lower(),text)
            self.assertIn('errorlevel',text)
            self.assertIn('pause',text)

    def test_install_and_update_keep_user_data_outside_application(self):
        install=(ROOT/'scripts'/'install_desktop.ps1').read_text('utf-8',errors='replace').lower()
        update=(ROOT/'scripts'/'update_desktop.ps1').read_text('utf-8',errors='replace').lower()
        for text in (install,update):
            self.assertIn("programs\\senda.v0",text)
            self.assertIn("join-path $env:localappdata 'senda.v0'",text)
            self.assertIn('senda.v0.exe',text)
        self.assertIn('datos protegidos',update)
        self.assertNotIn('remove-item $dataroot',update)

    def test_installer_checks_desktop_exe_before_shortcut(self):
        install=(ROOT/'scripts'/'install_desktop.ps1').read_text('utf-8',errors='replace').lower()
        self.assertIn('& $targetexe --check',install)
        self.assertIn('new-sendashortcut',install)
        self.assertLess(install.index('& $targetexe --check'), install.index('new-sendashortcut (join-path $desktop'))
        self.assertNotIn('127.0.0.1',install)
        self.assertNotIn('python.org',install)
        self.assertNotIn('winget',install)

    def test_uninstall_defaults_to_preserve_data_and_requires_explicit_delete(self):
        text=(ROOT/'scripts'/'uninstall_desktop.ps1').read_text('utf-8',errors='replace').lower()
        self.assertIn('conservar',text);self.assertIn('eliminar',text);self.assertIn("$choice -eq '2'",text)
        self.assertIn("-ceq 'eliminar'",text)

    def test_maintenance_menu_exposes_install_update_uninstall(self):
        text=(ROOT/'MANTENIMIENTO_SENDA_V0.bat').read_text('utf-8',errors='replace').lower()
        for word in ('instalar','actualizar','desinstalar'):self.assertIn(word,text)


    def test_repository_can_download_and_extract_latest_installer_without_installing(self):
        bat=ROOT/'EXTRAER_INSTALADOR_GITHUB.bat'
        ps=ROOT/'scripts'/'extract_installer_from_github.ps1'
        self.assertTrue(bat.is_file())
        self.assertTrue(ps.is_file())
        batch=bat.read_text('utf-8',errors='replace').lower()
        script=ps.read_text('utf-8',errors='replace').lower()
        self.assertIn('extract_installer_from_github.ps1',batch)
        self.assertIn('releases/latest',script)
        self.assertIn(r'senda\.v0_.*_windows_desktop\.zip',script)
        self.assertIn('expand-archive',script)
        self.assertIn('instalar_senda_v0.bat',script)
        self.assertNotIn('& $installer',script)
        self.assertNotIn('start-process',script)

class OfflineDependencyTests(unittest.TestCase):
    def test_github_build_creates_windows_desktop_exe(self):
        text=(ROOT/'.github'/'workflows'/'build-windows-desktop.yml').read_text('utf-8',errors='replace').lower()
        self.assertIn('windows-latest',text)
        self.assertIn('pyinstaller',text)
        self.assertIn('--windowed',text)
        self.assertIn('--name senda.v0',text)
        self.assertIn('xlrd',text)
        self.assertIn('7z.exe',text)
        self.assertIn('asset = "senda.v0_${version}_windows_desktop.zip"',text)

if __name__=='__main__':unittest.main()
