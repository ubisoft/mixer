#!/bin/bash

set -e
set -x

CURRENT_DIR=`dirname $0`
mkdir -p $CURRENT_DIR/blender/cache/
curl https://builder.blender.org/download/$MIXER_BLENDER_ZIP_BASENAME.zip -o $CURRENT_DIR/blender/cache/$MIXER_BLENDER_ZIP_BASENAME.zip
ls -l $CURRENT_DIR/blender/cache/$MIXER_BLENDER_ZIP_BASENAME.zip