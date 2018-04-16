#!/bin/sh

set -e

mtd_write() {
	mtd -e "$2" write "$1" "$2"
}

FW_ENV_CFG="fw_env.config"

echo "Running stage2 upgrade process..."

ETHADDR=$(fw_printenv -n ethaddr 2> /dev/null)
MINER_HWID=$(fw_printenv -n miner_hwid 2> /dev/null)

mtd_write fit.itb recovery
mtd -n -p 0x0800000 write factory.bin.gz recovery
mtd -n -p 0x1400000 write system.bit.gz recovery

# backup and change original fw_env.config
cp "/etc/$FW_ENV_CFG" "/tmp"
cp "miner_cfg.config" "/etc/$FW_ENV_CFG"

mtd_write miner_cfg.bin miner_cfg
fw_setenv ethaddr ${ETHADDR}
fw_setenv miner_hwid ${MINER_HWID}

# restore original fw_env.config
cp "/tmp/$FW_ENV_CFG" "/etc"

mtd erase uboot_env
mtd erase fpga1
mtd erase fpga2
mtd erase firmware1
mtd erase firmware2

sync
