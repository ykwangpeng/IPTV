@echo off
chcp 65001 >nul 2>&1
setlocal

:: Load environment variables (GIST_TOKEN, GIST_ID, etc.)
if exist env_config.bat (
    call env_config.bat
)

:: Python path
set PYTHON=C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe

:: Run IPTV checker
%PYTHON% run_iptv.py -w 20 -t 10 --no-speed-check --async-crawl

:: Generate M3U
if exist live_ok.txt (
    %PYTHON% scripts\generate_m3u.py
)

:: Sync to GitHub/Gist
if exist live_ok.txt (
    %PYTHON% scripts\sync_to_gist.py
)

endlocal
