#!/bin/bash
# Purpose: release script for braiins OS firmware

# The script:
# - generates a new release for specified sub targets
#
#

# Synopsis: ./make-release.sh SUBTARGET1 [SUBTARGET2 [SUBTARGET3...]]

target=zynq
release_subtargets=$@

$DRY_RUN virtualenv --python=/usr/bin/python3.5 .env
$DRY_RUN source .env/bin/activate
$DRY_RUN pip3 install -r requirements.txt

# Create release for all subtargets
for subtarget in $release_subtargets; do
    platform=$target-$subtarget
    echo Releasing $platform
    $DRY_RUN ./bb.py --platform $platform release
done
