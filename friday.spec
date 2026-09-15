# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['main_gui.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets', 'assets'),
        ('.env.example', '.'),
    ],
    hiddenimports=[
        'core', 'config', 'intelligence', 'llm', 'memory', 'skills', 'speech', 'ui', 'utils', 'vision',
        'pydantic', 'SpeechRecognition', 'pyttsx3', 'faster_whisper', 'openwakeword', 'pvporcupine'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='FRIDAY',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False, # GUI app, hide console
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/friday-banner.jpg',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='FRIDAY',
)
