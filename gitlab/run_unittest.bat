tscon 0 /dest:console
tscon 1 /dest:console
tscon 2 /dest:console
tscon 3 /dest:console
tscon 4 /dest:console
tscon 5 /dest:console

set ERROR=0
set CURRENT_DIR=%~dp0

REM Detect nasty cases where the working copy is not correctly updated
git log -n 1
echo %CI_COMMIT_SHA%
set GIT=git log -n 1 --oneline --no-abbrev-commit         
for /f "tokens=1 USEBACKQ" %%F in (`%GIT%`) do (set COMMIT_SHA=%%F)
if %COMMIT_SHA% NEQ %CI_COMMIT_SHA% (exit /B 1)

SET

REM create local folders if required
if not exist %CURRENT_DIR%\blender mkdir %CURRENT_DIR%\blender
set CACHE=%CURRENT_DIR%\blender\cache
if not exist %CACHE% mkdir %CACHE%

REM remove old blender install if it exists
RD /S /Q %CURRENT_DIR%\blender\%MIXER_BLENDER_ZIP_BASENAME%

IF %MIXER_BLENDER_DOWNLOAD% == "release" GOTO DOWNLOADZIP
REM Download from builder: always cleanup, files are never reusable
REM - Beta file changes event if name does not
REM - Alpha file has hash in name
RMDIR /S /Q %CACHE%\%MIXER_BLENDER_ZIP_BASENAME%
DEL %CACHE%\%MIXER_BLENDER_ZIP_BASENAME%.zip

:DOWNLOADZIP
REM if unzipped folder already exists in cache folder, just copy it
IF EXIST %CACHE%\%MIXER_BLENDER_ZIP_BASENAME% GOTO COPYUNZIPEDFOLDER
IF EXIST %CACHE%\%MIXER_BLENDER_ZIP_BASENAME%.zip GOTO UNZIP

REM rely on a bash script to download blender, to bypass proxy issues with powershell Invoke-WebRequest
"%MIXER_BASH_EXE%" %CURRENT_DIR%\download_blender_%MIXER_BLENDER_DOWNLOAD%%.sh

:UNZIP
REM unzip blender
powershell Expand-Archive %CACHE%\%MIXER_BLENDER_ZIP_BASENAME%.zip -DestinationPath %CURRENT_DIR%\blender\cache

:COPYUNZIPEDFOLDER
xcopy /S /Q /Y /F %CACHE%\%MIXER_BLENDER_ZIP_BASENAME% %CURRENT_DIR%\blender\%MIXER_BLENDER_ZIP_BASENAME%\

REM create config folder to isolate blender from user environment
powershell New-Item -ItemType Directory -Path %CURRENT_DIR%\blender\%MIXER_BLENDER_ZIP_BASENAME%\%MIXER_BLENDER_VERSION_BASE%\config

set MIXER_BLENDER_EXE_DIR=%CURRENT_DIR%\blender\%MIXER_BLENDER_ZIP_BASENAME%
set MIXER_BLENDER_EXE_PATH=%MIXER_BLENDER_EXE_DIR%\blender.exe
set PYTHON=%MIXER_BLENDER_EXE_DIR%\%MIXER_BLENDER_VERSION_BASE%\python\bin\python.exe

REM install Mixer in local blender
%MIXER_BLENDER_EXE_PATH% --background --python %CURRENT_DIR%\install_mixer.py

REM These tests run within blender
%PYTHON% -m pip install unittest-xml-reporting parameterized
%MIXER_BLENDER_EXE_PATH% --background --python-exit-code 1 --python mixer\blender_data\tests\ci.py
if %ERRORLEVEL% GEQ 1 SET ERROR=%ERRORLEVEL%

REM These tests launch 2 blender that communicate together
%PYTHON% -m xmlrunner discover --verbose tests.vrtist -o %MIXER_TEST_OUTPUT%
if %ERRORLEVEL% GEQ 1 SET ERROR=%ERRORLEVEL%

%PYTHON% -m xmlrunner discover --verbose tests.broadcaster -o %MIXER_TEST_OUTPUT%
if %ERRORLEVEL% GEQ 1 SET ERROR=%ERRORLEVEL%

%PYTHON% -m xmlrunner discover --verbose tests.blender -o %MIXER_TEST_OUTPUT%
if %ERRORLEVEL% GEQ 1 SET ERROR=%ERRORLEVEL%

IF %MIXER_BLENDER_DOWNLOAD% == "release" GOTO END
REM Download from builder: always cleanup, files are never reusable
RMDIR /S /Q %CACHE%\%MIXER_BLENDER_ZIP_BASENAME%
DEL %CACHE%\%MIXER_BLENDER_ZIP_BASENAME%.zip

:END
if %ERROR% GEQ 1 EXIT /B %ERROR%