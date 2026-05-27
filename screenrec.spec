# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[],
    hiddenimports=[
        'ffmpeg_probe',
        'recorder',
        'capture',
        'audio',
        'hotkeys',
        'utils',
        'ui',
        'ui.app_window',
        'ui.styles',
        'mss',
        'mss.windows',
        'numpy',
        'cv2',
        'sounddevice',
        'PIL',
        'PIL.Image',
        'keyboard',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ScreenRec',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    onefile=True,
)
