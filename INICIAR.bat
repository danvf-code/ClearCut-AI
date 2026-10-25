@echo off
title ClearCut AI
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
    echo No se encontro Python. Instala Python 3.11 o 3.12 desde https://www.python.org/downloads/
    echo Marca la casilla "Add Python to PATH" durante la instalacion.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creando entorno virtual...
    py -3.12 -m venv .venv
    if errorlevel 1 py -3.11 -m venv .venv
    if errorlevel 1 (
        echo No se pudo crear el entorno virtual. Instala Python 3.11 o 3.12.
        pause
        exit /b 1
    )
)

set PY=".venv\Scripts\python.exe"

%PY% -c "import rembg, customtkinter, onnxruntime" >nul 2>nul
if errorlevel 1 (
    echo Instalando dependencias. Esto puede tardar varios minutos...
    %PY% -m pip install --upgrade pip
    %PY% -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo ERROR instalando dependencias. Revisa los mensajes de arriba.
        echo Necesitas Python 3.11 o 3.12 ^(no 3.13 o superior^).
        pause
        exit /b 1
    )
    %PY% -c "import rembg, customtkinter, onnxruntime" >nul 2>nul
    if errorlevel 1 (
        echo.
        echo rembg sigue sin instalarse. Borra la carpeta .venv e intenta de nuevo.
        pause
        exit /b 1
    )
)

%PY% app.py
if errorlevel 1 pause
