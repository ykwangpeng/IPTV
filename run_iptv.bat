@echo off
chcp 65001 >nul 2>&1
setlocal

:: Python path
set PYTHON=C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe

:: Run IPTV checker
%PYTHON% run_iptv.py -w 80 -t 8 --no-speed-check

:: Generate M3U
if exist live_ok.txt (
    %PYTHON% scripts\generate_m3u.py
)

:: Sync to GitHub/Gist
if exist live_ok.txt (
    %PYTHON% scripts\sync_to_gist.py
)

endlocal
