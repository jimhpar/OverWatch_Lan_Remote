# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['launcher.py'],
    pathex=[],
    binaries=[],
    datas=[('app_icon.ico', '.'), ('style.qss', '.'), ('config.py', '.'), ('protocol.py', '.'), ('master_dashboard.py', '.'), ('employee_client.py', '.'), ('logo', 'logo')],
    hiddenimports=['websockets', 'websockets.exceptions', 'mss', 'cv2', 'numpy', 'pynput', 'pynput.mouse', 'pynput.keyboard', 'master_dashboard', 'employee_client'],
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
    name='Overwatch',
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
    icon=['app_icon.ico'],
)
