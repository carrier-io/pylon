"""
    Clone git repository
"""
import getpass
import os
import io
import shutil
from typing import Optional

from dulwich import refs, repo, porcelain, client
from dulwich.contrib.paramiko_vendor import ParamikoSSHVendor

import paramiko.transport
from paramiko import SSHException, Message

from pylon.core.tools import log


class DebugLogStream(io.RawIOBase):
    """ IO stream that writes to log.debug """

    def read(self, size=-1):  # pylint: disable=W0613
        return

    def readall(self):
        return

    def readinto(self, b):  # pylint: disable=W0613
        return

    def write(self, b):
        for line in b.decode().splitlines():
            log.debug(line)


class GitManager:
    """ Action: clone git repository """

    def __init__(self, config):
        # Patch dulwich to work without valid UID/GID
        repo.__original__get_default_identity = repo._get_default_identity  # pylint: disable=W0212
        repo._get_default_identity = self._patched_repo_get_default_identity  # pylint: disable=W0212
        # Patch dulwich to use paramiko SSH client
        client.get_ssh_vendor = ParamikoSSHVendor
        # Patch paramiko to skip key verification
        paramiko.transport.Transport._verify_key = self._paramiko_transport_verify_key  # pylint: disable=W0212
        # Set USERNAME if needed
        try:
            getpass.getuser()
        except:  # pylint: disable=W0702
            os.environ["USERNAME"] = "git"

        self.config = config

    @staticmethod
    def _patched_repo_get_default_identity():
        try:
            return repo.__original__get_default_identity()  # pylint: disable=W0212
        except:  # pylint: disable=W0702
            return ("Carrier User", "dusty@localhost")

    @staticmethod
    def _paramiko_transport_verify_key(self, host_key, sig):  # pylint: disable=W0613
        key = self._key_info[self.host_key_type](Message(host_key))  # pylint: disable=W0212
        if key is None:
            raise SSHException('Unknown host key type')
        self.host_key = key

    @staticmethod
    def _paramiko_client_SSHClient_auth(original_auth, forced_pkey):  # pylint: disable=C0103
        from functools import partial
        return partial(original_auth, pkey=forced_pkey)
        # def __paramiko_client_SSHClient_auth(  # pylint: disable=C0103,R0913
        #         self, username, password, pkey, key_filenames, allow_agent, look_for_keys,  # pylint: disable=W0613
        #         gss_auth, gss_kex, gss_deleg_creds, gss_host, passphrase
        #     ):
        #     return original_auth(
        #         self, username, password, forced_pkey, key_filenames, allow_agent, look_for_keys,
        #         gss_auth, gss_kex, gss_deleg_creds, gss_host, passphrase
        #     )
        # return __paramiko_client_SSHClient_auth

    def get_auth_args(self) -> dict:
        auth_args = dict()
        if self.config.get('username'):
            auth_args['username'] = self.config.get('username')
        if self.config.get("password"):
            auth_args['password'] = self.config.get('password')
        if self.config.get('key', None) is not None:
            auth_args["key_filename"] = self.config.get("key")
        if self.config.get("key_data"):
            key_obj = io.StringIO(self.config.get("key_data").replace("|", "\n"))
            pkey = paramiko.RSAKey.from_private_key(key_obj)
            # Patch paramiko to use our key
            # todo: thread-safe patching
            paramiko.client.SSHClient._auth = self._paramiko_client_SSHClient_auth(  # pylint: disable=W0212
                paramiko.client.SSHClient._auth, pkey  # pylint: disable=W0212
            )
        return auth_args

    def clone(
            self, source: str, target: str,
            branch: str = 'master', depth: Optional[int] = None, delete_git_dir: bool = False,
            auth_args_override: Optional[dict] = None
    ):
        auth_args = self.get_auth_args()
        if auth_args_override:
            auth_args.update(auth_args_override)
        # Clone repository
        log.info("Cloning repository %s into %s", source, target)
        repository = porcelain.clone(
            source, target, checkout=False, depth=depth,
            errstream=DebugLogStream(),
            **auth_args
        )

        # Get current HEAD tree (default branch)
        try:
            head_tree = repository[b"HEAD"]
        except:  # pylint: disable=W0702
            head_tree = None
        # Get target tree (requested branch)
        branch_b = branch.encode("utf-8")
        try:
            target_tree = repository[b"refs/remotes/origin/" + branch_b]
        except:  # pylint: disable=W0702
            target_tree = None
        # Checkout branch
        if target_tree is not None:
            log.info("Checking out branch %s", branch)
            repository[b"refs/heads/" + branch_b] = repository[b"refs/remotes/origin/" + branch_b]
            repository.refs.set_symbolic_ref(b"HEAD", b"refs/heads/" + branch_b)
            repository.reset_index(repository[b"HEAD"].tree)
        elif head_tree is not None:
            try:
                default_branch_name = repository.refs.follow(b"HEAD")[0][1]
                if default_branch_name.startswith(refs.LOCAL_BRANCH_PREFIX):
                    default_branch_name = default_branch_name[len(refs.LOCAL_BRANCH_PREFIX):]
                default_branch_name = default_branch_name.decode("utf-8")
                log.warning(
                    "Branch %s was not found. Checking out default branch %s",
                    branch, default_branch_name
                )
            except:  # pylint: disable=W0702
                log.warning("Branch %s was not found. Trying to check out default branch", branch)
            try:
                repository.reset_index(repository[b"HEAD"].tree)
            except:  # pylint: disable=W0702
                log.exception("Failed to checkout default branch")
        else:
            log.error("Branch %s was not found and default branch is not set. Skipping checkout")

        # Delete .git if requested
        if delete_git_dir:
            log.info("Deleting .git directory")
            shutil.rmtree(os.path.join(target, ".git"))



if __name__ == '__main__':
    config = {
        'source': 'https://github.com/carrier-io/theme.git',
        'target': './tmp/',
        # 'delete_git_dir': True
        'branch': 'main'
    }
    # config = BigDict()
    # Cloner.fill_config(config)
    # print(config)
    c = GitManager(config)
    shutil.rmtree(config['target'])
    c.clone(**config)
    # from dulwich.repo import Repo
    # from dulwich.client import TCPGitClient
    # client = TCPGitClient(server_address, server_port)
    # local = Repo.init("local", mkdir=True)
    # remote_refs = client.fetch(b"/", local)
