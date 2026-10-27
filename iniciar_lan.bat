@echo off
rem Arranca Hadoop Battle Arena en este equipo para jugar por red local (LAN).
rem Crea el entorno virtual la primera vez, instala dependencias y muestra la direccion para compartir.
cd /d "%~dp0"
title Hadoop Battle Arena

where python >nul 2>nul
if errorlevel 1 (
  echo No se encontro Python. Instala Python 3.10 o superior desde https://www.python.org/downloads/
  echo y marca la casilla "Add Python to PATH".
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creando entorno virtual...
  python -m venv .venv || goto :error
)
echo Instalando dependencias...
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt || goto :error

if not exist ".env" (
  echo.
  set /p HOST_PIN=PIN del anfitrion [Enter = 1234]:
)

echo.
echo Comparte con los jugadores la direccion "En la red local" que aparece abajo.
echo Si no pueden entrar, abre el puerto en el Firewall de Windows (ver README, seccion LAN).
echo Para detener el servidor cierra esta ventana o pulsa Ctrl+C.
".venv\Scripts\python.exe" app.py
pause
exit /b 0

:error
echo.
echo Ocurrio un error. Revisa los mensajes anteriores.
pause
exit /b 1
