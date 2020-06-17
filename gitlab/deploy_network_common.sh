#!/bin/bash

DEPLOY_PATH=//ubisoft.org/mtrstudio/World/UAS/Tech/_DEPLOY/blender/addons_intern/_deploy_test

mkdir -p $DEPLOY_PATH

unzip $1 $DEPLOY_PATH/
# rm mixer-$CI_COMMIT_REF_NAME.zip