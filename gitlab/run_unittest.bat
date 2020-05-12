tscon 0 /dest:console
tscon 1 /dest:console
tscon 2 /dest:console
tscon 3 /dest:console
tscon 4 /dest:console
tscon 5 /dest:console

set PYTHON=%MIXER_BLENDER_EXE_DIR%\2.82\python\bin\python.exe
%MIXER_BLENDER_EXE_PATH% --background --python gitlab\install_mixer.py
%PYTHON% -m unittest --verbose
