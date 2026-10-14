# -*- mode: python ; coding: utf-8 -*-
# Compilar com build.bat (usa o .venv).
# Se existir config.json na raiz (fora do git), ele é EMBUTIDO no exe, para o exe
# rodar sozinho no servidor. Um config.json ao lado do exe tem prioridade.
import os

from PyInstaller.utils.hooks import collect_submodules

datas = [('assets/megaqg_vivo.ico', 'assets'), ('assets/pikachu_logo.png', 'assets'),
         # visão para o cliente: logo e ícone da Vivo no lugar do Pikachu
         ('assets/vivo_logo.png', 'assets'), ('assets/vivo.ico', 'assets'),
         # Pokémon: as animações (andar, golpe, pulo), os dados delas e os créditos (licença CC BY-NC 4.0)
         ('assets/pokemon/*.png', 'assets/pokemon'), ('assets/pokemon/animacoes.json', 'assets/pokemon'),
         ('assets/pokemon/CREDITOS.md', 'assets/pokemon')]
if os.path.exists('config.json'):
    datas.append(('config.json', '.'))
else:
    print('AVISO: config.json nao encontrado - o exe vai precisar de um config.json ao lado dele.')


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    # As telas são importadas pelo nome (modulos/registro.py), então o PyInstaller
    # não as encontra sozinho: inclui todos os submódulos explicitamente.
    hiddenimports=['openpyxl'] + collect_submodules('modulos'),
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
    name='MegaQGVivo',
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
    icon=['assets/megaqg_vivo.ico'],
)
