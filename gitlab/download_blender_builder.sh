#!/bin/bash

set -e
set -v

CURRENT_DIR=`dirname $0`
mkdir -p $CURRENT_DIR/blender/cache/
curl https://builder.blender.org/download/$MIXER_BLENDER_ZIP_BASENAME.zip > $CURRENT_DIR/blender/cache/$MIXER_BLENDER_ZIP_BASENAME.zip