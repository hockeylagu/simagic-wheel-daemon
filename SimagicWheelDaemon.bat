@echo off
title Simagic Wheel Daemon
cd /d "%~dp0"
echo Starting Simagic Wheel Daemon in Windows System Tray...
start "" pythonw -m simagic_daemon.tray
echo Daemon launched in background. Check your Windows System Tray (notification area).
timeout /t 3 >nul
exit
