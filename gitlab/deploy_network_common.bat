set DEPLOY_PATH=\\ubisoft.org\mtrstudio\World\UAS\Tech\_DEPLOY\blender\addons_intern\_deploy_test

if not exist %DEPLOY_PATH% mkdir %DEPLOY_PATH%

powershell Expand-Archive %1 -DestinationPath %DEPLOY_PATH%