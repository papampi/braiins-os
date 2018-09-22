# Miner Firmware SD Card Version

This version of firmware is intended only for development and test purpouse.

## Prerequisites

Two things are needed for successful installatio:

* Standard microSD card
* Hardware jumper

## SD Card Preparation

SD card must be properly formated and loaded with firmware and configuration files.

### Formating

Create one partition with the FAT16/32 filesystem. The size of partition is arbitrary.

The second partition with the Ext4 filesystem is optional and when presented, it is
used for storing configuration files. When this partition is omitted then all miner
settings are discarded after restart (the data are not persistent).

### Partition Content

The first partition should contain following files:

* boot.bin
* fit.itb
* system.bit
* u-boot.img
* uEnv.txt (optional)

The second partition can be empty.

### Configuration

The file uEnv.txt should contain setup of MAC address. The address is in following
format:

```
ethaddr=00:0A:35:DD:EE:FF
```

The last three numbers of MAC address determine miner host name. The host name for
previous example will be:

```
miner-ddeeff
```

## Control Board Setup

The boot process of the control board can be controlled by two pairs of pins (J1, J2).

For SD boot is needed following pins configuration:

```
J1 - OFF
J2 - ON
```

This means that only J2 pins are connected. This can be done by jumper or any applicable
wire.
