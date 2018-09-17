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
import datetime
import subprocess
import shutil
import hwid
import sys
import os

from ssh import SSHManager
from progress.bar import Bar

USERNAME = 'root'
PASSWORD = None

SYSTEM_DIR = 'system'
BACKUP_DIR = 'backup'
SOURCE_DIR = 'firmware'
TARGET_DIR = '/tmp/firmware'


class Progress:
    def __init__(self, file_path):
        self.file_path = file_path
        self.progress = None
        self._last = 0

    def __enter__(self):
        file_size = os.path.getsize(self.file_path)
        self.progress = Bar('{}:'.format(self.file_path), max=file_size)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.progress.finish()

    def __call__(self, transferred: int, total: int):
        self.progress.next(transferred - self._last)
        self._last = transferred


def upload_files(sftp, local_path, remote_path):
    print("Uploading firmware...")
    sftp.chdir(remote_path)

    for root, dirs, files in os.walk(local_path):
        root_remote = os.path.relpath(root, local_path)
        for name in files:
            local_file = os.path.join(root, name)
            with Progress(local_file) as progress:
                sftp.put(local_file, os.path.join(root_remote, name), callback=progress)
        for name in dirs:
            sftp.mkdir(os.path.join(root_remote, name))


def prepare_system(ssh):
    binaries = [
        ('ld-musl-armhf.so.1', '/lib'),
        ('sftp-server', '/usr/lib/openssh'),
        ('fw_printenv', '/usr/sbin')
    ]

    print("Preparing remote system...")

    for file_name, remote_path in binaries:
        ssh.run('mkdir', '-p', remote_path)
        remote_file_name = '{}/{}'.format(remote_path, file_name)
        print('Copy {} to {}'.format(file_name, remote_file_name))
        ssh.put(os.path.join(SYSTEM_DIR, file_name), remote_file_name)
        ssh.run('chmod', '+x', remote_file_name)

    ssh.run('ln', '-fs', '/usr/sbin/fw_printenv', '/usr/sbin/fw_setenv')
    print()


def mtdparts_size(value):
    for unit in ['', 'k', 'm']:
        if (value % 1024) != 0:
            break
        value = int(value / 1024)
    else:
        unit = 'g'
    return '{}{}'.format(value, unit)


def backup_firmware(ssh):
    print('Processing miner backup...')
    with ssh.pipe('cat', '/sys/class/net/eth0/address') as remote:
        mac = next(remote.stdout).strip()
    backup_dir = os.path.join(BACKUP_DIR, '{}-{:%Y-%m-%d}'.format(mac.replace(':', ''), datetime.datetime.now()))
    os.makedirs(backup_dir, exist_ok=True)
    mtdparts = []
    with ssh.pipe('cat', '/proc/mtd') as remote:
        next(remote.stdout)
        for line in remote.stdout:
            dev, size, _, name = line.split()
            dev = dev[:-1]
            size = int(size, 16)
            name = name[1:-1]
            print('Backup {} ({})'.format(dev, name))
            dump_path = os.path.join(backup_dir, dev + '.bin')
            with open(dump_path, "wb") as local_dump, ssh.pipe('/usr/sbin/nanddump', '/dev/' + dev) as remote_dump:
                shutil.copyfileobj(remote_dump.stdout, local_dump)
            mtdparts.append('{}({})'.format(mtdparts_size(size), name))

    with open(os.path.join(backup_dir, 'uEnv.txt'), 'w') as uenv:
        uenv.write('recovery=yes\n'
                   'recovery_mtdparts=mtdparts=pl35x-nand:{}\n'
                   'ethaddr={}\n'.format(','.join(mtdparts), mac))


def main(args):
    print("Connecting to remote host...")
    with SSHManager(args.hostname, USERNAME, PASSWORD) as ssh:
        # prepare target directory
        ssh.run('rm', '-fr', TARGET_DIR)
        ssh.run('mkdir', '-p', TARGET_DIR)

        # upgrade remote system with missing utilities
        if os.path.isdir(SYSTEM_DIR):
            prepare_system(ssh)

        if not args.no_backup:
            backup_firmware(ssh)

        # copy firmware files to the server over SFTP
        sftp = ssh.open_sftp()
        upload_files(sftp, SOURCE_DIR, TARGET_DIR)
        sftp.close()

        # generate HW identifier for miner
        hw_id = hwid.generate()

        # run stage1 upgrade process
        try:
            print("Upgrading firmware...")
            stdout, _ = ssh.run('cd', TARGET_DIR, '&&', 'ls', '-l', '&&',
                                "/bin/sh stage1.sh '{}'".format(hw_id))
        except subprocess.CalledProcessError as error:
            for line in error.stderr.readlines():
                print(line, end='')
        else:
            for line in stdout.readlines():
                print(line, end='')
            print('Upgrade was successful!')
            print('Rebooting...')
            try:
                ssh.run('/sbin/reboot')
            except subprocess.CalledProcessError:
                # reboot returns exit status -1
                pass


if __name__ == "__main__":
    # execute only if run as a script
    parser = argparse.ArgumentParser()

    parser.add_argument('hostname',
                        help='hostname of miner with original firmware')
    parser.add_argument('--no-backup', action='store_true',
                        help='skip NAND backup before upgrade')

    # parse command line arguments
    args = parser.parse_args(sys.argv[1:])
    main(args)
