#!/bin/bash

# This script assume $CI_ENVIRONMENT_URL contains a network folder path after http://
# For example http:///A/B/C/D would deploy to //A/B/C/D

if [ -z $1 ]; then
  echo "Usage: $0 <zipfile>"
  exit 1
fi

OFFSET=`echo "http://" | wc -c`
DEPLOY_PATH=/`echo $CI_ENVIRONMENT_URL | cut -c $OFFSET-`

echo "DEPLOY_PATH = $DEPLOY_PATH"

mkdir -p $DEPLOY_PATH
if [ -e $DEPLOY_PATH/mixer ]; then
  rm -rf $DEPLOY_PATH/mixer
fi

unzip $1 -d $DEPLOY_PATH