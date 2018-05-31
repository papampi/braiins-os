#!/usr/bin/env python3

import sys
import argparse
import logging
import colorlog
import miner


class CommandManager:
    def __init__(self):
        self._argv = None
        self._args = None
        self._config = None

    def set_args(self, argv, args):
        self._argv = argv
        self._args = args
        self._config = miner.load_config(args.config)

        if args.platform:
            # change default platform in configuration
            self._config.miner.platform = args.platform

    def get_builder(self):
        """
        Return miner builder for current configuration
        """
        return miner.Builder(self._config, self._argv)

    def prepare(self):
        logging.debug("Called command 'prepare'")
        builder = self.get_builder()
        builder.prepare(fetch=self._args.fetch)

    def clean(self):
        logging.debug("Called command 'clean'")
        builder = self.get_builder()
        if self._args.purge:
            builder.clean(purge=True)
            builder.prepare()
        else:
            builder.prepare()
            builder.clean()

    def config(self):
        logging.debug("Called command 'config'")
        builder = self.get_builder()
        builder.prepare()
        builder.config(kernel=self._args.kernel)

    def build(self):
        logging.debug("Called command 'build'")
        key = []
        if self._args.key:
            keys = self._args.key.split(':', 1)
            key.append(keys[0])
            key.append(keys[1] if len(keys) > 1 else '{}.pub'.format(key[0]))

        builder = self.get_builder()
        builder.prepare()
        builder.build(targets=self._args.target, jobs=self._args.jobs, verbose=self._args.verbose, key=tuple(key))

    def deploy(self):
        logging.debug("Called command 'deploy'")
        builder = self.get_builder()
        builder.prepare()
        builder.deploy(targets=self._args.targets or None)

    def status(self):
        logging.debug("Called command 'status'")
        builder = self.get_builder()
        builder.status()

    def debug(self):
        logging.debug("Called command 'debug'")
        builder = self.get_builder()
        builder.prepare()
        builder.build()
        builder.debug()

    def toolchain(self):
        logging.debug("Called command 'toolchain'")
        builder = self.get_builder()
        builder.prepare()
        builder.toolchain()

    def release(self):
        logging.debug("Called command 'release'")
        sysupgrade = self._config.build.sysupgrade
        for include in set(self._args.include or []):
            setattr(sysupgrade, include, 'yes')

        builder = self.get_builder()
        builder.prepare()
        builder.release()

    def key(self):
        logging.debug("Called command 'key'")
        secret = self._args.secret
        public = self._args.public or '{}.pub'.format(secret)

        builder = self.get_builder()
        builder.prepare()
        builder.generate_key(secret_path=secret, public_path=public)


def main(argv):
    command = CommandManager()

    # create the top-level parser
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()
    subparsers.required = True
    subparsers.dest = 'command'

    # create the parser for the "prepare" command
    subparser = subparsers.add_parser('prepare',
                                      help="prepare source directory")
    subparser.set_defaults(func=command.prepare)

    subparser.add_argument('--fetch', action='store_true',
                           help='force to fetch all repositories')

    # create the parser for the "clean" command
    subparser = subparsers.add_parser('clean',
                                      help="clean source directory")
    subparser.set_defaults(func=command.clean)

    subparser.add_argument('--purge', action='store_true',
                           help='reset all repositories to its initial state')

    # create the parser for the "prepare" command
    subparser = subparsers.add_parser('config',
                                      help="change default configuration of LEDE project")
    subparser.set_defaults(func=command.config)

    subparser.add_argument('--kernel', action='store_true',
                           help='configure Linux kernel')

    # create the parser for the "build" command
    subparser = subparsers.add_parser('build',
                                      help="build image for current configuration")
    subparser.set_defaults(func=command.build)

    subparser.add_argument('-j', '--jobs', type=int,
                           help='specifies the number of jobs to run simultaneously')

    subparser.add_argument('-v', '--verbose', action='store_true',
                           help='show all commands during build process')

    subparser.add_argument('-k', '--key',
                           help='specify path to build key in a format <secret>[:<public>]; '
                                'when the <public> key is omitted then <secret>.pub is used')

    subparser.add_argument('target', nargs='*',
                           help='build only specific targets when specified')

    # create the parser for the "deploy" command
    subparser = subparsers.add_parser('deploy',
                                      help="deploy selected image to target device")
    subparser.set_defaults(func=command.deploy)

    subparser.add_argument('targets', nargs='*',
                           help='list of targets for deployment')

    # create the parser for the "status" command
    subparser = subparsers.add_parser('status',
                                      help="show status of LEDE repository and all dependent projects")
    subparser.set_defaults(func=command.status)

    # create the parser for the "debug" command
    subparser = subparsers.add_parser('debug',
                                      help="debug application on remote target")
    subparser.set_defaults(func=command.debug)

    # create the parser for the "toolchain" command
    subparser = subparsers.add_parser('toolchain',
                                      help="set environment for LEDE toolchain")
    subparser.set_defaults(func=command.toolchain)

    # create the parser for the "release" command
    subparser = subparsers.add_parser('release',
                                      help="create branch with configuration for release version")
    subparser.set_defaults(func=command.release)

    subparser.add_argument('--include', choices=['command', 'uboot', 'fpga'], nargs='*',
                           help='components included in sysupgrade (firmware)')

    # create the parser for the "key" command
    subparser = subparsers.add_parser('key',
                                      help="generate build key pair for signing firmware tarball and packages")
    subparser.set_defaults(func=command.key)

    subparser.add_argument('secret',
                           help='path to secret key output')

    subparser.add_argument('public', nargs='?',
                           help='path to public key output; when omitted then <secret>.pub is used')

    # add global arguments
    parser.add_argument('--log', choices=['error', 'warn', 'info', 'debug'], default='info',
                        help='logging level')
    parser.add_argument('--config', default=miner.DEFAULT_CONFIG,
                        help='path to configuration file')
    parser.add_argument('--platform', choices=['zynq-dm1-g9', 'zynq-dm1-g19'], nargs='?',
                        help='change default miner platform')

    # parse command line arguments
    args = parser.parse_args(argv)

    # create color handler
    handler = colorlog.StreamHandler()
    handler.setFormatter(colorlog.ColoredFormatter(log_colors={
        'DEBUG':    'cyan',
        'INFO':     'green',
        'WARNING':  'yellow',
        'ERROR':    'red',
        'CRITICAL': 'red,bg_white',
    }))

    # set logging level
    logging.basicConfig(level=getattr(logging, args.log.upper()), handlers=[handler])

    # set arguments
    command.set_args(argv, args)

    # call sub-command
    args.func()


if __name__ == "__main__":
    # execute only if run as a script
    try:
        main(sys.argv[1:])
    except miner.BuilderStop:
        sys.exit(1)
