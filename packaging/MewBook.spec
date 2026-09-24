# -*- mode: python ; coding: utf-8 -*-
#
# Build:  powershell -File packaging\build.ps1   (exe + installer)
#   or:   uv run pyinstaller --noconfirm packaging\MewBook.spec   (exe only)
#
# The product version comes from src/smartdoc/__init__.py (__version__, the
# single source of truth) and is embedded as the exe's Windows version
# resource -- right-click MewBook.exe -> Properties -> Details shows it.
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from importlib.metadata import PackageNotFoundError

from PyInstaller.utils.hooks import collect_data_files, copy_metadata
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)

_ROOT = Path(SPECPATH).parent
_INIT = (_ROOT / 'src' / 'smartdoc' / '__init__.py').read_text(encoding='utf-8')


def _meta(name):
    return re.search(rf'^{name} = "([^"]*)"', _INIT, re.M).group(1)


VERSION = _meta('__version__')
_nums = tuple(int(n) for n in re.match(r'(\d+)\.(\d+)\.(\d+)', VERSION).groups()) + (0,)


def _build_id():
    """The commit this build is made from: its first 12 hex characters, with '-dirty' appended when the working tree had
    uncommitted changes. MEWBOOK_BUILD_ID overrides it (a build from a source archive has no .git). 'dev' when it cannot
    be known. smartdoc/core/build_info.py reads the stamp: only a clean commit is the 'release' channel that may send
    error reports, and the id is what lets a reported error be traced to the exact source (docs/handoff/09, ERR-A14)."""
    override = os.environ.get('MEWBOOK_BUILD_ID', '').strip().lower()
    if re.fullmatch(r'[0-9a-f]{7,40}(-dirty)?', override):
        return override
    try:
        head = subprocess.run(['git', 'rev-parse', '--short=12', 'HEAD'], cwd=_ROOT, capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(['git', 'status', '--porcelain'], cwd=_ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return 'dev'
    if not re.fullmatch(r'[0-9a-f]{7,40}', head):
        return 'dev'
    return head + ('-dirty' if dirty else '')


# Written next to the PyInstaller work files (git-ignored), never into the source tree, and bundled as smartdoc/data/.
_stamp = _ROOT / 'build_pyinstaller' / 'build_info.json'
_stamp.parent.mkdir(parents=True, exist_ok=True)
_stamp.write_text(
    json.dumps({'build_id': _build_id(), 'built_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}),
    encoding='utf-8',
)

version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=_nums, prodvers=_nums, mask=0x3F, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0),
    kids=[
        StringFileInfo([
            StringTable('040904B0', [
                StringStruct('CompanyName', _meta('APP_PUBLISHER')),
                StringStruct('FileDescription', f"{_meta('APP_NAME')} - {_meta('APP_DESCRIPTION')}"),
                StringStruct('FileVersion', VERSION),
                StringStruct('InternalName', 'MewBook'),
                StringStruct('LegalCopyright', _meta('APP_COPYRIGHT')),
                StringStruct('OriginalFilename', 'MewBook.exe'),
                StringStruct('ProductName', f"{_meta('APP_DISPLAY_NAME')} ({_meta('APP_NAME')})"),
                StringStruct('ProductVersion', VERSION),
            ])
        ]),
        VarFileInfo([VarStruct('Translation', [1033, 1200])]),
    ],
)

_datas = [
    ('../src/smartdoc/presentation/assets/app_icon.ico', 'smartdoc/presentation/assets'),
    ('../src/smartdoc/presentation/assets/brand_logo.png', 'smartdoc/presentation/assets'),
    # The mascot pictures + manifest (presentation/brand.py).
    ('../src/smartdoc/presentation/assets/brand/*', 'smartdoc/presentation/assets/brand'),
    # Supabase upgrade SQL, served by Settings -> "Sao chép SQL nâng cấp".
    ('../src/smartdoc/application/sql/*.sql', 'smartdoc/application/sql'),
    # AGPL-3.0-or-later text and the third-party notices travel with every build.
    ('../LICENSE', '.'),
    ('../THIRD_PARTY_NOTICES.md', '.'),
    # The full privacy policy and terms, shown in Help -> About (presentation/about_dialog.py reads them at docs/legal/).
    ('../docs/legal/PRIVACY.md', 'docs/legal'),
    ('../docs/legal/TERMS.md', 'docs/legal'),
    # Which commit this build is (see _build_id above).
    (str(_stamp), 'smartdoc/data'),
]
# Smart classification: the category list and the trained model (train.py
# regenerates classifier_model.json.gz), plus the Vietnamese word segmenter's
# model files (pyvi keeps them as plain data files next to its code).
_datas += [
    ('../src/smartdoc/data/*.json', 'smartdoc/data'),
    ('../src/smartdoc/data/*.json.gz', 'smartdoc/data'),
]
_datas += collect_data_files('pyvi')
# Every redistributed dependency's dist-info (METADATA + licence files), so its licence text ships
# with the exe as THIRD_PARTY_NOTICES.md promises. Names as in THIRD_PARTY_NOTICES.md.
for _dist in ('PySide6', 'PySide6_Essentials', 'PySide6_Addons', 'shiboken6', 'pymupdf', 'mobi', 'pillow',
              'watchdog', 'requests', 'urllib3', 'certifi', 'idna', 'charset-normalizer', 'cryptography',
              'cffi', 'pycparser', 'loguru', 'colorama', 'win32-setctime', 'standard-imghdr', 'pyvi',
              'scikit-learn', 'numpy', 'scipy', 'joblib', 'cloudpickle', 'narwhals', 'threadpoolctl',
              'python-crfsuite', 'sklearn-crfsuite', 'tabulate', 'tqdm'):
    try:
        _datas += copy_metadata(_dist)
    except PackageNotFoundError:
        pass  # an optional/transitive package that this environment does not have
# The donate QR is the author's personal bank code and is not committed
# (.gitignore). Official builds have it on disk and bundle it; a build from a
# clean checkout skips it and the popup shows a text fallback instead.
if (_ROOT / 'src/smartdoc/presentation/assets/donate_qr.png').exists():
    _datas.append(('../src/smartdoc/presentation/assets/donate_qr.png', 'smartdoc/presentation/assets'))

a = Analysis(
    ['../src/smartdoc/app.py'],
    pathex=[],
    binaries=[],
    datas=_datas,
    # pyvi is imported lazily inside the classification worker process, so
    # PyInstaller's static scan may not see its dependency chain.
    hiddenimports=['pyvi.ViTokenizer', 'sklearn_crfsuite', 'pycrfsuite'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='MewBook',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='../src/smartdoc/presentation/assets/app_icon.ico',
    version=version_info,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='MewBook',
)
