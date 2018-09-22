#!/bin/bash
# Purpose: release script for braiins OS firmware

# The script:
# - generates a new release for specified sub targets
#
#

# Synopsis: ./make-release.sh SUBTARGET1 [SUBTARGET2 [SUBTARGET3...]]

target=zynq
release_subtargets=$@

# Create release for all subtargets
for subtarget in $release_subtargets; do
    platform=$target-$subtarget
    echo Releasing $platform
    $DRY_RUN ./bb.py --platform $platform release
done
