# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['校对工具整合版v1.7.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('subjects', 'subjects'),
        ('templates', 'templates'),
    ],
    hiddenimports=[
        'sympy', 'sympy_tools', 'sympy_tools.tools', 'sympy_tools.templates',
        'sympy_tools.sandbox', 'sympy_tools.safety',
        'web_tools', 'latex_generator', 'pdf_compiler',
        'pydantic', 'langchain_core', 'langchain_core.tools',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tests', 'pytest'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='校对工具v1.7',
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
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='校对工具v1.7',
)
