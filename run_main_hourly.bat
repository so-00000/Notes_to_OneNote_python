@echo off
setlocal

cd /d "%~dp0"

set "LOG_DIR=%~dp0logs\task_scheduler"
set "LOG_FILE=%LOG_DIR%\run_main_hourly.log"
set "STATUS_FILE=%LOG_DIR%\run_main_hourly.status.txt"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

(
  echo status=RUNNING
  echo started_at=%date% %time%
  echo working_dir=%cd%
  echo log_file=%LOG_FILE%
) > "%STATUS_FILE%"

>> "%LOG_FILE%" echo ==================================================
>> "%LOG_FILE%" echo [%date% %time%] START python -m main.main
>> "%LOG_FILE%" echo [%date% %time%] WORKDIR %cd%

python -m main.main >> "%LOG_FILE%" 2>&1
set "EXIT_CODE=%ERRORLEVEL%"

>> "%LOG_FILE%" echo [%date% %time%] END python -m main.main exit_code=%EXIT_CODE%
>> "%LOG_FILE%" echo.

(
  if "%EXIT_CODE%"=="0" (
    echo status=SUCCESS
  ) else (
    echo status=FAILED
  )
  echo finished_at=%date% %time%
  echo exit_code=%EXIT_CODE%
  echo log_file=%LOG_FILE%
) > "%STATUS_FILE%"

exit /b %EXIT_CODE%
