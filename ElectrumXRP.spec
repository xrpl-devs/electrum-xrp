# Build on the target operating system: python -m PyInstaller ElectrumXRP.spec
from PyInstaller.utils.hooks import collect_submodules, collect_data_files, copy_metadata

a = Analysis(
    ['run_wallet.py'],
    pathex=[],
    binaries=[],
    datas=copy_metadata('xrpl-py') + collect_data_files('xrpl'),
    hiddenimports=collect_submodules('xrpl'),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'tkinter'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name='ElectrumXRP',
    debug=False,
    strip=False,
    upx=False,
    console=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='ElectrumXRP')
