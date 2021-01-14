@rem Repeat a test to highlight random failures

@echo off
setlocal enabledelayedexpansion

@rem set PYTHONHASHSEED=1
set TEST=tests.vrtist.test_conflicts.TestObjectRenameGeneric.test_update_object
set MIXER_BLENDER_EXE_PATH=c:\Blender-dev\blender-2.83.9-windows64\blender.exe

set FAIL=0
FOR /L %%x IN (1,1,10) do (
    python -m unittest -v %TEST%
    if errorlevel 1 (
        set FAIL=1
        exit /b 1) else echo OK
)

exit /b %FAIL%
