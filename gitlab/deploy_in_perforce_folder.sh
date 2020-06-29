#!/bin/bash

set -e

# This script assume $CI_ENVIRONMENT_URL contains a perforce folder path after http://
# For example http://RRSpecial/_Tech/Blender/addons would map to //RRSpecial/_Tech/Blender/addons
# Perforce access is made with client workspace stored in P4CLIENT

if [ -z $P4CLIENT ]; then
  echo "Specify P4CLIENT env var: it should contain a perforce client name that can be used on the runner."
  exit 1
fi

if [ -z $1 ]; then
  echo "Usage: $0 <zipfile>"
  exit 1
fi

OFFSET=`echo "http:" | wc -c`
PERFORCE_PATH=`echo $CI_ENVIRONMENT_URL | cut -c $OFFSET-`

echo "PERFORCE_PATH = $PERFORCE_PATH"

PATHS=`p4 where $PERFORCE_PATH | tr '\' '/'`
if [ -z "$PATHS" ]; then
  echo "Empty PATHS returned by p4 where for $PERFORCE_PATH, check that is it correct."
  exit 1
fi

IFS=' '
read -a strarr <<< "$PATHS"

echo "PATHS = $PATHS"

DEPLOY_PATH=${strarr[-1]}

echo "Local path is $DEPLOY_PATH"

if [ ! -e $DEPLOY_PATH ]; then
  echo "Error: Deploy path does not exists, create it first."
  exit 1
fi

p4 sync -f

if [ -e $DEPLOY_PATH/mixer ]; then
  echo "Deleting previous mixer installation"
  shopt -s globstar dotglob
  pushd $DEPLOY_PATH/mixer/
  for file in **/*; do
    if [ -f "$file" ]; then
      p4 delete "$PERFORCE_PATH/mixer/$file"
    fi
  done
  popd
  rm -rf $DEPLOY_PATH/mixer

  p4 submit -d "Remove old mixer installation"
  p4 sync -f
fi

echo "Unzipping mixer installation"
unzip $1 -d $DEPLOY_PATH

if [ -e $DEPLOY_PATH/mixer ]; then
  echo "Adding new mixer installation"
  shopt -s globstar dotglob
  pushd $DEPLOY_PATH/mixer/
  for file in **/*; do
    if [ -f "$file" ]; then
      p4 add "$PERFORCE_PATH/mixer/$file"
    fi
  done
  popd

  p4 submit -d "Update mixer to $CI_COMMIT_REF_NAME"
  p4 sync -f
fi