@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

title Actualización Diaria ARES & GFS - SENAMHI

echo ======================================================================
echo    SENAMHI - DIRECCIÓN DE HIDROLOGÍA
echo    Sincronizador Automatizado de Pronósticos ARES y GFS
echo ======================================================================
echo.

cd /d "%~dp0"

set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"

if not exist "!PYTHON_EXE!" (
    echo [ERROR] No se encontró el entorno virtual en !PYTHON_EXE!
    echo Utilizando python del sistema...
    set "PYTHON_EXE=python"
)

echo [%date% %time%] Iniciando cron_diario.py...
"!PYTHON_EXE!" "%~dp0cron_diario.py" %*

set EXIT_CODE=%ERRORLEVEL%

if %EXIT_CODE% EQU 0 (
    echo.
    echo [%date% %time%] [EXITO] Proceso finalizado correctamente.
) else (
    echo.
    echo [%date% %time%] [ERROR] Ocurrió un problema durante la sincronización (Código: %EXIT_CODE%).
)

exit /b %EXIT_CODE%
