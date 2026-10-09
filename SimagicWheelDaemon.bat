@echo off
title Simagic Wheel Daemon
cd /d "%~dp0"
echo Starting Simagic Wheel Daemon in Windows System Tray...
start "" pythonw "%~dp0SimagicWheelDaemon.pyw"
echo Daemon launched in background. Check your Windows System Tray (notification area).
timeout /t 3 >nul
exit
