#!/bin/sh

set -e

file_size() {
	printf "0x%x" $(stat -c "%s" "$1")
}

cd /tmp/firmware

. ./info.sh

ETHADDR=$(fw_printenv -n ethaddr)
MINER_HWVER=$(fw_printenv -n hwver)
ROOTFS_FLAG=$(fw_printenv -n rootfs_flag) # a|b

UBOOT_ENV_CFG="uboot_env.config"

SPL_IMAGE="boot.bin"
UBOOT_IMAGE="u-boot.img"
UBOOT_ENV_DATA="uboot_env.bin"
BITSTREAM_DATA="system.bit.gz"
KERNEL_IMAGE="fit.itb"
STAGE2_FIRMWARE="stage2.tgz"

SPL_OFF=0x0
UBOOT_OFF=0x80000
UBOOT_ENV1_OFF=0x200000
UBOOT_ENV2_OFF=0x220000
BITSTREAM_OFF=0x300000

UBOOT_MTD=0
UBOOT_ENV_MTD=3

if [ x${MINER_HWVER} != x${FW_MINER_HWVER} ]; then
	echo "Unsupported miner version: ${MINER_HWVER}"
	exit 1
fi

if [ x${ROOTFS_FLAG} == x"a" ]; then
	SRC_KERNEL_OFF=0x0500000
	DST_KERNEL_OFF=0x7D00000
	SRC_STAGE2_OFF=0x0F00000
	DST_STAGE2_OFF=0x0A00000
	SRC_STAGE2_MTD=6
	DST_STAGE2_MTD=8
elif [ x${ROOTFS_FLAG} == x"b" ]; then
	SRC_KERNEL_OFF=0x1400000
	DST_KERNEL_OFF=0x1E00000
	SRC_STAGE2_OFF=0x1E00000
	DST_STAGE2_OFF=0x0A00000
	SRC_STAGE2_MTD=4
	DST_STAGE2_MTD=7
else
	echo "Unsupported rootfs flag: ${ROOTFS_FLAG}"
	exit 1
fi

echo ${ETHADDR} > /dev/urandom
echo ${MINER_HWVER} > /dev/urandom
MINER_HWID=$(dd if=/dev/urandom bs=1 count=12 2>/dev/null | base64)

flash_eraseall /dev/mtd${UBOOT_MTD}

echo "Writing U-Boot images with FPGA bitstream..."
nandwrite -ps ${SPL_OFF} /dev/mtd${UBOOT_MTD} "$SPL_IMAGE"
nandwrite -ps ${UBOOT_OFF} /dev/mtd${UBOOT_MTD} "$UBOOT_IMAGE"
nandwrite -ps ${BITSTREAM_OFF} /dev/mtd${UBOOT_MTD} "$BITSTREAM_DATA"

flash_eraseall /dev/mtd${UBOOT_ENV_MTD}

echo "Writing U-Boot environment..."
nandwrite -ps ${UBOOT_ENV1_OFF} /dev/mtd${UBOOT_ENV_MTD} "$UBOOT_ENV_DATA"
nandwrite -ps ${UBOOT_ENV2_OFF} /dev/mtd${UBOOT_ENV_MTD} "$UBOOT_ENV_DATA"

flash_eraseall /dev/mtd${SRC_STAGE2_MTD}

echo "Writing kernel image..."
nandwrite -ps ${SRC_KERNEL_OFF} /dev/mtd${SRC_STAGE2_MTD} "$KERNEL_IMAGE"

echo "Writing stage2 tarball..."
nandwrite -ps ${SRC_STAGE2_OFF} /dev/mtd${SRC_STAGE2_MTD} "$STAGE2_FIRMWARE"

echo "U-Boot configuration..."

# bitstream metadata
fw_setenv -c "$UBOOT_ENV_CFG" bitstream_off ${BITSTREAM_OFF}
fw_setenv -c "$UBOOT_ENV_CFG" bitstream_size $(file_size "$BITSTREAM_DATA")

# set kernel metadata
fw_setenv -c "$UBOOT_ENV_CFG" kernel_off ${DST_KERNEL_OFF}
fw_setenv -c "$UBOOT_ENV_CFG" kernel_size $(file_size "$KERNEL_IMAGE")

# set firmware stage2 metadata
fw_setenv -c "$UBOOT_ENV_CFG" stage2_off ${DST_STAGE2_OFF}
fw_setenv -c "$UBOOT_ENV_CFG" stage2_size $(file_size "$STAGE2_FIRMWARE")
fw_setenv -c "$UBOOT_ENV_CFG" stage2_mtd ${DST_STAGE2_MTD}

# set miner configuration
fw_setenv -c "$UBOOT_ENV_CFG" ethaddr ${ETHADDR}
fw_setenv -c "$UBOOT_ENV_CFG" miner_hwid ${MINER_HWID}

echo
echo "Content of U-Boot configuration:"
fw_printenv -c "$UBOOT_ENV_CFG"

sync
reboot
