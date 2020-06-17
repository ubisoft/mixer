#!/bin/bash

DOWNLOAD_URL=$CI_PROJECT_URL/releases/$CI_COMMIT_REF_NAME/downloads/mixer-addon-zip
DEPLOY_PATH=//ubisoft.org/mtrstudio/World/UAS/Tech/_DEPLOY/blender/addons_intern/_deploy_test

mkdir -p $DEPLOY_PATH

curl $DOWNLOAD_URL > $DEPLOY_PATH/mixer-$CI_COMMIT_REF_NAME.zip
rm -rf $DEPLOY_PATH/mixer
unzip $DEPLOY_PATH/mixer-$CI_COMMIT_REF_NAME.zip
# rm mixer-$CI_COMMIT_REF_NAME.zip