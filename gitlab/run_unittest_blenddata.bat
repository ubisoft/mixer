tscon 0 /dest:console
tscon 1 /dest:console
tscon 2 /dest:console
tscon 3 /dest:console
tscon 4 /dest:console
tscon 5 /dest:console

set PYTHON=%DCCSYNC_BLENDER_EXE_DIR%\2.82\python\bin\python.exe
%DCCSYNC_BLENDER_EXE_PATH% --background --python gitlab\install_dccsync.py
%DCCSYNC_BLENDER_EXE_PATH% --background --python dccsync\blender_data\tests\test_for_debug.py