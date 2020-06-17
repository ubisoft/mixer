#!/bin/bash

if [ -z $1 ]; then
  echo "Usage: $0 <zipfile>"
  exit 1
fi

OFFSET=`echo "file://" | wc -c`
DEPLOY_PATH=/`echo $CI_ENVIRONMENT_URL | cut -c $OFFSET-`

mkdir -p $DEPLOY_PATH
if [ -e $DEPLOY_PATH/mixer ]; then
  rm -rf $DEPLOY_PATH/mixer
fi

unzip $1 -d $DEPLOY_PATH