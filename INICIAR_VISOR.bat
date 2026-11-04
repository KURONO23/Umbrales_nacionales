@echo off
setlocal
title ARES Nacional - Visor SENAMHI Google Flood Hub
cd /d "%~dp0"

echo ============================================================
echo   Iniciando ARES Nacional (Google Flood Hub - SENAMHI)
echo ============================================================
echo.
echo Directorio de trabajo: %CD%

:: Detectar interprete de Python (priorizando el entorno virtual .venv local)
set "PY="
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PY=%~dp0.venv\Scripts\python.exe"
) else if exist "C:\Users\mgutierrez\AppData\Local\Programs\Python\Python312\python.exe" (
    set "PY=C:\Users\mgutierrez\AppData\Local\Programs\Python\Python312\python.exe"
) else (
    set "PY=python"
)

echo Interprete detectado: %PY%
echo Abriendo Google Chrome en http://localhost:8505 ...
start "" http://localhost:8505
echo.
echo Iniciando servidor Streamlit en puerto 8505...
"%PY%" -m streamlit run app.py --server.port 8505 --server.headless true

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] No se pudo iniciar el visor. Verifique que Python y las dependencias esten disponibles.
    pause
)
endlocal
