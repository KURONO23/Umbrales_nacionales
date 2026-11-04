@echo off
setlocal

cd /d "%~dp0"

set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" (
    set "PY=python"
)

echo [%date% %time%] Iniciando cron_diario.py...
"%PY%" "%~dp0cron_diario.py" %*

set "EXIT_CODE=%errorlevel%"
if %EXIT_CODE% EQU 0 (
    echo [%date% %time%] [EXITO] Proceso finalizado correctamente.
) else (
    echo [%date% %time%] [ERROR] Fallo en la sincronizacion. Codigo: %EXIT_CODE%
)

exit /b %EXIT_CODE%
