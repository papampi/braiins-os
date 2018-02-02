#!/usr/bin/python3

import sys
import argparse
import logging
import colorlog
import lede

# constant definitions
DEFAULT_CONFIG = 'configs/default.yml'


class CommandManager:
    def __init__(self):
        self._args = None
        self._builder = None

    def set_args(self, args):
        config = lede.load_config(args.config)
        self._args = args
        self._builder = lede.Builder(config)

    def prepare(self):
        logging.debug("Called command 'prepare'")
        self._builder.prepare(fetch=self._args.fetch)

    def clean(self):
        logging.debug("Called command 'clean'")
        purge = self._args.purge
        if purge:
            self._builder.clean(purge=True)
            self._builder.prepare()
        else:
            self._builder.prepare()
            self._builder.clean()

    def config(self):
        logging.debug("Called command 'config'")
        self._builder.prepare()
        self._builder.config(kernel=self._args.kernel)

    def build(self):
        logging.debug("Called command 'build'")
        self._builder.prepare()
        self._builder.build()

    def deploy(self):
        logging.debug("Called command 'deploy'")
        self._builder.prepare()
        self._builder.build()
        self._builder.deploy()

    def status(self):
        logging.debug("Called command 'status'")
        self._builder.status()

    def debug(self):
        logging.debug("Called command 'debug'")
        self._builder.prepare()
        self._builder.build()
        self._builder.debug()

    def toolchain(self):
        logging.debug("Called command 'toolchain'")
        self._builder.prepare()
        self._builder.toolchain()


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

    # create the parser for the "deploy" command
    subparser = subparsers.add_parser('deploy',
                                      help="deploy selected image to target device")
    subparser.set_defaults(func=command.deploy)

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

    # add global arguments
    parser.add_argument('--log', choices=['error', 'warn', 'info', 'debug'], default='info',
                        help='logging level')
    parser.add_argument('--config', default=DEFAULT_CONFIG,
                        help='path to configuration file')

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
    command.set_args(args)

    # call sub-command
    args.func()


if __name__ == "__main__":
    # execute only if run as a script
    try:
        main(sys.argv[1:])
    except lede.BuilderStop:
        sys.exit(1)
