# PyInstaller spec for Repeat-Werx (onedir)
# Build: .venv/bin/pip install pyinstaller && .venv/bin/pyinstaller packaging/repeatwerx.spec

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(SPEC)))

a = Analysis(
    [os.path.join(ROOT, "packaging/run.py")],
    pathex=[os.path.join(ROOT, "src")],
    binaries=[],
    datas=[(os.path.join(ROOT, "Images"), "Images")],
    hiddenimports=["repeatwerx.gui.export_dialog",
                   "repeatwerx.gui.import_dialog"],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="repeatwerx",
    console=False,
    icon=os.path.join(ROOT, "Images", "repeatwerx-icon.ico"),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="repeatwerx",
)
