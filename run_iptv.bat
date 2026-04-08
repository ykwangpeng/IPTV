@echo off
set PATH=C:\tools\ffmpeg\ffmpeg-7.1-essentials_build\bin;%PATH%
set GIST_TOKEN=YOUR_GIST_TOKEN_HERE
set HTTP_PROXY=http://127.0.0.1:3067
set HTTPS_PROXY=http://127.0.0.1:3067
cd /d C:\tools\IPTV
echo [%date% %time%] === IPTV Check Started === >> run.log
python IPTV-Apex-dzh.py -w 80 -t 5 >> run.log 2>&1
echo [%date% %time%] IPTV Check done, Exit: %errorlevel% >> run.log
python scripts\post_process.py >> run.log 2>&1
python scripts\sync_to_gist.py >> run.log 2>&1
echo [%date% %time%] === IPTV Check Finished === >> run.log