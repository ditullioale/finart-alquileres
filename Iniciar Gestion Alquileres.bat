@echo off
title Gestion de Alquileres
cd /d "%~dp0"

REM Abre el navegador a los 3 segundos (cuando el servidor ya levanto)
start "" cmd /c "timeout /t 3 >nul & start http://localhost:5000"

echo ============================================================
echo   Gestion de Alquileres esta corriendo.
echo   Se abrio en el navegador: http://localhost:5000
echo   Desde otra PC de la red:  http://192.168.100.11:5000
echo.
echo   Para CERRAR el programa: cerra esta ventana (o Ctrl+C).
echo ============================================================
echo.

REM Usa el Python instalado en el sistema (el mismo que en VS)
where python >nul 2>&1
if %errorlevel%==0 (
  python run.py
) else (
  py run.py
)

pause
