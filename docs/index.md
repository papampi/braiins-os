# Overview

This document is a quick-start guide how to install braiins OS image
on an original factory firmware.

It is recommended to test the hardware with an SD card image before flashing the firmware directly into your device.

# Common steps

Download the latest released firmware images + signatures from: [https://feeds.braiins-os.org/](https://feeds.braiins-os.org/)


The table below outlines correspondence between firmware image archive and a particular hardware type.

| Firmware prefix | Hardware |
| --- | --- |
| braiins-os-firmware_zynq-am1-s9_*.tar.bz2 | Antminer S9 |
| braiins-os-firmware_zynq-dm1-g9_*.tar.bz2 | Dragon Mint T1 with G9 control board |
| braiins-os-firmware_zynq-dm1-g19_*.tar.bz2 | Dragon Mint T1 with G19 control board |

The image signature can be verified by GPG:

```bash
gpg --search-keys release@braiins.cz
for i in ./braiins-os-firmware_*.tar.bz2; do gpg2 --verify $i.asc; done
```

You should see something like:

```
gpg: assuming signed data in './braiins-os-firmware_zynq-am1-s9_2018-09-22-0-853643de.tar.bz2'
gpg: Signature made Sat 22 Sep 2018 02:27:03 PM CEST using RSA key ID 616D9548
gpg: Good signature from "Braiins Systems Release Key (Key used for signing software made by Braiins Systems) <release@braiins.cz>" [ultimate]
```

Unpack the firmware image:

```bash
for i in  ./braiins-os-firmware_*.tar.bz2; do tar xvjf $i; done
```

The downloaded firmware image contains SD card components as well has a transitional firmware that can be flashed into device's on-board flash memory.


# Testing SD card image  (Antminer S9i example)

Insert an empty SD card into your reader and identify its block device (e.g. by ```lsblk```). You need an SD card with minimum capacity of 32 MB.

```
cd braiins-os-firmware_am1-s9-latest;
sudo dd if=sd.img of=/dev/your-sd-card-block-device
sync
```

## Adjusting MAC address
If you know the MAC address of your device, mount the SD card and adjust the MAC address. in ```uEnv.txt``` (most desktop Linux systems have automount capabilities once you reinsert the card into your reader). The ```uEnv.txt``` is environment for the bootloader and resides in the first (FAT) partition of the SD card. That way, once the device boots with braiins OS, it would have the same IP address as it had with the factory firmware.

## Booting the device from SD card
- Unmount the SD card
- Adjust jumper to boot from SD card (instead of flash memory):
   - [Antminer S9](s9)
   - [Dragon Mint T1](dm1)
- Insert it into the device and start the device. You should see a login screen shortly.


# Migrating from factory firmware to Braiins OS

Once the SD card works, it is very safe to attempt flashing the built-in flash memory as there will always be a way to recover the factory firmware.
Follow the steps below. The tool creates a backup of the original firmware in the ```backup``` folder

Below are steps to replace original factory firmware with braiins OS. The tool attempts to login to the machine via ssh, therefore you maybe prompted for a password.

```bash
cd braiins-os-firmware_am1-s9-latest/factory-transition
virtualenv --python=/usr/bin/python3 .env
source .env/bin/activate
pip install -r ./requirements.txt

python3 upgrade2bos.py your-miner-hostname-or-ip
```

# Migrating from Braiins OS to factory firmware

Restoring the original factory firmware requires issuing the command below. Please, note that the previously created backup needs to be available.

```bash
python3 restore2factory.py backup/2ce9c4aab53c-2018-09-19/ your-miner-hostname-or-ip
```

# Recovering bricked (unbootable) devices using SD card

If anything goes wrong and your device seems unbootable, you can use the previously created SD card image to recover it:

- Follow the steps in *Testing SD card image* to boot the device
- Run:
```
cd braiins-os-firmware_am1-s9-latest/factory-transition
python3 restore.py --sd-recovery backup/2ce9c4aab53c-2018-09-19/ your-miner-hostname-or-ip
```

# Firmware upgrade

Firmware upgrade process uses standard mechanism for installing/upgrading software packages within any OpenWrt based system. Follow the steps below to perform firmware upgrade:

```bash
# download latest packages from feeds server
$ opkg update
# try to upgrade to the latest firmware
$ opkg install firmware
```

Since the firmware installation results in reboot, the following output is expected:

```
root@MINER:~# opkg install firmware
Upgrading firmware on root from 2018-09-22-0-853643de to 2018-09-22-1-8d9b127d...
Downloading https://feeds.braiins-os.org/am1-s9/firmware_2018-09-22-1-8d9b127d_arm_cortex-a9_neon.ipk
Running system upgrade...
--2018-09-22 14:23:47--  https://feeds.braiins-os.org/am1-s9/firmware_2018-09-22-1-8d9b127d_arm_cortex-a9_neon.tar
Resolving feeds.braiins-os.org... 104.25.97.101, 104.25.98.101, 2400:cb00:2048:1::6819:6165, ...
Connecting to feeds.braiins-os.org|104.25.97.101|:443... connected.
HTTP request sent, awaiting response... 200 OK
Length: 10373471 (9.9M) [application/octet-stream]
Saving to: '/tmp/sysupgrade.tar'

/tmp/sysupgrade.tar                     100%[==============================================================================>]   9.89M  10.7MB/s    in 0.9s

2018-09-22 14:23:48 (10.7 MB/s) - '/tmp/sysupgrade.tar' saved [10373471/10373471]

Collected errors:
* opkg_conf_load: Could not lock /var/lock/opkg.lock: Resource temporarily unavailable.
Saving config files...
Connection to 10.33.0.166 closed by remote host.
Connection to 10.33.0.166 closed.
```

# Factory reset

Factory reset is as simple as uninstalling the the current firmware package:

```bash
$ opkg remove firmware
```

This effectively downgrades your firmware version to whatever it was when the transition to braiins OS has been done for the first time.
