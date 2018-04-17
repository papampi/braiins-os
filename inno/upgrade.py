#!/usr/bin/env python3

import argparse
import telnetlib
import tarfile
import socket
import time
import sys
import io

from functools import partial
from progress.bar import Bar

TELNET_PORT = 8100

NC_PORT = 9000

USERNAME = 'root'
PASSWORD = 't1t2t3a5'

SOURCE_DIR = 'firmware'
TARGET_DIR = '/tmp'

BLOCK_SIZE = 0x80000


def write_str(self, buffer: str):
    self.write(buffer.encode('ascii'))


def tar_directory(path):
    stream = io.BytesIO()
    tar = tarfile.open(mode="w:gz", fileobj=stream)
    tar.add(path)
    tar.close()
    return stream


def send_stream(stream, hostname: str, port: int):
    # get stream size
    stream_size = stream.seek(0, io.SEEK_END)
    stream.seek(0)

    # connect to server
    print("Connecting to netcat server...")
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    while True:
        try:
            time.sleep(0.5)
            server.connect((hostname, port))
        except ConnectionRefusedError:
            continue
        else:
            break

    progress = Bar('Uploading: ', max=stream_size)
    while True:
        data = stream.read(BLOCK_SIZE)
        if len(data) == 0:
            break
        server.sendall(data)
        progress.next(len(data))
    progress.finish()

    # disconnect from server
    print("Transfer done...")
    # FIXME: why sleep?
    time.sleep(1)
    server.shutdown(socket.SHUT_WR)
    server.close()


def main(args):
    print("Preparing upgrade tarball...")
    tarball = tar_directory(SOURCE_DIR)

    print("Connecting to remote host...")

    tn = telnetlib.Telnet(host=args.hostname, port=args.port)
    tn.write_str = partial(write_str, tn)

    tn.read_until(b'login: ')
    tn.write_str("{}\n".format(USERNAME))

    tn.read_until(b'Password: ')
    tn.write_str("{}\n".format(PASSWORD))

    # exit immediately when error occurs
    tn.write_str("set -e\n")

    # remove old data from target directory for uploaded firmware
    tn.write_str("rm -fr {}/{}\n".format(TARGET_DIR, SOURCE_DIR))

    # change current directory to target directory
    tn.write_str("cd {}\n".format(TARGET_DIR))

    # transfer files with netcat utility
    tn.write_str("nc -lp {} | tar zx\n".format(NC_PORT))

    print("Sending upgrade tarball...")
    send_stream(tarball, args.hostname, NC_PORT)

    print("Upgrading firmware...")

    # change current directory to extracted one
    tn.write_str("cd {}\n".format(SOURCE_DIR))
    tn.write_str("ll\n")

    tn.write_str("/bin/sh stage1.sh\n")

    tn.write_str("exit\n")
    print(tn.read_all().decode('ascii'))


if __name__ == "__main__":
    # execute only if run as a script
    parser = argparse.ArgumentParser()

    parser.add_argument('hostname',
                        help='hostname of DragonMint miner with original firmware')
    parser.add_argument('port', nargs='?', default=TELNET_PORT,
                        help='telnet port (default value is {})'.format(TELNET_PORT))

    # parse command line arguments
    args = parser.parse_args(sys.argv[1:])
    main(args)
