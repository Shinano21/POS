# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['E:\\Projects\\POS\\Separate\\login.py'],
    pathex=[],
    binaries=[],
    datas=[('E:\\Projects\\POS\\dist\\images', 'images'), ('E:\\Projects\\POS\\Separate\\login.py', '.'), ('E:\\Projects\\POS\\Separate\\inventory.py', '.'), ('E:\\Projects\\POS\\Separate\\transactions.py', '.'), ('E:\\Projects\\POS\\Separate\\sales_summary.py', '.'), ('E:\\Projects\\POS\\Separate\\dashboard.py', '.')],
    hiddenimports=[],
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
    a.binaries,
    a.datas,
    [],
    name='Gems_POS',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['E:\\Projects\\POS\\dist\\images\\shinano.ico'],
)
