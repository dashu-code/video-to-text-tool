@echo off
setlocal
set "DIR=%~dp0"
if "%DIR:~-1%"=="\" set "DIR=%DIR:~0,-1%"

if "%~1"=="" goto :usage

echo ============================================
echo  Select model tier:
echo    1 = Fast     (tiny,   quick, less accurate)
echo    2 = Standard (small,  balanced)   [default]
echo    3 = Precise  (large,  slow, most accurate)
echo ============================================
set "TIER=2"
set /p "TIER=Enter 1 / 2 / 3 (default 2): "

set "MODEL=m_mid.bin"
set "LABEL=Standard (small)"
if "%TIER%"=="1" set "MODEL=m_fast.bin"
if "%TIER%"=="1" set "LABEL=Fast (tiny)"
if "%TIER%"=="3" set "MODEL=m_large.bin"
if "%TIER%"=="3" set "LABEL=Precise (large)"
echo Tier: %LABEL%

if not exist "%DIR%\%MODEL%" goto :no_model

set "TMPDIR=%TEMP%\whisper_run"
if not exist "%TMPDIR%" mkdir "%TMPDIR%"

echo [1/2] Extracting audio...
"%DIR%\1.exe" -y -i "%~1" -ar 16000 -ac 1 "%DIR%\audio.wav"
if not exist "%DIR%\audio.wav" goto :no_audio

echo [2/2] Recognizing (tier %TIER%)...
copy /Y "%DIR%\%MODEL%" "%TMPDIR%\model.bin" >nul 2>&1
copy /Y "%DIR%\audio.wav" "%TMPDIR%\audio.wav" >nul 2>&1
copy /Y "%DIR%\2.exe" "%TMPDIR%\whisper.exe" >nul 2>&1
copy /Y "%DIR%\whisper.dll" "%TMPDIR%\whisper.dll" >nul 2>&1
copy /Y "%DIR%\ggml.dll" "%TMPDIR%\ggml.dll" >nul 2>&1
copy /Y "%DIR%\ggml-base.dll" "%TMPDIR%\ggml-base.dll" >nul 2>&1
copy /Y "%DIR%\ggml-cpu-haswell.dll" "%TMPDIR%\ggml-cpu-haswell.dll" >nul 2>&1

cd /d "%TMPDIR%"
whisper.exe -m model.bin -f audio.wav -l zh -t 8 -osrt -oj -of transcript

if not exist "%TMPDIR%\transcript.srt" goto :no_srt
copy /Y "%TMPDIR%\transcript.srt" "%DIR%\transcript.srt" >nul 2>&1
copy /Y "%TMPDIR%\transcript.json" "%DIR%\transcript.json" >nul 2>&1
cd /d "%DIR%"
echo.
echo Done. transcript.srt is in the toolkit folder.
goto :end

:no_model
echo.
echo ERROR: model file "%MODEL%" not found in this folder.
echo Run get_models.bat first and download the matching tier:
echo   tier 1 -^> m_fast.bin    tier 2 -^> m_mid.bin    tier 3 -^> m_large.bin
goto :end

:no_audio
echo.
echo ERROR: audio extraction failed. Is the input file a valid video/audio?
echo Check that 1.exe (ffmpeg) is present; run get_models.bat if not.
goto :end

:no_srt
cd /d "%DIR%"
echo.
echo ERROR: transcript.srt was NOT produced. See the message above.
goto :end

:usage
echo Usage: drag a video or audio file onto this bat.
goto :end

:end
echo.
pause
