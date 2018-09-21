#!/bin/bash

# Make sure the image has been built:

#docker build -t braiins-os-builder .
echo params: $@
#docker run --rm -u `id -u`:`id -u` -v ${PWD}:/src -w /src \
#       braiins-os-builder ./build-release.sh $@

release_build_dir=/src/release-build
docker run --env RELEASE_BUILD_DIR=$release_build_dir --env LOC_UID=`id -u` --env LOC_GID=`id -g` --volume $HOME/.ssh/known_hosts:$release_build_dir/.ssh/known_hosts:ro --volume $SSH_AUTH_SOCK:/ssh-agent --volume\
 ${PWD}:/src -w /src --env SSH_AUTH_SOCK=/ssh-agent braiins-os-builder ./docker/build-release-as-local-uid.sh $@
