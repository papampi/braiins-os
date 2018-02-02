# Miner Firmware Build System

The Miner build system is based on the LEDE build system and it is only wrapper around this system.

It extends the LEDE build system with following features:

* automatic clone/pull of all repositories
* switching between several configurations
* out-of-tree repositories for development
* status of all developed repositories
* cleaning and purging repositories
* setup environment for using LEDE toolchain in external projects

## Getting Started

These instructions will get you a copy of the project up and running on your local machine for development and testing
purposes. See deployment for notes on how to deploy the project on a live system.

### Prerequisites

The Miner build system is written in *Python 3.5.3* and it also requires following modules:

* GitPython 2.1.8
* ruamel.yaml 0.13.4
* termcolor 1.1.0
* colorlog 2.10.0
* progress 1.2

### Installing

Clone git repository with *lede-meta* to some directory.

```commandline
# clone LEDE build system from git
$ git clone git@gitlab.bo:x/lede-meta.git
$ cd lede-meta
```

## Building

For building firmware image with default configuration it can be simply called *lede.py* script with *build* command.

Default configuration is set for **development** and not for **release** image!

```commandline
# build firmware image with default configuration
$ ./lede.py build

# build firmware image with release configuration
$ ./lede.py --config configs/release.yml build
```

All repositories are stored in **build**/<*target*> directory where *target* is specified in *YAML* configuration file
under *build.name* attribute.

## Development

Default configuration for development has disabled automatic fetching/merging of remote repositories when *build*
command is executed. But it can be used *prepare* command instead when synchronization with remote is needed.

```commandline
# force fetching from remote repositories
$ ./lede.py prepare --fetch
```

It is possible to clean all project with two options. Simple execution of *clean* command use LEDE *make clean* to clean
the whole build system. It does not guarantee that all files will be in its initial state. The second option use git
command to clean all repositories and after that run initialization phase again. This option removes all untracked files
and must be called with cautious!

```commandline
# clean repositories with LEDE make clean
$ ./lede.py clean

# clean repositories with git clean
$ ./lede.py clean --purge
```

The whole miner project consists of several git repositories and during development is convenient to track status of all
changes in all repositories at once. For this purpose can be used command *status* which is similar to git status but
it is executed on all repositories.

```commandline
# get status of all repositories
$ ./lede.py status
```

Rather then executing the whole LEDE build system which can be slow, it can be used standard *make* of developed
subproject (e.g. CGMiner) with LEDE toolchain. Environment variables must be set correctly for use LEDE toolchain in
out-of-tree projects. For this purpose, the *toolchain* command is provided.

```commandline
# set environment variables for LEDE toochain out-of-tree use
$ eval $(./lede.py toolchain 2>/dev/null)
```

It is used standard LEDE menuconfig for firmware image configuration. When some changes are detected then configuration
difference is saved to the file specified in *YAML* configuration file under *build.config* attribute. It is also
possible to configure Linux kernel but configuration changes are then saved in LEDE build system in target directory.

```commandline
# configure miner firwmare
$ ./lede.py config

# configure Linux kernel
$ ./lede.py config --kernel
```

Miner build system supports multiple configurations which can be selected by global parameter *--config*. When script is
run without this parameter then **configs/default.yml** is used.

## Debugging


## Deployment


## Authors

* **Libor Vašíček** - *Initial work*


## License
