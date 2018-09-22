FROM debian:stretch

RUN apt-get update && apt-get install -y \
    build-essential \
    sudo \
    python3 \
    virtualenv \
    git

RUN apt-get update && apt-get install -y \
    gawk \
    zlib1g-dev \
    libncurses5-dev \
    unzip \
    wget

RUN apt-get update && apt-get install -y \
    python2.7

RUN apt-get update && apt-get install -y \
    libssl1.0-dev

WORKDIR /
