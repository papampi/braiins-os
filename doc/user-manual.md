# Overview

This document is a quick-start guide how to install braiins OS image
on an original factory firmware.

It is recommended to test the hardware with an SD card image before flashing the firmware directly into your device.

# Common steps

Download the latest released firmware images + signatures from:
https://github.com/braiins/braiins-os-releases/releases/latest


The table below outlines correspondence between firmware image archive and a particular hardware type.

| Firmware prefix | Hardware |
| --- | --- |
| braiins-os-firmware_zynq-am1-s9_*.tar.bz2 | Antminer S9 |
| braiins-os-firmware_zynq-dm1-g9_*.tar.bz2 | Dragon Mint T1 with G9 control board |
| braiins-os-firmware_zynq-dm1-g19_*.tar.bz2 | Dragon Mint T1 with G19 control board |

The image can be verified by GPG:

```bash
gpg --search-keys release@braiins.cz
for i in ./braiins-os-firmware_*.tar.bz2; do gpg2 --verify $i.asc; done
```

Unpack the firmware image:

```bash
for i in  ./braiins-os-firmware_*.tar.bz2; do tar xvjf $i; done
```

The downloaded firmware image contains SD card components as well has a transitional firmware that can be flashed into device's on-board flash memory.


# Testing SD card image


Before built-in flash memoryproceeding further it is recommended to verify that your mining hardware works as expe


# Migrating from factory firmware to Braiins OS

The trans

```

virtualenv --python=/usr/bin/python3 .env
source .env/bin/activate
pip install -r ./requirements.txt

Below are steps to perform remote upgrade of your factory
```
python3 upgrade.py your-miner-hostname-or-ip
```

# Migrating from Braiins OS to factory firmware
```
python3 restore.py backup/2ce9c4aab53c-2018-09-19/ 10.33.0.172
```

# Recovering bricked (unbootable) devices using SD card

Download SD card image and unpack all files to a dedicated partition.
Most boards boot from NAND flash by default. In case of recovery of bricked devices or testing experimental firmwares, it may be desirable to switch to SD card boot.

Adjust jumper to boot from SD card (instead of flash memory):
- [Antminer S9](s9#bootmode)
- [Dragon Mint T1][dm1#bootmode)

Important use:

```
python3 restore.py --sd-recovery backup/2ce9c4aab53c-2018-09-19/ 10.33.0.172
```

# Firmware upgrade

Firmware upgrade process uses standard mechanism for installing/upgrading software packages within any OpenWrt based system. Follow the steps below to perform firmware upgrade:

```bash
# download latest packages from feeds server
$ opkg update
# try to upgrade to the latest firmware
$ opkg install firmware
```

# Downgrade/roll back to previous version

```bash
opkg install --force-downgradable firmware
```
