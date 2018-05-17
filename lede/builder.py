import logging
import subprocess
import shutil
import tarfile
import gzip
import git
import io
import os
import sys

from collections import OrderedDict, namedtuple
from termcolor import colored
from functools import partial

from lede.config import ListWalker, RemoteWalker, load_config
from lede.repo import RepoProgressPrinter
from lede.ssh import SSHManager
from lede.packages import Packages


class BuilderStop(Exception):
    """
    Exception raised when builder detected error and stopped immediately.
    """
    pass


ImageSd = namedtuple('ImageSd', ['boot', 'uboot', 'fpga', 'kernel'])
ImageRecovery = namedtuple('ImageRecovery', ['boot', 'uboot', 'fpga', 'kernel', 'factory'])
ImageNand = namedtuple('ImageNand', ['boot', 'uboot', 'fpga', 'factory', 'sysupgrade'])
ImageInno = namedtuple('ImageInno', ['boot', 'uboot', 'fpga', 'kernel', 'kernel_recovery', 'factory'])
ImageFeeds = namedtuple('ImageFeeds', ['key', 'packages', 'sysupgrade'])


def get_stream_size(stream):
    stream_pos = stream.tell()
    stream_size = stream.seek(0, os.SEEK_END)
    stream.seek(stream_pos)
    return stream_size


def is_target_latest(src_path: str, dst_path: str) -> bool:
    """
    Check if target file is up-to-date with source file

    :param src_path:
        Path to source file.
    :param dst_path:
        Path to destination file.
    :return:
        True when destination file exists and its creatin time is not older then source file.
    """
    if not os.path.exists(dst_path):
        # destination file does not exists so source is newer
        return False
    src_time = os.path.getmtime(src_path)
    dst_time = os.path.getmtime(dst_path)
    return dst_time >= src_time


