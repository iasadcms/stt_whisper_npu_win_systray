# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('.', '.')],
    hiddenimports=['PIL', 'PIL.Image', 'PIL.ImageDraw', 'PIL.ImageEnhance', 'pyautogui', 'pyaudio', 'whisper', 'numpy', 'wave', 'openai', 'pynput', 'pynput.keyboard', 'pynput._util', 'pygame', 'pygame._view', 'win32gui', 'win32con', 'win32api'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],  # Removed exclusions that were causing issues with hotkeys and animations
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
    name='stt_whisper_npu_win_systray',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=True,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
