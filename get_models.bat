@echo off
setlocal enabledelayedexpansion
set "DIR=%~dp0"
if "%DIR:~-1%"=="\" set "DIR=%DIR:~0,-1%"

echo ============================================
echo  Whisper models + ffmpeg downloader
echo ============================================
echo  Choose what to download:
echo    1 = tiny only    ~41 MB   quick smoke test
echo    2 = small only   ~252 MB  recommended for daily use
echo    3 = tiny+small   ~293 MB  [default]
echo    4 = all          ~3.2 GB  includes large-v3, may take hours
echo    5 = large only   ~2.9 GB
echo    0 = skip models, just get ffmpeg
echo ============================================
set "PICK=3"
set /p "PICK=Enter 1 / 2 / 3 / 4 / 5 / 0 (default 3): "

set "WANT_TINY=0"
set "WANT_SMALL=0"
set "WANT_LARGE=0"
if "%PICK%"=="1" set "WANT_TINY=1"
if "%PICK%"=="2" set "WANT_SMALL=1"
if "%PICK%"=="3" set "WANT_TINY=1" & set "WANT_SMALL=1"
if "%PICK%"=="4" set "WANT_TINY=1" & set "WANT_SMALL=1" & set "WANT_LARGE=1"
if "%PICK%"=="5" set "WANT_LARGE=1"

echo.
echo Plan: tiny=%WANT_TINY%  small=%WANT_SMALL%  large=%WANT_LARGE%
echo Downloads resume automatically; re-run this script anytime.
echo.

set "BASE=https://hf-mirror.com/ggerganov/whisper.cpp/resolve/main"

if "%WANT_TINY%"=="1" goto :dl_tiny
goto :chk_small

:dl_tiny
echo [model] tiny ~41 MB ...
curl -L -C - --retry 3 --retry-delay 3 -o "%DIR%\m_fast.bin" "%BASE%/ggml-tiny-q8_0.bin"
if not exist "%DIR%\m_fast.bin" echo   WARNING: tiny download failed, re-run to retry.

:chk_small
if "%WANT_SMALL%"=="1" goto :dl_small
goto :chk_large

:dl_small
echo [model] small ~252 MB ...
curl -L -C - --retry 3 --retry-delay 3 -o "%DIR%\m_mid.bin" "%BASE%/ggml-small-q8_0.bin"
if not exist "%DIR%\m_mid.bin" echo   WARNING: small download failed, re-run to retry.

:chk_large
if "%WANT_LARGE%"=="1" goto :dl_large
goto :chk_ffmpeg

:dl_large
echo [model] large-v3 ~2.9 GB, this takes a long time ...
curl -L -C - --retry 3 --retry-delay 5 -o "%DIR%\m_large.bin" "%BASE%/ggml-large-v3.bin"
if not exist "%DIR%\m_large.bin" echo   WARNING: large download failed, re-run to retry.

:chk_ffmpeg
if exist "%DIR%\1.exe" goto :ffmpeg_ok
goto :dl_ffmpeg

:ffmpeg_ok
echo.
echo [ffmpeg] 1.exe already present, skipping.
goto :summary

:dl_ffmpeg
echo.
echo [ffmpeg] downloading audio extractor ~110-190 MB ...
if exist "%DIR%\ffmpeg-master-latest-win64-gpl" rd /s /q "%DIR%\ffmpeg-master-latest-win64-gpl" >nul 2>&1

curl -L -C - --retry 3 --retry-delay 3 -o "%DIR%\ffmpeg.zip" "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
if %ERRORLEVEL% NEQ 0 echo   Primary source failed, trying mirror ...
if %ERRORLEVEL% NEQ 0 curl -L -C - --retry 3 --retry-delay 3 -o "%DIR%\ffmpeg.zip" "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

if not exist "%DIR%\ffmpeg.zip" goto :ffmpeg_fail
for %%A in ("%DIR%\ffmpeg.zip") do set "FSIZE=%%~zA"
if not defined FSIZE goto :ffmpeg_fail
if !FSIZE! LSS 100000 goto :ffmpeg_fail

echo   extracting with tar ...
tar -xf "%DIR%\ffmpeg.zip" -C "%DIR%"
if exist "%DIR%\ffmpeg-master-latest-win64-gpl\bin\ffmpeg.exe" goto :ffmpeg_btbn

for /d %%D in ("%DIR%\ffmpeg-*") do call :take_bin "%%D"
goto :ffmpeg_cleanup

:ffmpeg_btbn
copy /Y "%DIR%\ffmpeg-master-latest-win64-gpl\bin\*" "%DIR%\" >nul 2>&1
ren "%DIR%\ffmpeg.exe" "1.exe"

:ffmpeg_cleanup
for /d %%D in ("%DIR%\ffmpeg-*") do rd /s /q "%%D" >nul 2>&1
del /q "%DIR%\ffmpeg.zip" >nul 2>&1
if exist "%DIR%\1.exe" echo   ffmpeg OK.
if not exist "%DIR%\1.exe" echo   ERROR: ffmpeg.exe not found after extracting.
goto :summary

:take_bin
if exist "%~1\bin\ffmpeg.exe" (
  copy /Y "%~1\bin\*" "%DIR%\" >nul 2>&1
  ren "%DIR%\ffmpeg.exe" "1.exe"
)
goto :eof

:ffmpeg_fail
echo   ERROR: ffmpeg download incomplete or corrupted.
echo   Delete ffmpeg.zip and re-run this script.

:summary
echo.
echo ============================================
echo  Summary:
for %%M in (m_fast.bin m_mid.bin m_large.bin 1.exe) do call :report "%DIR%\%%M" "%%M"
echo ============================================
echo.
echo Next step:
echo   Drag any video/audio file onto 4.bat    (command line version)
echo   or run: python desktop-app\app.py        (GUI version)
echo.
echo Anything missing? Re-run this script - it resumes where it left off.
echo.
pause
goto :eof

:report
if exist "%~1" (
  for %%A in ("%~1") do echo   [OK]      %~2   %%~zA bytes
) else (
  echo   [MISSING] %~2
)
goto :eof