class Builder:
    """
    Main class for building the Miner firmware based on the LEDE (OpenWRT) project.

    It prepares the LEDE source code and all related projects.
    Then it is possible to configure the project and build the firmware.
    The class also provides miscellaneous methods for cleaning build directories, firmware deployment and debugging
    on target platform.
    """
    TARGET_ZYNQ_DM1_G9 = 'zynq-dm1-g9'
    TARGET_ZYNQ_DM1_G19 = 'zynq-dm1-g19'

    LEDE_META_DIR = 'lede'
    LEDE_META_SSH = 'ssh.py'
    LEDE_META_HWID = 'hwid.py'

    LEDE = 'lede'
    LUCI = 'luci'
    PLATFORM = 'platform'
    UBOOT = 'u-boot'
    LINUX = 'linux'
    CGMINER = 'cgminer'
    FEEDS_CONF_SRC = 'feeds.conf.default'
    FEEDS_CONF_DST = 'feeds.conf'
    CONFIG_NAME = '.config'
    BUILD_KEY_NAME = 'key-build'
    BUILD_KEY_PUB_NAME = 'key-build.pub'

    MINER_MAC = 'ethaddr'
    MINER_HWID = 'miner_hwid'
    MINER_FIRMWARE = 'firmware'
    MINER_ENV_SIZE = 0x20000
    MINER_CFG_SIZE = 0x20000

    UENV_TXT = 'uEnv.txt'

    MTD_BITSTREAM = 'fpga'

    INNO_VERSIONS=2
    INNO_DIR = 'inno'
    INNO_FIRMWARE_DIR = 'firmware'
    INNO_UBOOT_ENV = 'uboot_env.bin'
    INNO_UBOOT_ENV_CONFIG = 'uboot_env.config'
    INNO_UBOOT_ENV_SRC = 'uboot_env.txt'
    INNO_MINER_CFG = 'miner_cfg.bin'
    INNO_MINER_CFG_CONFIG = 'miner_cfg.config'
    INNO_UPGRADE_SCRIPT_SRC = 'upgrade_v{version}.py'
    INNO_UPGRADE_SCRIPT = 'upgrade.py'
    INNO_SCRIPT_REQUIREMENTS_SRC = 'requirements_v{version}.txt'
    INNO_SCRIPT_REQUIREMENTS = 'requirements.txt'
    INNO_STAGE1_CONTROL_SRC = 'CONTROL_v{version}'
    INNO_STAGE1_CONTROL = 'CONTROL'
    INNO_STAGE1_SCRIPT = 'stage1.sh'
    INNO_STAGE2_SCRIPT = 'stage2.sh'
    INNO_STAGE2 = 'stage2.tgz'

    # feeds index constants
    FEEDS_INDEX = 'Packages'
    FEEDS_ATTR_PACKAGE = 'Package'
    FEEDS_ATTR_FILENAME = 'Filename'
    FEEDS_EXCLUDED_ATTRIBUTES = ['Source', 'Maintainer']

    FEED_FIRMWARE = 'firmware'

    # list of supported utilities
    LEDE_MKENVIMAGE = 'mkenvimage'
    LEDE_USIGN = 'usign'

    LEDE_UTILITIES = {
        LEDE_MKENVIMAGE: os.path.join('build_dir', 'host', 'u-boot-2014.10', 'tools', 'mkenvimage'),
        LEDE_USIGN: os.path.join('staging_dir', 'host', 'bin', 'usign')
    }

    # configuration file constants
    CONFIG_DEVICES = ['nand', 'inno', 'recovery', 'sd']
    PACKAGE_LIST_PREFIX = 'image_'

    def _write_target_config(self, stream, config):
        """
        Write all settings concerning target configuration

        :param stream:
            Opened stream for writing configuration.
        :param config:
            Configuration name prefix.
        """
        image_packages = load_config(self._config.build.packages)

        platform = self._config.miner.platform
        target_name = platform.split('-', 1)[0]
        device_name = platform.replace('-', '_')
        bitstream_path = self._get_bitstream_path()

        stream.write('CONFIG_TARGET_{}=y\n'.format(target_name))
        stream.write('CONFIG_TARGET_{}=y\n'.format(device_name))
        stream.write('CONFIG_TARGET_MULTI_PROFILE=y\n')
        stream.write('CONFIG_TARGET_PER_DEVICE_ROOTFS=y\n')

        for image in self.CONFIG_DEVICES:
            packages = ' '.join(ListWalker(image_packages, self.PACKAGE_LIST_PREFIX + image))
            stream.write('CONFIG_TARGET_DEVICE_{}_DEVICE_{}=y\n'.format(device_name, image))
            stream.write('CONFIG_TARGET_DEVICE_PACKAGES_{}_DEVICE_{}="{}"\n'.format(device_name, image, packages))

        logging.debug("Set bitstream target path to '{}'".format(bitstream_path))
        stream.write('CONFIG_TARGET_FPGA="{}"\n'.format(bitstream_path))

    def _write_external_path(self, stream, config, repo_name: str, name: str):
        """
        Write absolute path to external directory of corespondent repository

        :param stream:
            Opened stream for writing configuration.
        :param config:
            Configuration name prefix.
        :param repo_name:
            Name of repository.
        :param name:
            Descriptive name of repository.
        :return:
            Absolute path to external directory.
        """
        external_dir = self._get_repo(repo_name).working_dir
        logging.debug("Set external {} tree to '{}'".format(name, external_dir))
        stream.write('{}="{}"\n'.format(config, external_dir))

    GENERATED_CONFIGS = [
        ('CONFIG_TARGET_', _write_target_config),
        ('CONFIG_EXTERNAL_KERNEL_TREE', partial(_write_external_path, repo_name=LINUX, name='kernel')),
        ('CONFIG_EXTERNAL_CGMINER_TREE', partial(_write_external_path, repo_name=CGMINER, name='CGMiner')),
        ('CONFIG_EXTERNAL_UBOOT_TREE', partial(_write_external_path, repo_name=UBOOT, name='U-Boot')),
        # remove all commented CONFIG_TARGET_
        ('# CONFIG_TARGET_', None)
    ]

    def __init__(self, config, argv):
        """
        Initialize builder for specific configuration

        :param config:
            Configuration object which has its attributes stored in dictionary or list.
            The key of dictionary can be also accessed as an object attribute.
        :param argv:
            Command line arguments for better help printing.
        """
        self._config = config
        self._argv = argv
        self._build_dir = os.path.join(os.path.abspath(config.build.dir), config.build.name)
        self._working_dir = None
        self._repos = OrderedDict()
        self._init_repos()

    def _run(self, *args, path=None, input=None, output=False, init=None):
        """
        Run system command in LEDE source directory

        The running environment is checked and when system command returns error it throws an exception.
        Two key arguments are supported. The `path` is for altering PATH environment variable and the `output`
        specifies if stdout is captured and returned by this method.

        :param args:
            First item is a command executed in the LEDE source directory.
            Remaining items are passed into the program as arguments.
            If args[0] is a list then this list is used instead of args.

            This allows use method in two forms:

            - `self._run([cmd, arg1, arg2])`
            - `self._run(cmd, arg1, arg2)`.
        :param path:
            List of directories prepended to PATH environment variable.
        :param input:
            A string which is passed to the subprocess's stdin.
        :param output:
            If true then method returns captured stdout otherwise stdout is printed to standard output.
        :param init:
            An object to be called in the child process just before the child is executed.
        :return:
            Captured stdout when `output` argument is set to True.
        """
        env = None
        cwd = self._working_dir
        stdout = subprocess.PIPE if output else None

        if path:
            env = os.environ.copy()
            env['PATH'] = ':'.join((*path, env['PATH']))
        if type(args[0]) is list:
            args = args[0]
        if path:
            logging.debug("Set PATH environment variable to '{}'".format(env['PATH']))

        logging.debug("Run '{}' in '{}'".format(' '.join(args), cwd))

        process = subprocess.run(args, input=input, stdout=stdout, check=True, cwd=cwd, env=env, preexec_fn=init)
        if output:
            return process.stdout

    def _get_repo(self, name: str) -> git.Repo:
        """
        Return git repository by its name

        :param name: The name of repository as it has been specified in configuration file.
        :return: Associated git repository or raise exception if the repository does not exist.
        """
        return self._repos[name]

    def _get_repo_path(self, name: str) -> str:
        """
        Return absolute path to repository specified by its name

        :param name: The name of repository as it has been specified in configuration file.
        :return: Absolute path to the repository.
        """
        return os.path.join(self._build_dir, name)

    def _get_config_paths(self):
        """
        Return absolute paths to default and current configuration file

        - `default` configuration file points to a file specified in `build.config`
        - `current` configuration file points to a file in LEDE build directory

        :return:
            Pair of absolute paths to default and current configuration file.
        """
        lede_dir = self._get_repo(self.LEDE).working_dir
        config_src_path = os.path.abspath(self._config.build.config)
        config_dst_path = os.path.join(lede_dir, self.CONFIG_NAME)
        return config_src_path, config_dst_path

    def _use_glibc(self):
        """
        Check if glibc is used for build

        :return:
            True when configuration file is set for use of glibc.
        """
        config_path, _ = self._get_config_paths()
        with open(config_path, 'r') as config:
            return any((line.startswith('CONFIG_LIBC="glibc"') for line in config))

    def _get_hostname(self) -> str:
        """
        Return hostname derived from miner MAC address

        :return:
            Miner hostname for current configuration.
        """
        mac = self._config.miner.mac
        return 'miner-' + ''.join(mac.split(':')[-3:]).lower()

    def _get_utility(self, name: str):
        """
        Return LEDE utility when it exists or raise an exception

        :param name:
            Name of LEDE utility.
        :return:
            Path to specified LEDE utility.
        """
        utility_path = os.path.join(self._working_dir, self.LEDE_UTILITIES[name])
        if not os.path.exists(utility_path):
            logging.error("Missing utility '{}'".format(utility_path))
            raise BuilderStop
        return utility_path

    def _init_repos(self):
        """
        Initialize all repositories specified in configuration file

        The list of repositories is stored under `remote.repos`.

        If repository is not cloned yet then None is used otherwise the repository is opened by `git.Repo`.
        """
        error = False
        for name in self._config.remote.repos:
            path = self._get_repo_path(name)
            logging.debug("Init repo '{}' in '{}'".format(name, path))
            repo = None
            try:
                repo = git.Repo(path)
            except git.exc.NoSuchPathError:
                logging.debug("Missing directory '{}'".format(path))
            except git.exc.InvalidGitRepositoryError:
                if os.listdir(path):
                    logging.error("Invalid Git repository '{}'".format(path))
                    error = True
                else:
                    logging.warning("Empty Git repository '{}'".format(path))
            self._repos[name] = repo
        if error:
            raise BuilderStop

    def _prepare_repo(self, remote):
        """
        Prepare one remote repository for use

        It clones or fetches latest changes from remote repository.
        The fetch can be altered by user in configuration file or from command line.
        When current branch differs from specified one it allow switching branches.

        :param remote:
            Named tuple where following attributes are used:

            - `name` - name of repository
            - `uri` - address of remote git repository
            - `branch` - name of branch
            - `fetch` - if True then fetch+merge is done
        """
        name = remote.name
        path = self._get_repo_path(name)
        repo = self._repos[name]
        logging.debug("Start preparing remote '{}' in '{}'".format(name, path))
        if not repo:
            logging.info("Cloning remote '{}'".format(name))
            repo = git.Repo.clone_from(remote.uri, path, branch=remote.branch,
                                       progress=RepoProgressPrinter())
            self._repos[name] = repo
        elif remote.fetch:
            logging.info("Fetching remote '{}'".format(name))
            for repo_remote in repo.remotes:
                repo_remote.fetch()
        if remote.branch not in repo.heads:
            for repo_remote in repo.remotes:
                if remote.branch in repo_remote.refs:
                    ref = repo_remote.refs[remote.branch]
                    repo.create_head(remote.branch, ref).set_tracking_branch(ref)
                    break
            else:
                logging.error("Branch '{}' does not exist".format(remote.branch))
                raise BuilderStop
        branch = repo.heads[remote.branch]
        if repo.active_branch != branch:
            branch.checkout()
        if remote.fetch:
            for repo_remote in repo.remotes:
                repo_remote.pull()

    def _prepare_feeds(self):
        """
        Prepare LEDE feeds

        It creates `feeds.conf` when it is not present and then calls

        - `./scripts/feeds update -a`
        - `./scripts/feeds install -a`
        """
        logging.info("Preparing feeds...")
        lede_dir = self._working_dir
        luci_dir = self._get_repo(self.LUCI).working_dir
        feeds_src_path = os.path.join(lede_dir, self.FEEDS_CONF_SRC)
        feeds_dst_path = os.path.join(lede_dir, self.FEEDS_CONF_DST)

        feeds_create = self._config.feeds.create_always == 'yes'
        feeds_update = self._config.feeds.update_always == 'yes'
        feeds_install = self._config.feeds.install_always == 'yes'

        if not os.path.exists(feeds_dst_path) or feeds_create:
            logging.debug("Creating '{}'".format(feeds_dst_path))
            feeds_update = True
            feeds_install = True
            with open(feeds_src_path, 'r') as feeds_src, open(feeds_dst_path, 'w') as feeds_dst:
                for line in feeds_src:
                    if self.LUCI not in line:
                        feeds_dst.write(line)
                # create link to LUCI in feeds configuration file
                feeds_dst.write('src-link {} {}\n'.format(self.LUCI, luci_dir))

        if feeds_update:
            logging.debug('Updating feeds')
            self._run(os.path.join('scripts', 'feeds'), 'update', '-a')
        if feeds_install:
            logging.debug('Installing feeds')
            self._run(os.path.join('scripts', 'feeds'), 'install', '-a')

    def _prepare_config(self):
        """
        Prepare LEDE configuration file

        It sets default configuration specified in the configuration file under `build.config`.
        It also sets paths to Linux and CGMiner external directories in this configuration file.
        """
        logging.info("Preparing config...")

        config_src_path, config_dst_path = self._get_config_paths()

        config_copy = self._config.build.config_always == 'yes'
        default_config = not os.path.exists(config_dst_path)

        if default_config:
            logging.debug("Creating default configuration")
            self._run('make', 'defconfig')

        if default_config or not is_target_latest(config_src_path, config_dst_path) or config_copy:
            logging.debug("Copy config from '{}'".format(config_src_path))
            shutil.copy(config_src_path, config_dst_path)

            with open(config_dst_path, 'a') as config_dst:
                # set paths to Linux and CGMiner external directories
                for config, generator in self.GENERATED_CONFIGS:
                    generator and generator(self, config_dst, config)
            logging.debug("Creating full configuration file")
            self._run('make', 'defconfig')

    def _prepare_keys(self):
        """
        Prepare LEDE build keys

        The keys are used for signing packages and sysupgrade tarball.
        When configuration does not contain any key then LEDE generates new one.
        """
        build_key = self._config.build.get('key', None)

        if not build_key:
            # missing build key
            return

        logging.info("Preparing build key...")

        lede_dir = self._get_repo(self.LEDE).working_dir
        key1_src_path = build_key.secret
        key2_src_path = build_key.public
        key1_dst_path = os.path.join(lede_dir, self.BUILD_KEY_NAME)
        key2_dst_path = os.path.join(lede_dir, self.BUILD_KEY_PUB_NAME)

        if not is_target_latest(key1_src_path, key1_dst_path):
            logging.debug("Copy secret build key from '{}'".format(key1_src_path))
            shutil.copy(key1_src_path, key1_dst_path)

        if not is_target_latest(key2_src_path, key2_dst_path):
            logging.debug("Copy public build key from '{}'".format(key2_src_path))
            shutil.copy(key2_src_path, key2_dst_path)

    def _config_lede(self):
        """
        Configure LEDE project

        It calls `make menuconfig` and then stores configuration diff to the file specified in `build.config`.
        """
        config_dst_path, config_src_path = self._get_config_paths()

        config_src_time = os.path.getmtime(config_src_path)
        self._run('make', 'menuconfig')
        if os.path.getmtime(config_src_path) == config_src_time:
            logging.info("Configuration file has not been changed")
            return

        logging.info("Saving changes in configuration to '{}'...".format(config_dst_path))
        with open(config_dst_path, 'w') as config_dst:
            # call ./scripts/diffconfig.sh to get configuration diff
            output = self._run(os.path.join('scripts', 'diffconfig.sh'), output=True)
            for line in output.decode('utf-8').splitlines():
                # do not store lines with configuration of external directories
                # this files are automatically generated
                if not any(line.startswith(config) for config, _ in self.GENERATED_CONFIGS):
                    config_dst.write(line)
                    config_dst.write('\n')

    def _config_kernel(self):
        """
        Configure Linux kernel

        It calls `make kernel_menuconfig`. The configuration is stored in the target directory of the LEDE build system.
        """
        self._run('make', 'kernel_menuconfig')

    def prepare(self, fetch: bool=False):
        """
        Prepare all projects and configure the LEDE build system.

        :param fetch:
            If True then override configuration file and force fetch all repositories.
        """
        logging.info("Preparing build directory...'")
        if not os.path.exists(self._build_dir):
            logging.debug("Creating build directory '{}'".format(self._build_dir))
            os.makedirs(self._build_dir)
        for remote in RemoteWalker(self._config.remote, fetch):
            self._prepare_repo(remote)

        # set working directory to LEDE root directory
        self._working_dir = self._get_repo(self.LEDE).working_dir

        self._prepare_feeds()
        self._prepare_config()
        self._prepare_keys()

    def clean(self, purge: bool=False):
        """
        Clean all projects or purge them to initial state.

        :param purge:
            If True then use git to clean the whole repository to its initial state.
        """
        logging.info("Start cleaning LEDE build directory...'")
        if not purge:
            self._run('make', 'clean')
        else:
            for name, repo in self._repos.items():
                if not repo:
                    continue
                logging.debug("Purging '{}'".format(name))
                repo.git.clean('-dxf')

    def config(self, kernel: bool=False):
        """
        Configure LEDE project or Linux kernel

        :param kernel:
            If True then Linux kernel configuration is called instead of LEDE configuration.
        """
        if not kernel:
            logging.info("Start LEDE configuration...'")
            self._config_lede()
        else:
            logging.info("Start Linux kernel configuration...'")
            self._config_kernel()

    def build(self, targets=None, jobs=None, verbose=False):
        """
        Build the Miner firmware for current configuration

        It is possible alter build system by following attributes in configuration file:

        - `build.jobs` - number of jobs to run simultaneously (default is `1`)
        - `build.debug` - show all commands during build process (default is `no`)

        :param targets:
            List of targets for build. Target is specified as an alias to real LEDE target.
            The aliases are stored in configuration file under `build.aliases`
        :param jobs:
            Specifies the number of jobs (commands) to run simultaneously.
        :param verbose:
            Force to show all commands called from make build system.
        """
        logging.info("Start building LEDE...'")
        jobs = jobs or self._config.build.get('jobs', 1)
        verbose = verbose or self._config.build.get('verbose', 'no') == 'yes'

        # set PATH environment variable
        env_path = self._config.build.get('env_path', None)
        path = env_path and [os.path.abspath(os.path.expanduser(env_path))]

        # prepare arguments for build
        args = ['make', '-j{}'.format(jobs)]
        if verbose:
            args.append('V=s')
        if targets:
            aliases = self._config.build.aliases
            args.extend('{}/install'.format(aliases[target]) for target in targets)
        # run make to build whole LEDE
        # set umask to 0022 to fix issue with incorrect root fs access rights
        self._run(args, path=path, init=partial(os.umask, 0o0022))

    def _write_uenv(self, stream, recovery: bool=False):
        """
        Generate content of uEnv.txt to the file stream

        :param stream:
            File stream with write access.
        :param recovery:
            Write also recovery parameters.
        """
        if self._config.uenv.get('mac', 'no') == 'yes':
            stream.write("{}={}\n".format(self.MINER_MAC, self._config.miner.mac))

        bool_attributes = (
            'factory_reset',
            'sd_images',
            'sd_boot'
        )
        for attribute in bool_attributes:
            if self._config.uenv.get(attribute, 'no') == 'yes':
                stream.write("{}=yes\n".format(attribute))

    def _mtd_write(self, ssh, image_path: str, device: str, offset: int=0, compress: bool=False, erase: bool=True):
        """
        Write image to remote NAND partition

        :param ssh:
            Connected SSH client.
        :param image_path:
            Path to local image file.
        :param device:
            Name of NAND partition for writing image.
        :param offset:
            Skip the first n bytes.
        :param compress:
            Compress data with gzip before write to NAND.
        :param erase:
            Write first erasing the blocks.
        """
        command = ['mtd']
        if not erase:
            command.append('-n')
        if offset:
            command.extend(('-p', str(offset)))
        command.extend(('write', '-', device))
        with open(image_path, "rb") as image_file, ssh.pipe(command) as remote:
            if compress:
                remote.stdin.write(gzip.compress(image_file.read()))
            else:
                shutil.copyfileobj(image_file, remote.stdin)

    def _get_bitstream_mtd_name(self, index) -> str:
        """
        Return MTD device name for selected firmware

        :param index:
            Index of firmware partition.
        :return:
            String with name of MTD device.
        """
        return self.MTD_BITSTREAM + str(index)

    def _get_bitstream_path(self, platform: str=None) -> str:
        """
        Return path to FPGA bitstream for selected platform

        :param platform:
            Name of selected platform.
            When platform is omitted then platform from current configuration is used.
        :return:
            String with path to FPGA bitstream.
        """
        bitstream = {
            self.TARGET_ZYNQ_DM1_G9: os.path.join('g9', 'bin', 'system.bit'),
            self.TARGET_ZYNQ_DM1_G19: os.path.join('g19', 'bin', 'system.bit')
        }
        platform_dir = self._get_repo(self.PLATFORM).working_dir
        platform = platform or self._config.miner.platform
        return os.path.join(platform_dir, bitstream[platform])

    @staticmethod
    def _get_firmware_mtd(index) -> str:
        """
        Return MTD device for selected firmware

        :param index:
            Index of firmware partition.
        :return:
            String with path to MTD device.
        """
        return '/dev/mtd' + {1: '7', 2: '8'}.get(index)

    def _get_hw_version(self) -> str:
        """
        Return hardware version for selected platform
        :return:
            String with hardware version.
        """
        return '-'.join(self._config.miner.platform.split('-')[1:])

    def _write_nand_uboot(self, ssh, image):
        """
        Write SPL and U-Boot to NAND over SSH connection

        :param ssh:
            Connected SSH client.
        :param image:
            Paths to firmware images.
        """
        boot_images = (
            (image.boot, 'boot'),
            (image.uboot, 'uboot')
        )
        for local, mtd in boot_images:
            logging.info("Writing '{}' to NAND partition '{}'...".format(os.path.basename(local), mtd))
            self._mtd_write(ssh, local, mtd)

    def _upload_images(self, upload_manager, image, recovery: bool=False, compressed=()):
        """
        Upload all image files using upload manager

        :param upload_manager:
            Upload manager for images transfer.
        :param image:
            Paths to firmware images.
        :param recovery:
            Transfer recovery images.
        :param compressed:
            List of images which should be compressed.
        """
        upload = [
            (image.boot, 'boot.bin'),
            (image.uboot, 'u-boot.img'),
            (image.fpga, 'system.bit'),
            (image.kernel, 'fit.itb')
        ]
        if recovery:
            upload.append((image.factory, 'factory.bin'))

        for local, remote in upload:
            compress = remote in compressed
            if compress:
                remote += '.gz'
            upload_manager.put(local, remote, compress)

    def _deploy_ssh_sd(self, ssh, sftp, image, recovery: bool):
        """
        Deploy image to the SD card over SSH connection

        :param ssh:
            Connected SSH client.
        :param sftp:
            Opened SFTP connection by SSH client.
        :param image:
            Paths to firmware images.
        :param recovery:
            Transfer recovery images.
        """
        class UploadManager:
            def __init__(self, sftp):
                self.sftp = sftp

            def put(self, src, dst, compress=False):
                logging.info("Uploading '{}'...".format(dst))
                self.sftp.put(src, dst)

        ssh.run('mount', '/dev/mmcblk0p1', '/mnt')
        sftp.chdir('/mnt')

        # start uploading
        self._upload_images(UploadManager(sftp), image, recovery)

        ssh.run('umount', '/mnt')

    def _deploy_ssh_nand_recovery(self, ssh, image):
        """
        Deploy image to the NAND recovery over SSH connection

        It is required that remote system has been booted from SD card or recovery partition!

        :param ssh:
            Connected SSH client.
        :param image:
            Paths to firmware images.
        """
        mtd_name = 'recovery'

        self._write_nand_uboot(ssh, image)

        # erase device before formating
        ssh.run('mtd', 'erase', mtd_name)

        local = image.kernel
        logging.info("Writing '{}' to NAND partition '{}'..."
                     .format(os.path.basename(local), mtd_name))
        self._mtd_write(ssh, local, mtd_name)

        local = image.factory
        logging.info("Writing '{}' to NAND partition '{}'..."
                     .format(os.path.basename(local), mtd_name))
        self._mtd_write(ssh, local, mtd_name, offset=0x800000, compress=True, erase=False)

        local = image.fpga
        logging.info("Writing '{}' to NAND partition '{}'..."
                     .format(os.path.basename(local), mtd_name))
        self._mtd_write(ssh, local, mtd_name, offset=0x1400000, compress=True, erase=False)

    def _deploy_ssh_nand(self, ssh, image):
        """
        Deploy image to the NAND over SSH connection

        It is required that remote system has been booted from SD card or recovery partition!

        :param ssh:
            Connected SSH client.
        :param image:
            Paths to firmware images.
        """
        platform = self._config.miner.platform

        self._write_nand_uboot(ssh, image)

        firmwares = (
            ('nand_firmware1', 1),
            ('nand_firmware2', 2)
        )
        targets = self._config.deploy.targets

        if self._config.deploy.write_bitstream == 'yes':
            mtds = (self._get_bitstream_mtd_name(i) for name, i in firmwares if name in targets)
            for mtd_name in mtds:
                logging.info("Writing bitstream for platform '{}' to NAND partition '{}'..."
                             .format(platform, mtd_name))
                self._mtd_write(ssh, image.fpga, mtd_name, compress=True)

        mtds = ((name[5:], self._get_firmware_mtd(i)) for name, i in firmwares if name in targets)
        for firmware, mtd in mtds:
            if self._config.deploy.factory_image == 'yes':
                logging.info("Formating '{}' ({}) with 'factory.bin'...".format(firmware, mtd))
                # erase device before formating
                ssh.run('mtd', 'erase', mtd)
                # use factory image which deletes overlay data from UBIFS
                image_size = os.path.getsize(image.factory)
                with open(image.factory, "rb") as image_file:
                    with ssh.pipe('ubiformat', mtd, '-f', '-', '-S', str(image_size)) as remote:
                        shutil.copyfileobj(image_file, remote.stdin)
            else:
                logging.info("Updating '{}' ({}) volumes with 'sysupgrade.tar'...".format(firmware, mtd))
                # use sysupgrade image which preserves overlay data from UBIFS
                ssh.run('ubiattach', '-p', mtd)
                volume_images = (
                    ('kernel', 'sysupgrade-miner-nand/kernel', '/dev/ubi0_0'),
                    ('rootfs', 'sysupgrade-miner-nand/root', '/dev/ubi0_1')
                )
                for volume_name, volume_image, device in volume_images:
                    logging.info("Updating volume '{}' ({}) with '{}'...".format(volume_name, device, volume_image))
                    with tarfile.open(image.sysupgrade, 'r') as sysupgrade_file:
                        image_info = sysupgrade_file.getmember(volume_image)
                        image_file = sysupgrade_file.extractfile(image_info)
                        with ssh.pipe('ubiupdatevol', device, '-', '-s', str(image_info.size)) as remote:
                            shutil.copyfileobj(image_file, remote.stdin)
                ssh.run('ubidetach', '-p', mtd)

    def _config_ssh_sd(self, ssh, sftp, recovery: bool):
        """
        Change configuration on SD card over SSH connection

        :param ssh:
            Connected SSH client.
        :param sftp:
            Opened SFTP connection by SSH client.
        :param recovery:
            Use options for recovery image.
        """
        reset_extroot = self._config.deploy.reset_extroot == 'yes'
        remove_extroot_uuid = self._config.deploy.remove_extroot_uuid == 'yes'

        # create uEnv.txt for U-Boot external configuration
        ssh.run('mount', '/dev/mmcblk0p1', '/mnt')
        sftp.chdir('/mnt')

        logging.info("Creating '{}'...".format(self.UENV_TXT))
        with sftp.open(self.UENV_TXT, 'w') as file:
            self._write_uenv(file, recovery)

        ssh.run('umount', '/mnt')

        # delete the whole extroot or delete extroot UUID
        if reset_extroot or remove_extroot_uuid:
            ssh.run('mount', '/dev/mmcblk0p2', '/mnt')
            sftp.chdir('/mnt')

            if reset_extroot:
                logging.info("Removing all data from extroot...")
                ssh.run('rm', '-fr', '/mnt/*')
            elif '.extroot-uuid' in sftp.listdir('etc'):
                logging.info("Removing extroot UUID...")
                sftp.remove('etc/.extroot-uuid')

            ssh.run('umount', '/mnt')

    def _config_ssh_nand(self, ssh):
        """
        Change configuration on NAND over SSH connection

        :param ssh:
            Connected SSH client.
        """
        # write miner configuration to miner_cfg NAND
        if self._config.deploy.write_miner_cfg == 'yes':
            mkenvimage = self._get_utility(self.LEDE_MKENVIMAGE)
            input = '{}={}\n' \
                    '{}={}\n' \
                    ''.format(self.MINER_MAC, self._config.miner.mac,
                              self.MINER_HWID, self._config.miner.hwid)
            output = self._run(mkenvimage, '-r', '-p', str(0), '-s', str(self.MINER_CFG_SIZE), '-',
                               input=input.encode(), output=True)
            logging.info("Writing miner configuration to NAND partition 'miner_cfg'...")
            with ssh.pipe('mtd', 'write', '-', 'miner_cfg') as remote:
                remote.stdin.write(output)

        # change miner configuration in U-Boot env
        if self._config.deploy.set_miner_env == 'yes' and self._config.deploy.reset_uboot_env == 'no':
            logging.info("Writing miner configuration to U-Boot env in NAND...")
            ssh.run('fw_setenv', self.MINER_MAC, self._config.miner.mac)
            ssh.run('fw_setenv', self.MINER_HWID, self._config.miner.hwid)
            ssh.run('fw_setenv', self.MINER_FIRMWARE, str(self._config.miner.firmware))

        reset_uboot_env = self._config.deploy.reset_uboot_env == 'yes'
        reset_overlay = self._config.deploy.reset_overlay == 'yes'

        ubi_attach = reset_overlay

        if ubi_attach:
            firmware_mtd = self._get_firmware_mtd(self._config.miner.firmware)
            ssh.run('ubiattach', '-p', firmware_mtd)

        if reset_uboot_env:
            logging.info("Erasing NAND partition 'uboot_env'...")
            ssh.run('mtd', 'erase', 'uboot_env')

        # truncate overlay for current firmware
        if reset_overlay:
            logging.info("Truncating UBI volume 'rootfs_data'...")
            ssh.run('ubiupdatevol', '/dev/ubi0_2', '-t')

        if ubi_attach:
            ssh.run('ubidetach', '-p', firmware_mtd)

    def _deploy_ssh(self, images, sd_config: bool, nand_config: bool):
        """
        Deploy NAND or SD card image over SSH connection

        It can also change configuration in NAND and SD card.

        :param images:
            List of images for deployment.
            It is also possible to provide empty list and alter only miner configuration:

            - change MAC and HW ID in U-Boot env
            - erase NAND partitions to set it to the default state
            - remove extroot UUID
            - overwrite miner configuration with new MAC or HW ID
        :param sd_config:
            Modify configuration files on SD card.
        :param nand_config:
            Modify configuration files/partitions on NAND.
        """
        hostname = self._config.deploy.ssh.get('hostname', None)
        password = self._config.deploy.ssh.get('password', None)
        username = self._config.deploy.ssh.username

        if not hostname:
            # when hostname is not set, use standard name derived from MAC address
            hostname_suffix = self._config.deploy.ssh.get('hostname_suffix', '')
            hostname = self._get_hostname() + hostname_suffix

        with SSHManager(hostname, username, password) as ssh:
            sftp = ssh.open_sftp()

            image_sd = images.get('sd')
            image_nand_recovery = images.get('nand_recovery')
            image_nand = images.get('nand')

            sd_recovery = image_sd and isinstance(image_sd, ImageRecovery)

            if image_sd:
                self._deploy_ssh_sd(ssh, sftp, image_sd, sd_recovery)
            if sd_config:
                self._config_ssh_sd(ssh, sftp, sd_recovery)
            if image_nand_recovery:
                self._deploy_ssh_nand_recovery(ssh, image_nand_recovery)
            if image_nand:
                self._deploy_ssh_nand(ssh, image_nand)
            if nand_config:
                self._config_ssh_nand(ssh)

            # reboot system if requested
            if self._config.deploy.reboot == 'yes':
                ssh.run('reboot')

            sftp.close()

    def _get_local_target_dir(self, dir_name: str):
        """
        Return path to local target directory

        :param dir_name:
            Name of target directory.
        :return:
            Path to target directory.
        """
        target_dir = self._config.local.get(dir_name, None)
        if not target_dir:
            logging.error("Missing path for local target '{}'".format(dir_name))
            raise BuilderStop

        # prepare target directory
        target_dir = os.path.abspath(target_dir)
        if not os.path.exists(target_dir):
            os.makedirs(target_dir)
        return target_dir

    def _write_local_uenv(self, dir_name: str, recovery: bool=False):
        """
        Create uEnv.txt file in target directory with specific parameters

        :param dir_name:
            Name of target directory.
        :param recovery:
            Write also recovery parameters.
        """
        target_dir = self._get_local_target_dir(dir_name)
        with open(os.path.join(target_dir, self.UENV_TXT), 'w') as target_file:
            logging.info("Creating '{}' in '{}'...".format(self.UENV_TXT, target_dir))
            self._write_uenv(target_file, recovery)

    @staticmethod
    def _get_project_file(*path):
        """
        Return absolute path to the file from project directory

        :param name:
            Relative path to the file.
        :return:
            Path to the file from project directory.
        """
        return os.path.abspath(os.path.join(*path))

    def _create_inno_uboot_env(self):
        """
        Create U-Boot environment for converted Inno firmware

        :return:
            Bytes stream with U-Boot environment.
        """
        mkenvimage = self._get_utility(self.LEDE_MKENVIMAGE)
        uboot_env_src = self._get_project_file(self.INNO_DIR, self.INNO_UBOOT_ENV_SRC)

        return io.BytesIO(
            self._run(mkenvimage, '-r', '-p', str(0), '-s', str(self.MINER_ENV_SIZE),
                      uboot_env_src, output=True)
        )

    def _create_inno_miner_cfg(self):
        """
        Create empty miner configuration environment

        :return:
            Bytes stream with miner configuration environment.
        """
        mkenvimage = self._get_utility(self.LEDE_MKENVIMAGE)

        return io.BytesIO(
            self._run(mkenvimage, '-r', '-p', str(0), '-s', str(self.MINER_CFG_SIZE), '-',
                      input=''.encode(), output=True)
        )

    def _add2tar_compressed_file(self, tar, file_path, arcname):
        """
        Add to opened tar compressed file

        :param tar:
            Opened tar for writing.
        :param file_path:
            Path to uncompressed file.
        :param arcname:
            Name of file in the archive.
        """
        file_info = tar.gettarinfo(file_path, arcname=arcname)

        with open(file_path, "rb") as image_file:
            compressed_file = gzip.compress(image_file.read())
            file_info.size = len(compressed_file)
            compressed_file = io.BytesIO(compressed_file)

        tar.addfile(file_info, compressed_file)

    def _create_inno_stage2(self, image):
        """
        Create tarball with images for stage2 upgrade

        :param image:
            Paths to firmware images.
        """
        logging.info("Creating inno stage2 tarball...")

        stage2 = io.BytesIO()
        tar = tarfile.open(mode = "w:gz", fileobj=stage2)

        # add recovery image
        tar.add(image.kernel_recovery, arcname='fit.itb')

        # add compressed system.bin and factory.bin
        self._add2tar_compressed_file(tar, image.fpga, 'system.bit.gz')
        self._add2tar_compressed_file(tar, image.factory, 'factory.bin.gz')

        # add miner_cfg.config file
        miner_cfg_config = self._get_project_file(self.INNO_DIR, self.INNO_MINER_CFG_CONFIG)
        tar.add(miner_cfg_config, self.INNO_MINER_CFG_CONFIG)

        # add miner configuration environment compatible with U-Boot
        miner_cfg = self._create_inno_miner_cfg()
        miner_cfg_info = tar.gettarinfo(miner_cfg_config, arcname=self.INNO_MINER_CFG)
        miner_cfg_info.size = get_stream_size(miner_cfg)
        tar.addfile(miner_cfg_info, miner_cfg)

        # add upgrade script
        upgrade = self._get_project_file(self.INNO_DIR, self.INNO_STAGE2_SCRIPT)
        tar.add(upgrade, self.INNO_STAGE2_SCRIPT)

        tar.close()
        stage2.seek(0)
        return stage2

    def _create_inno_stage1_control(self, version: int):
        """
        Create script with variables for stage1 upgrade script

        :param version:
            Version of target firmware.
        :return:
            Opened stream with generated script.
        """
        control_path = self._get_project_file(self.INNO_DIR, self.INNO_STAGE1_CONTROL_SRC.format(version=version))
        info = io.BytesIO()

        hwver = {
            'zynq-dm1-g9': 'G9',
            'zynq-dm1-g19': 'G19'
        }.get(self._config.miner.platform)
        info.write('FW_MINER_HWVER={}\n\n'.format(hwver).encode())

        with open(control_path, 'rb') as control_file:
            shutil.copyfileobj(control_file, info)

        info.seek(0)
        return info

    def _deploy_local_inno(self, upload_manager, image, version: int):
        """
        Deploy NAND or SD card image for Inno upgrade to local file system

        :param version:
            Version of target firmware.
        :param upload_manager:
            Upload manager for images transfer.
        :param image:
            Paths to firmware images.
        """
        # copy all files for transfer to subdirectory
        target_dir = upload_manager.target_dir
        upload_manager.target_dir = os.path.join(target_dir, self.INNO_FIRMWARE_DIR)
        os.makedirs(upload_manager.target_dir, exist_ok=True)

        self._upload_images(upload_manager, image, compressed=('system.bit',))

        # copy uboot_env.config file
        uboot_env_config = self._get_project_file(self.INNO_DIR, self.INNO_UBOOT_ENV_CONFIG)
        upload_manager.put(uboot_env_config, self.INNO_UBOOT_ENV_CONFIG)

        # create U-Boot environment
        uboot_env = self._create_inno_uboot_env()
        upload_manager.put(uboot_env, self.INNO_UBOOT_ENV)

        # create tar with images for stage2 upgrade
        stage2 = self._create_inno_stage2(image)
        upload_manager.put(stage2, self.INNO_STAGE2)

        # create env.sh with script variables
        stage1_env = self._create_inno_stage1_control(version)
        upload_manager.put(stage1_env, self.INNO_STAGE1_CONTROL)

        # copy stage1 upgrade script
        upgrade = self._get_project_file(self.INNO_DIR, self.INNO_STAGE1_SCRIPT)
        upload_manager.put(upgrade, self.INNO_STAGE1_SCRIPT)

        # change to original target directory
        upload_manager.target_dir = target_dir

        # copy upgrade script for deployment
        if version == 2:
            ssh = self._get_project_file(self.LEDE_META_DIR, self.LEDE_META_SSH)
            upload_manager.put(ssh, self.LEDE_META_SSH)
        ssh = self._get_project_file(self.LEDE_META_DIR, self.LEDE_META_HWID)
        upload_manager.put(ssh, self.LEDE_META_HWID)
        upgrade = self._get_project_file(self.INNO_DIR, self.INNO_UPGRADE_SCRIPT_SRC.format(version=version))
        requirements = self._get_project_file(self.INNO_DIR, self.INNO_SCRIPT_REQUIREMENTS_SRC.format(version=version))
        upload_manager.put(upgrade, self.INNO_UPGRADE_SCRIPT)
        upload_manager.put(requirements, self.INNO_SCRIPT_REQUIREMENTS)

    def _deploy_local(self, images, sd_config: bool, sd_recovery_config: bool):
        """
        Deploy NAND or SD card image to local file system

        It can also generate configuration files for SD card version.

        :param images:
            List of images for deployment.
        :param sd_config:
            Generate configuration files for SD card version.
        :param sd_recovery_config:
            Generate configuration files for recovery SD card version.
        """
        class UploadManager:
            def __init__(self, target_dir: str):
                self.target_dir = target_dir

            def put(self, src, dst, compress=False):
                logging.info("Copying '{}' to '{}'...".format(dst, self.target_dir))
                src_path = type(src) is str
                src_file = open(src, 'rb') if src_path else src
                dst_open = open if not compress else gzip.open
                with dst_open(os.path.join(self.target_dir, dst), 'wb') as dst_file:
                    shutil.copyfileobj(src_file, dst_file)
                if src_path:
                    src_file.close()

        image_sd = images.get('sd')
        image_sd_recovery = images.get('sd_recovery')
        image_nand_recovery = images.get('nand_recovery')

        if image_sd:
            target_dir = self._get_local_target_dir('sd')
            self._upload_images(UploadManager(target_dir), image_sd)
        if sd_config:
            self._write_local_uenv('sd_config')
        if image_sd_recovery:
            target_dir = self._get_local_target_dir('sd_recovery')
            self._upload_images(UploadManager(target_dir), image_sd_recovery, recovery=True)
        if sd_recovery_config:
            self._write_local_uenv('sd_recovery_config', recovery=True)

        if image_nand_recovery:
            target_dir = self._get_local_target_dir('nand_recovery')
            self._upload_images(UploadManager(target_dir), image_nand_recovery, recovery=True)

        # special local target for upgrading original firmware of specific version
        for version in range(1, self.INNO_VERSIONS + 1):
            target_name = 'nand_inno_v{}'.format(version)
            image_nand_inno = images.get(target_name)
            if image_nand_inno:
                target_dir = self._get_local_target_dir(target_name)
                self._deploy_local_inno(UploadManager(target_dir), image_nand_inno, version)

    def _deploy_feeds(self, images):
        """
        Deploy package feeds to local file system

        :param images:
            List of images for deployment.
        """
        local_feeds = images.get('local')
        target_dir = self._get_local_target_dir('feeds')

        src_feeds_index = os.path.join(local_feeds.packages, self.FEEDS_INDEX)
        dst_feeds_index = os.path.join(target_dir, self.FEEDS_INDEX)

        # find package firmware meta information
        with Packages(src_feeds_index) as src_packages:
            firmware_package = next((package for package in src_packages
                                     if package[self.FEEDS_ATTR_PACKAGE] == self.FEED_FIRMWARE), None)
        if not firmware_package:
            logging.error("Missing firmware package in '{}'".format(src_feeds_index))
            raise BuilderStop

        # overwrite previous file
        mode = 'w'

        # prepare base feeds index
        feeds_base = self._config.deploy.get('feeds_base', None)
        if feeds_base:
            # append to base file if file is not empty
            if os.path.getsize(feeds_base) > 0:
                shutil.copy(feeds_base, dst_feeds_index)
                mode = 'a'

        # create destination feeds index
        with open(dst_feeds_index, mode) as dst_packages:
            if mode == 'a':
                # appending to previous index
                dst_packages.write('\n')
            for attribute, value in firmware_package.items():
                if attribute not in self.FEEDS_EXCLUDED_ATTRIBUTES:
                    dst_packages.write('{}: {}\n'.format(attribute, value))

        # sign the created index file
        usign = self._get_utility(self.LEDE_USIGN)
        self._run(usign, '-S', '-m', dst_feeds_index, '-s', local_feeds.key)

        # compress signed index file
        with open(dst_feeds_index, 'rb') as file_in, gzip.open(dst_feeds_index + '.gz', 'wb') as file_out:
            shutil.copyfileobj(file_in, file_out)

        # copy firmware packages
        firmware_ipk = firmware_package[self.FEEDS_ATTR_FILENAME]
        src_package = os.path.join(local_feeds.packages, firmware_ipk)
        dst_sysupgrade = os.path.join(target_dir, os.path.splitext(firmware_ipk)[0] + '.tar')

        shutil.copy(src_package, target_dir)
        shutil.copy(local_feeds.sysupgrade, dst_sysupgrade)

    def _get_recovery_image(self, platform: str, generic_dir: str, uboot_dir: str):
        """
        Return recovery image for SD or NAND version

        :param platform:
            Name of platform.
        :param generic_dir:
            Path to LEDE output target directory.
        :param uboot_dir:
            Relative path to output U-Boot directory.
        :return:
            Recovery image with all image files.
        """
        return ImageRecovery(
                    boot=os.path.join(generic_dir, uboot_dir, 'boot.bin'),
                    uboot=os.path.join(generic_dir, uboot_dir, 'u-boot.img'),
                    fpga=self._get_bitstream_path(),
                    kernel=os.path.join(generic_dir, 'lede-{}-recovery-squashfs-fit.itb'.format(platform)),
                    factory=os.path.join(generic_dir, 'lede-{}-nand-squashfs-factory.bin'.format(platform))
                )

    def deploy(self):
        """
        Deploy Miner firmware to target platform
        """
        platform = self._config.miner.platform
        targets = self._config.deploy.get('targets', None)

        logging.info("Start deploying Miner firmware...")

        generic_dir = os.path.join(self._working_dir, 'bin', 'targets', 'zynq')

        supported_targets = [
            'sd_config',
            'sd', 'local_sd', 'local_sd_config',
            'sd_recovery', 'local_sd_recovery', 'local_sd_recovery_config',
            'nand_config',
            'nand_recovery', 'local_nand_recovery',
            'nand_firmware1',
            'nand_firmware2',
            'local_feeds'
        ]

        nand_inno_versions = list('local_nand_inno_v{}'.format(version) for version in range(1, self.INNO_VERSIONS + 1))
        supported_targets.extend(nand_inno_versions)

        images_ssh = {}
        images_local = {}
        images_feeds = {}

        if targets:
            for target in targets:
                if target not in supported_targets:
                    logging.error("Unsupported target '{}' for firmware image".format(target))
                    raise BuilderStop

            if all(target in targets for target in ('sd', 'sd_recovery')):
                logging.error("Targets 'sd' and 'sd_recovery' are mutually exclusive")
                raise BuilderStop

            if any(target in targets for target in ('sd', 'local_sd')):
                uboot_dir = 'uboot-{}-sd'.format(platform)
                sd = ImageSd(
                    boot=os.path.join(generic_dir, uboot_dir, 'boot.bin'),
                    uboot=os.path.join(generic_dir, uboot_dir, 'u-boot.img'),
                    fpga=self._get_bitstream_path(),
                    kernel=os.path.join(generic_dir, 'lede-{}-sd-squashfs-fit.itb'.format(platform))
                )
                if 'sd' in targets:
                    images_ssh['sd'] = sd
                if 'local_sd' in targets:
                    images_local['sd'] = sd
            if any(target in targets for target in ('sd_recovery', 'local_sd_recovery')):
                uboot_dir = 'uboot-{}-sd'.format(platform)
                sd_recovery = self._get_recovery_image(platform, generic_dir, uboot_dir)
                if 'sd_recovery' in targets:
                    images_ssh['sd'] = sd_recovery
                if 'local_sd_recovery' in targets:
                    images_local['sd_recovery'] = sd_recovery
            if any(target in targets for target in ('nand_recovery', 'local_nand_recovery')):
                uboot_dir = 'uboot-{}'.format(platform)
                nand_recovery = self._get_recovery_image(platform, generic_dir, uboot_dir)
                if 'nand_recovery' in targets:
                    images_ssh['nand_recovery'] = nand_recovery
                if 'local_nand_recovery' in targets:
                    images_local['nand_recovery'] = nand_recovery
            if any(target in targets for target in ('nand_firmware1', 'nand_firmware2')):
                uboot_dir = 'uboot-{}'.format(platform)
                images_ssh['nand'] = ImageNand(
                    boot=os.path.join(generic_dir, uboot_dir, 'boot.bin'),
                    uboot=os.path.join(generic_dir, uboot_dir, 'u-boot.img'),
                    fpga=self._get_bitstream_path(),
                    factory=os.path.join(generic_dir, 'lede-{}-nand-squashfs-factory.bin'.format(platform)),
                    sysupgrade=os.path.join(generic_dir, 'lede-{}-nand-squashfs-sysupgrade.tar'.format(platform))
                )
            if any(target in targets for target in nand_inno_versions):
                uboot_dir = 'uboot-{}'.format(platform)
                nand_inno = ImageInno(
                    boot=os.path.join(generic_dir, uboot_dir, 'boot.bin'),
                    uboot=os.path.join(generic_dir, uboot_dir, 'u-boot.img'),
                    fpga=self._get_bitstream_path(),
                    kernel=os.path.join(generic_dir, 'lede-{}-inno-squashfs-fit.itb'.format(platform)),
                    kernel_recovery=os.path.join(generic_dir, 'lede-{}-recovery-squashfs-fit.itb'.format(platform)),
                    factory=os.path.join(generic_dir, 'lede-{}-nand-squashfs-factory.bin'.format(platform))
                )
                for target in (target for target in nand_inno_versions if target in targets):
                    images_local['nand_inno_v{}'.format(target.split('_v')[1])] = nand_inno
            if 'local_feeds' in targets:
                feeds = ImageFeeds(
                    key=os.path.join(self._working_dir, self.BUILD_KEY_NAME),
                    packages=os.path.join(self._working_dir, 'staging_dir', 'packages', platform.split('-')[0]),
                    sysupgrade=os.path.join(generic_dir, 'lede-{}-nand-squashfs-sysupgrade.tar'.format(platform))
                )
                images_feeds['local'] = feeds

        sd_config = 'sd_config' in targets
        nand_config = 'nand_config' in targets

        sd_config_local = 'local_sd_config' in targets
        sd_recovery_config = 'local_sd_recovery_config' in targets

        if images_ssh or sd_config or nand_config:
            self._deploy_ssh(images_ssh, sd_config, nand_config)
        if images_local or sd_config_local or sd_recovery_config:
            self._deploy_local(images_local, sd_config_local, sd_recovery_config)
        if images_feeds:
            self._deploy_feeds(images_feeds)

    def status(self):
        """
        Show status of all repositories

        It is equivalent of `git status` and shows all changes in related projects.
        """
        def get_diff_path(diff):
            if diff.change_type[0] == 'R':
                return '{} -> {}'.format(diff.a_path, diff.b_path)
            else:
                return diff.a_path

        for name, repo in self._repos.items():
            working_dir = os.path.relpath(repo.working_dir, os.getcwd())
            logging.info("Status for '{}': '{}' ({})".format(name, working_dir, repo.active_branch.name))
            clean = True
            indexed_files = repo.head.commit.diff()
            if len(indexed_files):
                print('Changes to be committed:')
                for indexed_file in indexed_files:
                    change_type = indexed_file.change_type[0]
                    print('\t{}'.format(change_type), colored(get_diff_path(indexed_file), 'green'))
                print()
                clean = False
            staged_files = repo.index.diff(None)
            if len(staged_files):
                print('Changes not staged for commit:')
                for staged_file in staged_files:
                    change_type = staged_file.change_type[0]
                    print('\t{}'.format(change_type), colored(get_diff_path(staged_file), 'red'))
                print()
                clean = False
            if len(repo.untracked_files):
                print('Untracked files:')
                for untracked_file in repo.untracked_files:
                    print(colored('\t{}'.format(untracked_file), 'red'))
                print()
                clean = False
            if clean:
                print('nothing to commit, working tree clean')
                print()

    def debug(self):
        """
        Remotely run program on target platform and attach debugger to it
        """
        pass

    def toolchain(self):
        """
        Prepare environment for LEDE toolchain

        The bash script is returned to the stdout which can be then evaluated in parent process to correctly set build
        environment for LEDE toolchain. It is then possible to use gcc and other tools from this SDK in external
        projects.
        """
        logging.info("Preparing toolchain environment...'")

        if self._use_glibc():
            target_name = 'target-arm_cortex-a9+neon_glibc-2.24_eabi'
            toolchain_name = 'toolchain-arm_cortex-a9+neon_gcc-5.4.0_glibc-2.24_eabi'
        else:
            target_name = 'target-arm_cortex-a9+neon_musl-1.1.16_eabi'
            toolchain_name = 'toolchain-arm_cortex-a9+neon_gcc-5.4.0_musl-1.1.16_eabi'

        staging_dir = os.path.join(self._working_dir, 'staging_dir')
        target_dir = os.path.join(staging_dir, target_name)
        toolchain_dir = os.path.join(staging_dir, toolchain_name)

        if not os.path.exists(target_dir):
            msg = "Target directory '{}' does not exist".format(target_dir)
            logging.error(msg)
            sys.stdout.write('echo {};\n'.format(msg))
            raise BuilderStop

        if not os.path.exists(toolchain_dir):
            msg = "Toolchain directory '{}' does not exist".format(toolchain_dir)
            logging.error(msg)
            sys.stdout.write('echo {};\n'.format(msg))
            raise BuilderStop

        env_path = os.environ.get('PATH', '')

        sys.stderr.write('# set environment with command:\n')
        sys.stderr.write('# eval $(./lede.py {} 2>/dev/null)\n'.format(' '.join(self._argv)))
        sys.stdout.write('TARGET="{}";\n'.format(target_dir))
        sys.stdout.write('TOOLCHAIN="{}";\n'.format(toolchain_dir))
        sys.stdout.write('export STAGING_DIR="${TARGET}";\n')

        if (toolchain_dir + '/bin') not in env_path:
            # export PATH only if it has not been exported already
            sys.stdout.write('export PATH="${TOOLCHAIN}/bin:$PATH";\n')
