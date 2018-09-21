#!/bin/bash
# Purpose: custom script that prepares user environment and execute the release build

addgroup --gid=$LOC_GID build
adduser --system --home=$RELEASE_BUILD_DIR --no-create-home --uid=$LOC_UID --gid=$LOC_GID build
# release build is already created due to the fact that we have mapped into it .ssh with known hosts file
chown build.build $RELEASE_BUILD_DIR
sudo -H -E -u build bash << EOF
./build-release.sh $@
EOF
