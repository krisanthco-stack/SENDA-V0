from pathlib import Path
import re
import tomllib

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github' / 'workflows' / 'build-windows-desktop.yml'


def test_only_one_windows_release_workflow_remains():
    assert not (ROOT / '.github' / 'workflows' / 'build-windows.yml').exists()
    assert WORKFLOW.is_file()


def test_workflow_uses_node24_generation_actions():
    text = WORKFLOW.read_text(encoding='utf-8')
    assert 'actions/checkout@v7' in text
    assert 'actions/setup-python@v7' in text
    assert 'actions/upload-artifact@v7' in text


def test_workflow_derives_release_version_from_pyproject_once():
    text = WORKFLOW.read_text(encoding='utf-8')
    assert 'tomllib' in text
    assert 'pyproject.toml' in text
    assert 'SENDA_VERSION' in text
    # Packaging/release names must be composed from the resolved version,
    # not from copied literal release-version strings spread through the workflow.
    assert text.count('0.4.3') == 0


def test_release_tag_check_does_not_fail_when_tag_or_release_is_missing():
    text = WORKFLOW.read_text(encoding='utf-8')
    assert 'git ls-remote --tags origin' in text
    assert 'gh release list' in text
    assert 'git rev-parse' not in text
    assert 'gh release view' not in text


def test_workflow_rejects_existing_tag_pointing_at_another_commit():
    text = WORKFLOW.read_text(encoding='utf-8')
    assert 'existingTagSha' in text
    assert 'GITHUB_SHA' in text
    assert 'apunta a otro commit' in text


def test_archive_is_validated_before_upload_and_release():
    text = WORKFLOW.read_text(encoding='utf-8')
    verify_pos = text.index('Verify release package')
    upload_pos = text.index('Upload Windows Desktop artifact')
    publish_pos = text.index('Publish installable GitHub Release')
    assert verify_pos < upload_pos < publish_pos
    for item in (
        'SENDA.V0.exe',
        'scripts/install_desktop.ps1',
        'scripts/install_from_github.ps1',
        'INSTALAR_DESDE_GITHUB.bat',
        'scripts/extract_installer_from_github.ps1',
        'EXTRAER_INSTALADOR_GITHUB.bat',
    ):
        assert item in text


def test_actions_artifact_download_is_directly_extractable_installer_folder():
    text = WORKFLOW.read_text(encoding='utf-8')
    upload = text[text.index('Upload Windows Desktop artifact'):text.index('Publish installable GitHub Release')]
    assert 'path: release/SENDA.V0' in upload
    assert 'path: ${{ steps.meta.outputs.asset }}' not in upload


def test_runtime_version_markers_match_pyproject():
    with (ROOT / 'pyproject.toml').open('rb') as fh:
        version = tomllib.load(fh)['project']['version']
    assert (ROOT / 'app' / '__init__.py').read_text(encoding='utf-8').strip() == f"__version__ = '{version}'"
    assert f'SENDA.V0 {version}' in (ROOT / 'scripts' / 'install_desktop.ps1').read_text(encoding='utf-8')
    assert f'SENDA.V0 {version}' in (ROOT / 'MANTENIMIENTO_SENDA_V0.bat').read_text(encoding='utf-8')
