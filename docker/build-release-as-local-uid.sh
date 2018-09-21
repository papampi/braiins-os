#!/bin/bash
# Purpose: custom script that prepares user environment and execute the release build

addgroup --gid=$LOC_GID build
adduser --system --home=/ --no-create-home --uid=$LOC_UID --gid=$LOC_GID build
su build <<EOSU
./build-release.sh $@
EOSU
