#!/usr/bin/env python3

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

import argparse
import shutil
import socket
import errno
import time
import sys
import os

from ssh import SSHManager
from time import time as now

USERNAME = 'root'
PASSWORD = None

RECOVERY_MTDPARTS = 'recovery_mtdparts='

REBOOT_DELAY = (3, 8)


def get_mtdpart_size(value):
    multiplaier = {
        'k': 1024,
        'm': 1024 * 1024,
        'g': 1024 * 1024 * 1024
    }.get(value[-1], None)
    return multiplaier * int(value[:-1]) if multiplaier else int(value)


def parse_mtdparts(value):
    value = value[len(RECOVERY_MTDPARTS):].strip()
    start = value.index(':') + 1
    mtd_index = 0
    for mtdpart in value[start:].split(','):
        start = mtdpart.index('(')
        yield 'mtd{}'.format(mtd_index), get_mtdpart_size(mtdpart[:start]), mtdpart[start + 1:-1]
        mtd_index += 1


def parse_uenv(backup_dir):
    uenv_path = os.path.join(backup_dir, 'uEnv.txt')
    with open(uenv_path, 'r') as uenv_file:
        for line in uenv_file:
            if line.startswith(RECOVERY_MTDPARTS):
                return line[len(RECOVERY_MTDPARTS):].strip()
    return None


def wait_net_service(server, port, timeout=None):
    s = socket.socket()
    end = now() + timeout if timeout else None

    while True:
        try:
            if timeout:
                next_timeout = end - now()
                if next_timeout < 0:
                    return False
                else:
                    s.settimeout(next_timeout)

            s.connect((server, port))
        except socket.timeout:
            if timeout:
                return False
        except socket.error as err:
            if type(err.args) != tuple or err[0] != errno.ETIMEDOUT:
                raise
        else:
            s.close()
            return True


def wait(delay):
    for _ in range(delay):
        time.sleep(1)
        print('.', end='')
        sys.stdout.flush()


def wait_for_reboot(hostname, delay):
    print('Rebooting...', end='')
    delay_before, delay_after = delay
    wait(delay_before)
    while not wait_net_service(hostname, 22, 1):
        print('.', end='')
        sys.stdout.flush()
    wait(delay_after)
    print()


def main(args):
    mtdparts_params = parse_uenv(args.backup_dir)
    mtdparts = list(parse_mtdparts(mtdparts_params))

    if not args.sd_recovery:
        print("Connecting to remote host...")
        with SSHManager(args.hostname, USERNAME, PASSWORD) as ssh:
            ssh.run('fw_setenv', RECOVERY_MTDPARTS[:-1], '"{}"'.format(mtdparts_params))
            ssh.run('miner', 'run_recovery')
        wait_for_reboot(args.hostname, REBOOT_DELAY)

    print("Connecting to remote host...")
    # do not use host keys because recovery mode has different keys for the same MAC
    with SSHManager(args.hostname, USERNAME, PASSWORD, load_host_keys=False) as ssh:
        for dev, size, name in mtdparts:
            print('Restore {} ({})'.format(dev, name))
            dump_path = os.path.join(args.backup_dir, dev + '.bin')
            with open(dump_path, "rb") as local_dump, ssh.pipe('mtd', '-e', name, 'write', '-', name) as remote_dump:
                shutil.copyfileobj(local_dump, remote_dump.stdin)

        print('Restore finished successfully')
        if args.sd_recovery:
            print('Halting system...')
            print('Please turn off the miner and change jumper to boot it from NAND!')
            ssh.run('/sbin/halt')
        else:
            print('Rebooting to restored firmware...')
            ssh.run('/sbin/reboot')


if __name__ == "__main__":
    # execute only if run as a script
    parser = argparse.ArgumentParser()

    parser.add_argument('backup_dir',
                        help='path to directory with data for miner restore')
    parser.add_argument('hostname',
                        help='hostname of miner with original firmware')
    parser.add_argument('--sd-recovery', action='store_true',
                        help='use SD card recovery image with generated uEnv.txt')

    # parse command line arguments
    args = parser.parse_args(sys.argv[1:])
    main(args)
