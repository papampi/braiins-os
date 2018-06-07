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

        # set optional keys to default value
        self._config.setdefault('miner.pool.host', 'stratum+tcp://stratum.slushpool.com')
        self._config.setdefault('miner.pool.port', 3333)
        self._config.setdefault('miner.pool.user', 'braiinstest.worker1')
        self._config.setdefault('build.jobs', 1)
        self._config.setdefault('build.verbose', 'no')
        self._config.setdefault('remote.fetch', 'no')
        self._config.setdefault('remote.fetch_always', 'no')
        self._config.setdefault('uenv.mac', 'yes')
        self._config.setdefault('uenv.factory_reset', 'no')
        self._config.setdefault('uenv.sd_images', 'no')
        self._config.setdefault('uenv.sd_boot', 'no')

        # change default platform in configuration
        if args.platform:
            self._config.miner.platform = args.platform

    def get_builder(self):
        """
        Return miner builder for current configuration
        """
        return miner.Builder(self._config, self._argv)

    def prepare(self):
        logging.debug("Called command 'prepare'")
        if self._args.fetch:
            self._config.remote.fetch_always = 'yes'

        builder = self.get_builder()
        builder.prepare()

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
        force_key = False
        if self._args.key:
            keys = self._args.key.split(':', 1)
            key = self._config.setdefault('build.key', miner.ConfigDict())
            key.secret = keys[0]
            key.public = keys[1] if len(keys) > 1 else '{}.pub'.format(key[0])
            force_key = True
        if self._args.jobs:
            self._config.build.jobs = self._args.jobs
        if self._args.verbose:
            self._config.build.verbose = 'yes'

        builder = self.get_builder()
        builder.prepare()
        builder.build(targets=self._args.target, force_key=force_key)

    def deploy(self):
        logging.debug("Called command 'deploy'")
        # change target MAC address
        if self._args.mac:
            self._config.miner.mac = self._args.mac
        # change target hostname and override MAC determination
        if self._args.hostname:
            self._config.deploy.ssh.hostname = self._args.hostname
        # change default pool settings
        if self._args.pool_url:
            scheme, netloc = ([None] + self._args.pool_url.split('://', 1))[-2:]
            server, port = (netloc.rsplit(':', 1) + [None])[:2]
            self._config.miner.pool.host = '{}://{}'.format(scheme, server) if scheme else server
            if port:
                self._config.miner.pool.port = int(port)
        if self._args.pool_user:
            self._config.miner.pool.user = self._args.pool_user
        # change uEnv.txt configuration
        uenv = self._config.uenv
        for option in set(self._args.uenv or []):
            setattr(uenv, option, 'yes')
        # set feeds base index file
        if self._args.feeds_base:
            self._config.deploy.feeds_base = self._args.feeds_base

        # override default targets from command line
        if self._args.target:
            self._config.deploy.targets = miner.ConfigList()
            targets = self._config.deploy.targets
            local = self._config.local
            for target in self._args.target:
                target, path = (target.split(':', 1) + [None])[:2]
                targets.append(target)
                if path:
                    if not target.startswith('local_'):
                        logging.error("Target '{}' cannot have path specification".format(target))
                        raise miner.BuilderStop
                    target = target[6:]
                    if target in ['sd', 'sd_recovery']:
                        setattr(local, target + '_config', path)
                    setattr(local, target, path)

        builder = self.get_builder()
        builder.prepare()
        builder.deploy()

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

        if not self._args.no_fetch:
            # always fetch all repositories before creating release
            self._config.remote.fetch_always = 'yes'

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
    subparser.add_argument('--mac', nargs='?',
                           help='MAC address of miner (it is also used for remote host name determination)')
    subparser.add_argument('--hostname', nargs='?',
                           help='ip address or hostname of remote miner with ssh server')
    subparser.add_argument('--pool-url', nargs='?',
                           help='address of pool server in a format <host>[:<port>]')
    subparser.add_argument('--pool-user', nargs='?',
                           help='name of pool worker')
    subparser.add_argument('--uenv', choices=['mac', 'factory_reset', 'sd_images', 'sd_boot'], nargs='*',
                           help='enable some options in uEnv.txt for SD images')
    subparser.add_argument('--feeds-base', nargs='?',
                           help='path to the Packages file for concatenation with new feeds index '
                                '(for local_feeds target only)')
    subparser.add_argument('target', nargs='*',
                           help='list of targets for deployment (local target can specify also output directory '
                                'in a format <target>[:<path>])')

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
    subparser.add_argument('--no-fetch', action='store_true',
                           help='do not force fetching all repositories before creating release configuration')

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
