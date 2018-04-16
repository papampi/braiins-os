#!/bin/sh

set -e

cd /tmp/firmware

ETHADDR=$(fw_printenv -n ethaddr)
MINER_HWVER=$(fw_printenv -n hwver)

UBOOT_ENV_CFG="uboot_env.config"

STAGE2_FIRMWARE="stage2.tgz"

echo ${ETHADDR} > /dev/urandom
echo ${MINER_HWVER} > /dev/urandom
MINER_HWID=$(dd if=/dev/urandom bs=1 count=12 2>/dev/null | base64)

flash_eraseall /dev/mtd0

echo "Writing U-Boot images with FPGA bitstream..."
nandwrite -ps 0x000000 /dev/mtd0 "boot.bin"
nandwrite -ps 0x080000 /dev/mtd0 "u-boot.img"
nandwrite -ps 0x300000 /dev/mtd0 "system.bit.gz"

flash_eraseall /dev/mtd3

echo "Writing U-Boot environment..."
nandwrite -ps 0x200000 /dev/mtd3 "uboot_env.bin"
nandwrite -ps 0x220000 /dev/mtd3 "uboot_env.bin"

flash_eraseall /dev/mtd6

echo "Writing kernel image..."
nandwrite -ps 0x500000 /dev/mtd6 "fit.itb"

echo "Writing stage2 tarball..."
nandwrite -ps 0xF00000 /dev/mtd6 "$STAGE2_FIRMWARE"

echo "U-Boot configuration..."

# set firmware stage2 metadata
fw_setenv -c "$UBOOT_ENV_CFG" stage2_offset 0xA00000
fw_setenv -c "$UBOOT_ENV_CFG" stage2_size $(stat -c "%s" "$STAGE2_FIRMWARE")
fw_setenv -c "$UBOOT_ENV_CFG" stage2_mtd 8

# set miner configuration
fw_setenv -c "$UBOOT_ENV_CFG" ethaddr ${ETHADDR}
fw_setenv -c "$UBOOT_ENV_CFG" miner_hwid ${MINER_HWID}

echo
echo "Content of U-Boot configuration:"
fw_printenv -c "$UBOOT_ENV_CFG"

sync
reboot
