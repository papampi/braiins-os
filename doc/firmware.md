# braiins/LEDE Miner Firmware

## MTD Partitons (NAND)

| Dev           | Address               | Size       | Name      |
|:-------------:|:---------------------:|:----------:| --------- |
| mtd0          | 0x00000000-0x00080000 | 0x00080000 | boot      |
| mtd1          | 0x00080000-0x00300000 | 0x00280000 | uboot     |
| mtd2          | 0x00300000-0x00500000 | 0x00200000 | fpga1     |
| mtd3          | 0x00500000-0x00700000 | 0x00200000 | fpga2     |
| mtd4          | 0x00700000-0x00780000 | 0x00080000 | uboot_env |
| mtd5          | 0x00780000-0x00800000 | 0x00080000 | miner_cfg |
| mtd6          | 0x00800000-0x01e00000 | 0x01600000 | recovery  |
| mtd7          | 0x01e00000-0x07d00000 | 0x05f00000 | firmware1 |
| mtd8          | 0x07d00000-0x0dc00000 | 0x05f00000 | firmware2 |

### boot

The partition contains U-Boot *SPL* (Secondary Program Loader). This small boot loader is stripped-down version of
U-Boot and do initial hardware configuration and load the larger, fully featured version of U-Boot.

The *SPL* supports booting from SD and NAND configured for a DragonMint miner.

### uboot

The U-Boot legacy uImage with minor modification to control loading Linux kernel from various sources (NAND, SD, ...).
Default script supports following features:

* NAND boot,
* SD boot,
* auto recovery feature (return back previous firmware when new one does not work),
* recovery mode (boot to special factory image),
* factory reset (use recovery mode for resetting miner to default configuration),
* environment overloading with *uEnv.txt*,
* FPGA bitstream load,
* GPIO access,
* NAND MTD partitions.

### fpga

This partition contains the programming information (bitstream) for an FPGA. There are actually two partitions.
Only one partition is active at a time. This partition always contains the latest released version of bitstream and is used during auto
recovery process.

### uboot_env

This partition contains U-Boot redundant environment. This configuration uses two environments. When the second environment
gets corrupted, U-Boot tries to recover data from the first one. Linux U-Boot firmware tools (*fw_printenv*,
*fw_setenv*) have to be configured in *fw_env.config* as follows:

```
# MTD device name   Device offset   Env. size   Flash sector size
/dev/mtd4           0x00000         0x20000     0x20000
/dev/mtd4           0x20000         0x20000     0x20000
```

### miner_cfg

This partition uses U-Boot environment for storing unique information about miner and is written only once during factory
programming or initial upgrade from original firmware. The data is also stored in redundant environment format because
U-Boot can be configured only for one format. However, it does not use the second data storage. The environment stores
the following information:

* MAC address,
* miner HWID,
* default pool settings.

This data are used during factory reset to restore the initial configuration.

### recovery

This is read-only partition. It is created during factory programming or initial upgrade from original firmware.
When U-Boot is not corrupted this partition can be used for miner recovery. The recovery image is logically divided
to three partitions:

| Address               | Size       | Name      |
|:---------------------:|:----------:| --------- |
| 0x00000000-0x00800000 | 0x00800000 | kernel    |
| 0x00800000-0x01400000 | 0x00c00000 | factory   |
| 0x01400000-0x01600000 | 0x00200000 | fpga      |

The *kernel* partition contains an U-Boot *FIT* image with a gzipped Linux kernel image, *DTB* image and read-only root
filesystem (*SquashFS*). A writable overlay uses non-persistent *tmpfs*. The image is loaded by the U-Boot when recovery
mode is detected.

The *factory* partition contains *UBI* image compatible with *ubiformat* and used for factory reset. The factory reset
is automatically initiated from the recovery mode during boot process when variable `factory_reset=yes` is set in the
U-Boot environment. Default environment has set this variable so when the *uboot_env* is deleted and automatically
restored by U-Boot, the factory reset is run.

The U-Boot loads FPGA with bitstream from the recovery *fpga* partition when booting to recovery mode. This bitstream is
also used during factory reset. 

### firmware

An *UBI* partition with threed dynamic partitions contains a Linux kernel, read-only root file system and writable
overlay. There are actually two partitions. Only one partition is active. This partition always contains functional
version of firmware and is used during auto recovery process.

| Name   | File System        |
| ------ | ------------------ |
| kernel | None (*FIT* image) |
| rootfs | *SquashFS*         |
| data   | *UBIFS*            |

## Miner Signalization (LED)

A miner LED signalization depends on operational mode. There are two modes (*recovery* and *normal*) which are signaled
by a green LED on the front panel. A red LED on the front panel has different meaning based on operational mode. A red
LED on control board (inside) always shows *heartbeat* (flashes at a load average based rate).

### Recovery Mode

The recovery mode is signaled by **flashing green LED** on the front panel. The **red LED** represents access to a NAND
disk and flashing during factory reset when data are written to the NAND.

### Normal Mode

The normal mode is signaled by **solid green LED** on the front panel. The **red LED** on the front panel has the
following meaning:

* **on** - *cgminer* or *cgminer_monitor* are not running
* **slow flashing** - hashrate is bellow 80% of expected hashrate
* **off** - *cgminer* running and hashrate above 80% of expected hashrate
* **fast flashing** - LED override requested by user (`miner fault_light on`)

## SD Boot

It is possible to boot from SD card without opening miner and connecting HW jumper on a control board. The U-Boot loader
booted from a NAND tries to detect inserted SD card. When first partition with FAT contains a file *uEnv.txt* with a
line **sd_boot=yes** then the U-Boot tries to load FIT image from SD card. *However, the U-Boot from SD is not used!*

## Firmware Upgrade

First method is to used an *opkg* utility which use feeds server with a firmware meta-package:

```bash
# download latest packages from feeds server
$ opkg update
# try to upgrade to the latest firmware
$ opkg install firmware
```

The second option is to download sysupgrade tarball and update miner from web interface or from commandline:

```bash
# download latest firmware tarball
$ wget ${url}/firmware-xyz.tar
# call standard LEDE sysupgade utility
$ sysupgrade firmware-xyz.tar
```

## Recovery Mode

The recovery mode can be invoked by different ways:

* *IP SET button* - hold it for *3s* until green LED flashes
* *SD card* - first partition with FAT contains file *uEnv.txt* with a line **recovery=yes** 
* *miner utility* - call `miner run_recovery` from the miner's command line

## Factory Reset

The factory reset can be invoked by different ways:

* *IP SET button* - hold it for *10s* until red LED flashes
* *SD card* - first partition with FAT contains file *uEnv.txt* with a line **factory_reset=yes** 
* *miner utility* - call `miner factory_reset` from the miner's command line

## Miner Tools

```
usage: miner [-h] {factory_reset,run_recovery,fault_light} ...

positional arguments:
  {factory_reset,run_recovery,light}
    factory_reset       reboot and initiate factory reset
    run_recovery        reboot to recovery mode
    fault_light         turn on or off miner's fault LED

optional arguments:
  -h, --help            show this help message and exit
```
