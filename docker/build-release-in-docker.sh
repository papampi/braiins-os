#!/bin/bash

# Make sure the image has been built:

#docker build -t braiins-os-builder .
echo params: $@
docker run --rm -u `id -u`:`id -u` -v ${PWD}:/src -w /src \
       braiins-os-builder ./build-release.sh $@
