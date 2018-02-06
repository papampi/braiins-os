import paramiko
import logging

from contextlib import contextmanager
from subprocess import CalledProcessError


class SSHClient(paramiko.SSHClient):
    """
    Class for support authentication without password and key
    """
    def _auth(self, username, password, pkey, key_filenames, allow_agent,
              look_for_keys, gss_auth, gss_kex, gss_deleg_creds, gss_host):
        if password is None and not look_for_keys:
            self._transport.auth_none(username)
        else:
            super()._auth(username, password, pkey, key_filenames, allow_agent,
                          look_for_keys, gss_auth, gss_kex, gss_deleg_creds, gss_host)


class SSHManager:
    """
    SSH Manager simplifies file operations and command running
    """
    def __init__(self, hostname: str, username: str, password: str):
        """
        Initialize SSH client with server name and information for authentication

        :param hostname:
            The server to connect to.
        :param username:
            The username to authenticate as.
        :param password:
            A password to use for authentication.
        """
        self._client = SSHClient()
        self._hostname = hostname
        self._username = username
        self._password = password

        logging.debug("Loading system host keys...'")
        self._client.load_system_host_keys()
        self._client.set_missing_host_key_policy(paramiko.WarningPolicy())

    def __enter__(self):
        """
        Connect to an SSH server and authenticate to it

        :return:
            SSH manager connected to the server.
        """
        logging.debug("Connecting to remote SSH server...'")
        self._client.connect(hostname=self._hostname, username=self._username, password=self._password,
                             look_for_keys=False)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Close connection with SSH server
        """
        self._client.close()

    @staticmethod
    def _check_exit_status(cmd, stdout, stderr):
        """
        Check exit status of previous command

        :param cmd:
            Comand which has been run remotely.
        :param stdout:
            Standard output from SSH client.
        :param stderr:
            Standard error from SSH client.
        """
        returncode = stdout.channel.recv_exit_status()
        if returncode != 0:
            raise CalledProcessError(returncode, cmd, stdout, stderr)

    @contextmanager
    def open(self, file: str, mode='r'):
        """
        Open file and return a corresponding file object

        :param file:
            Pathname of the file to be opened.
        :param mode:
            An optional string that specifies the mode in which the file is opened.
        :return:
            File object.
        """
        direction = {
            'r': '<',
            'w': '>',
            'a': '>>'
        }.get(mode, None)
        if direction is None:
            raise ValueError("Unsupported mode '{}'".format(mode))

        cmd = 'cat {}{}'.format(direction, file)

        logging.debug("Remotely opening file '{}' with mode '{}'".format(file, mode))
        stdin, stdout, stderr = self._client.exec_command(cmd)
        if mode == 'r':
            yield stdout
        else:
            yield stdin
            stdin.channel.shutdown_write()

        self._check_exit_status(cmd, stdout, stderr)

    def run(self, *args):
        """
        Run system command on remote system
        """
        if type(args[0]) is list:
            args = args[0]

        cmd = ' '.join(args)

        logging.debug("Remotely running command '{}'...".format(cmd))
        _, stdout, stderr = self._client.exec_command(cmd)

        self._check_exit_status(cmd, stdout, stderr)

    def open_sftp(self):
        """
        Open an SFTP session on the SSH server

        :return:
            A new `.SFTPClient` session object.
        """
        return self._client.open_sftp()
