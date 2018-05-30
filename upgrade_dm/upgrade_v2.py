#!/usr/bin/env python3

import argparse
import subprocess
import hwid
import sys
import os

from ssh import SSHManager
from progress.bar import Bar

USERNAME = 'root'
PASSWORD = None

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
    sftp.chdir(remote_path)

    for root, dirs, files in os.walk(local_path):
        root_remote = os.path.relpath(root, local_path)
        for name in files:
            local_file = os.path.join(root, name)
            with Progress(local_file) as progress:
                sftp.put(local_file, os.path.join(root_remote, name), callback=progress)
        for name in dirs:
            sftp.mkdir(os.path.join(root_remote, name))


def main(args):
    print("Connecting to remote host...")
    with SSHManager(args.hostname, USERNAME, PASSWORD) as ssh:
        # prepare target directory
        ssh.run('rm', '-fr', TARGET_DIR)
        ssh.run('mkdir', '-p', TARGET_DIR)

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
                ssh.run('reboot')
            except subprocess.CalledProcessError:
                # reboot returns exit status -1
                pass


if __name__ == "__main__":
    # execute only if run as a script
    parser = argparse.ArgumentParser()

    parser.add_argument('hostname',
                        help='hostname of DragonMint miner with original firmware')

    # parse command line arguments
    args = parser.parse_args(sys.argv[1:])
    main(args)
