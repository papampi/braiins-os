#!/bin/sh

# Copyright (C) 2018  Braiins Systems s.r.o.
#
# This file is part of Braiins Build System (BB).
#
# BB is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

if [ "$#" -ne 1 ]; then
    echo "Illegal number of parameters"
    exit 1
fi

set -e

MINER_HWID="$1"
UBOOT_ENV_CFG="uboot_env.config"

SPL_IMAGE="boot.bin"
UBOOT_IMAGE="u-boot.img"
UBOOT_ENV_DATA="uboot_env.bin"
BITSTREAM_DATA="system.bit.gz"
KERNEL_IMAGE="fit.itb"
STAGE2_FIRMWARE="stage2.tgz"

function sed_variables() {
    local value
    local args
    local input="$1"
    shift

    for name in "$@"; do
        eval value=\$$name
        args="$args -e 's,\${$name},$value,g'"
    done
    eval sed -i $args "$input"
}

cd /tmp/firmware

# include firmware specific code
. ./CONTROL

# prepare configuration file
sed_variables "$UBOOT_ENV_CFG" UBOOT_ENV_MTD UBOOT_ENV1_OFF UBOOT_ENV2_OFF

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
