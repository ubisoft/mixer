set MIXER_BLENDER_EXE_PATH=c:\Blender-dev\blender-2.83.9-windows64\blender.exe

set TEST=tests.blender.test_blenddata_ids.TestShapeKey.test_remove_key
set GOOD=294ad1a30d10921afd4e94f36f718c7651cec66f
set BAD=2b86a2e2579c46156b1c69a7e3a668484967440f

git bisect reset
git bisect start %BAD% %GOOD%
git bisect run python -m unittest %TEST%
git bisect log
