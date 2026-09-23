@echo off
title UrbanNuna - Visor SENAMHI Google Flood Hub
cd /d "%~dp0"
echo ============================================================
echo   Iniciando Visor UrbanNuna (Google Flood Hub - SENAMHI)
echo ============================================================
echo.
echo Directorio de trabajo: %CD%
echo Abriendo Google Chrome en http://localhost:8505 ...
start "" http://localhost:8505
echo.
echo Iniciando servidor Streamlit en puerto 8505...
python run_server.py
pause
