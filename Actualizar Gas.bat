@echo off
REM ===== Actualizar el control de gas =====
REM Doble clic en este archivo para leer Litoral Gas y actualizar la app.
cd /d "%~dp0"
call venv\Scripts\activate.bat
python litoralgas_bot.py
echo.
echo ================================================
echo  Listo. Podes cerrar esta ventana.
echo ================================================
pause
