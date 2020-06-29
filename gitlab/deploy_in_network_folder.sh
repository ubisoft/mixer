#!/bin/bash

set -e

# This script assume $CI_ENVIRONMENT_URL contains a network folder path after http://
# For example http:///A/B/C/D would deploy to //A/B/C/D

if [ -z $1 ]; then
  echo "Usage: $0 <zipfile>"
  exit 1
fi

OFFSET=`echo "http:" | wc -c`
DEPLOY_PATH=`echo $CI_ENVIRONMENT_URL | cut -c $OFFSET-`

echo "DEPLOY_PATH = $DEPLOY_PATH"

if [ ! -e $DEPLOY_PATH ]; then
  echo "Error: Deploy path does not exists, create it first."
  exit 1
fi

if [ -e $DEPLOY_PATH/mixer ]; then
  echo "Deleting previous mixer installation"
  rm -rf $DEPLOY_PATH/mixer
fi

echo "Unzipping mixer installation"
unzip $1 -d tmp/
cp -r tmp/mixer $DEPLOY_PATH