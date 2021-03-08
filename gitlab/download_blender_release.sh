#!/bin/bash

set -e
set -x

CURRENT_DIR=`dirname $0`
mkdir -p $CURRENT_DIR/blender/cache/
curl https://download.blender.org/release/Blender$MIXER_BLENDER_VERSION_BASE/$MIXER_BLENDER_ZIP_BASENAME.zip -o $CURRENT_DIR/blender/cache/$MIXER_BLENDER_ZIP_BASENAME.zip
ls -l $CURRENT_DIR/blender/cache/$MIXER_BLENDER_ZIP_BASENAME.zip