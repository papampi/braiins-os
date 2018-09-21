#!/bin/bash
# Purpose: custom script that prepares user environment and execute the release build

addgroup --gid=$LOC_GID build
adduser --system --home=$RELEASE_BUILD_DIR --no-create-home --uid=$LOC_UID --gid=$LOC_GID build
sudo -E -u build bash << EOF
export HOME=$RELEASE_BUILD_DIR
./build-release.sh $@
EOF
