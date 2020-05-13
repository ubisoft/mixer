tscon 0 /dest:console
tscon 1 /dest:console
tscon 2 /dest:console
tscon 3 /dest:console
tscon 4 /dest:console
tscon 5 /dest:console

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

REM download zip of blender if not in cache folder
$pw = powershell ConvertTo-Securestring -AsPlainText -Force -String %MIXER_PROXY_PASSWORD%
$cred = powershell New-Object -TypeName System.Management.Automation.PSCredential -ArgumentList (%MIXER_PROXY_LOGIN%,$pw)
powershell Invoke-WebRequest https://download.blender.org/release/Blender%MIXER_BLENDER_VERSION_BASE%/%MIXER_BLENDER_ZIP_BASENAME%.zip -OutFile %CURRENT_DIR%\blender\cache\%MIXER_BLENDER_ZIP_BASENAME%.zip

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

REM run unit tests
%PYTHON% -m unittest --verbose
