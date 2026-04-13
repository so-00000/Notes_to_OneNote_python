@echo off
setlocal

start "" cmd /k ^
"cd /d "%~dp0" ^
&& echo [%date% %time%] Starting python -m main.main ^
&& python -m main.main ^
&& echo [%date% %time%] Finished python -m main.main with exit code %ERRORLEVEL%"