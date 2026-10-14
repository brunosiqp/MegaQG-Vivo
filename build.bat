@echo off
REM Compila sempre dentro do ambiente virtual .venv (so com o requirements.txt).
REM Isso deixa o exe pequeno e usa um PyInstaller que empacota o Tcl/Tk 9 do Python 3.14
REM (com o PyInstaller antigo/global o exe abria com erro "_tcl_data not found").
cd /d "%~dp0"
echo ============================================
echo   Compilando MegaQG Vivo
echo ============================================
echo.

if not exist .venv\Scripts\python.exe (
    echo [1/4] Criando ambiente virtual .venv...
    python -m venv .venv
)

echo [2/4] Instalando dependencias no .venv...
.venv\Scripts\python -m pip install -q -r requirements.txt "pyinstaller>=6.22.3"

echo.
echo [3/4] Compilando main.py em um unico .exe...
.venv\Scripts\python -m PyInstaller --noconfirm --clean MegaQGVivo.spec

REM O config.json local e embutido no exe pelo MegaQGVivo.spec.
if not exist config.json (
    echo.
    echo   ATENCAO: sem config.json - o exe vai precisar de um config.json ao lado dele.
)

echo.
echo [4/4] Montando o pacote de implantacao (pasta e zip em dist)...
.venv\Scripts\python tools\empacotar_deploy.py

echo.
echo ============================================
echo   Concluido! Executavel em: dist\MegaQGVivo.exe
echo ============================================
pause
