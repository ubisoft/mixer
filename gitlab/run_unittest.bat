tscon 0 /dest:console
tscon 1 /dest:console
tscon 2 /dest:console
tscon 3 /dest:console
tscon 4 /dest:console
tscon 5 /dest:console

set ERROR=0
set CURRENT_DIR=%~dp0

REM create local folders if required
if not exist %CURRENT_DIR%\blender mkdir %CURRENT_DIR%\blender
if not exist %CURRENT_DIR%\blender\cache mkdir %CURRENT_DIR%\blender\cache

REM remove old blender install if it exists
IF NOT EXIST %CURRENT_DIR%\blender\%MIXER_BLENDER_ZIP_BASENAME% GOTO DOWNLOADZIP
RMDIR /S /Q %CURRENT_DIR%\blender\%MIXER_BLENDER_ZIP_BASENAME%

:DOWNLOADZIP

REM if unzipped folder already exists in cache folder, just copy it
IF EXIST %CURRENT_DIR%\blender\cache\%MIXER_BLENDER_ZIP_BASENAME% GOTO COPYUNZIPEDFOLDER

IF EXIST %CURRENT_DIR%\blender\cache\%MIXER_BLENDER_ZIP_BASENAME%.zip GOTO UNZIP

REM rely on a bash script to download blender, to bypass proxy issues with powershell Invoke-WebRequest
"%MIXER_BASH_EXE%" %CURRENT_DIR%\download_blender.sh

:UNZIP

REM unzip blender
powershell Expand-Archive %CURRENT_DIR%\blender\cache\%MIXER_BLENDER_ZIP_BASENAME%.zip -DestinationPath %CURRENT_DIR%\blender\cache

:COPYUNZIPEDFOLDER
xcopy /S /Q /Y /F %CURRENT_DIR%\blender\cache\%MIXER_BLENDER_ZIP_BASENAME% %CURRENT_DIR%\blender\%MIXER_BLENDER_ZIP_BASENAME%\

REM create config folder to isolate blender from user environment
powershell New-Item -ItemType Directory -Path %CURRENT_DIR%\blender\%MIXER_BLENDER_ZIP_BASENAME%\%MIXER_BLENDER_VERSION_BASE%\config

set MIXER_BLENDER_EXE_DIR=%CURRENT_DIR%\blender\%MIXER_BLENDER_ZIP_BASENAME%
set MIXER_BLENDER_EXE_PATH=%MIXER_BLENDER_EXE_DIR%\blender.exe
set PYTHON=%MIXER_BLENDER_EXE_DIR%\%MIXER_BLENDER_VERSION_BASE%\python\bin\python.exe

REM install Mixer in local blender
%MIXER_BLENDER_EXE_PATH% --background --python %CURRENT_DIR%\install_mixer.py

REM Theses tests run within blender
%MIXER_BLENDER_EXE_PATH% --background --python mixer\blender_data\tests\ci.py
if %ERRORLEVEL% GEQ 1 SET ERROR=%ERRORLEVEL%

REM run unit tests. Theses tests launch 2 blender that communicate together
%PYTHON% -m unittest discover --verbose
if %ERRORLEVEL% GEQ 1 SET ERROR=%ERRORLEVEL%

if %ERROR% GEQ 1 EXIT /B %ERROR%