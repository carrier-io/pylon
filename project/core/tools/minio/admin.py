#!/usr/bin/python
# coding=utf-8

#   Copyright 2020 getcarrier.io
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

""" MinIO admin API """

import os
import ctypes
import base64
import json
import binascii
import requests  # pylint: disable=E0401
import minio  # pylint: disable=E0401


class MinIOAdminCrypt:
    """ MinIO admin encryption helper """

    def __init__(self, secret_key):
        self.key = secret_key
        self.lib = ctypes.cdll.LoadLibrary(
            os.path.join(os.path.dirname(__file__), "minio_madmin.so")
        )
        self.lib.decrypt.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
        self.lib.decrypt.restype = ctypes.c_char_p
        self.lib.encrypt.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
        self.lib.encrypt.restype = ctypes.c_char_p

    def encrypt(self, data):
        """ Encrypt data  """
        return binascii.unhexlify(self.lib.encrypt(self.key.encode(), binascii.hexlify(data)))

    def decrypt(self, data):
        """ Decrypt data """
        return binascii.unhexlify(self.lib.decrypt(self.key.encode(), binascii.hexlify(data)))


class MinIOAdminAuth(requests.auth.AuthBase):  # pylint: disable=R0903
    """ Set correct headers for MinIO """

    def __init__(self, access_key, secret_key):
        self.credentials = minio.credentials.static.Static(access_key, secret_key)
        self.credentials.get = self.credentials.retrieve

    def __call__(self, request):
        headers = minio.signer.sign_v4(
            request.method, request.url.replace("https://", "http://"),
            "", dict(),
            self.credentials,
            minio.helpers.get_sha256_hexdigest(request.body)
        )
        headers["Accept-Encoding"] = "gzip"
        headers["User-Agent"] = "MinIO (linux; amd64) python-minio-madmin/v1"
        request.headers = headers
        return request


class MinIOAdmin:
    """ MinIO admin API helper """

    def __init__(  # pylint: disable=R0913
            self, endpoint, access_key, secret_key,
            admin_api_prefix="/minio/admin/v2",
            verify=True, cert=None
    ):
        self.endpoint = endpoint + admin_api_prefix
        self.access_key = access_key
        self.secret_key = secret_key
        self.auth = MinIOAdminAuth(access_key, secret_key)
        self.crypt = MinIOAdminCrypt(secret_key)
        self.verify = verify
        self.cert = cert

    #
    # user-commands
    #

    def list_users(self):
        """ ListUsers """
        response = requests.get(
            self.endpoint + "/list-users",
            auth=self.auth, verify=self.verify, cert=self.cert
        )
        return json.loads(self.crypt.decrypt(response.content))

    def set_user(self, access_key, secret_key, status):
        """ SetUser """
        user_info = {
            "secretKey": secret_key,
            "status": status
        }
        requests.put(
            self.endpoint + "/add-user",
            params={"accessKey": access_key},
            data=self.crypt.encrypt(json.dumps(user_info).encode()),
            auth=self.auth, verify=self.verify, cert=self.cert
        )

    def add_user(self, access_key, secret_key):
        """ AddUser """
        self.set_user(access_key, secret_key, "enabled")

    def remove_user(self, access_key):
        """ RemoveUser """
        requests.delete(
            self.endpoint + "/remove-user",
            params={"accessKey": access_key},
            auth=self.auth, verify=self.verify, cert=self.cert
        )

    def set_user_status(self, access_key, status):
        """ SetUserStatus """
        requests.put(
            self.endpoint + "/set-user-status",
            params={"accessKey": access_key, "status": status},
            auth=self.auth, verify=self.verify, cert=self.cert
        )

    def get_user_info(self, access_key):
        """ GetUserInfo """
        response = requests.get(
            self.endpoint + "/user-info",
            params={"accessKey": access_key},
            auth=self.auth, verify=self.verify, cert=self.cert
        )
        return response.json()

    #
    # group-commands
    #

    def update_group_members(self, group, members=None, remove=False):
        """ UpdateGroupMembers """
        requests.put(
            self.endpoint + "/update-group-members",
            data=json.dumps({
                "group": group,
                "members": members if members is not None else list(),
                "isRemove": remove
            }),
            auth=self.auth, verify=self.verify, cert=self.cert
        )

    def get_group_description(self, group):
        """ GetGroupDescription """
        response = requests.get(
            self.endpoint + "/group",
            params={"group": group},
            auth=self.auth, verify=self.verify, cert=self.cert
        )
        return response.json()

    def list_groups(self):
        """ ListGroups """
        response = requests.get(
            self.endpoint + "/groups",
            auth=self.auth, verify=self.verify, cert=self.cert
        )
        return response.json()

    def set_group_status(self, group, status):
        """ SetGroupStatus """
        requests.put(
            self.endpoint + "/set-group-status",
            params={"group": group, "status": status},
            auth=self.auth, verify=self.verify, cert=self.cert
        )

    #
    # policy-commands
    #

    def info_canned_policy(self, name):
        """ InfoCannedPolicy """
        response = requests.get(
            self.endpoint + "/info-canned-policy",
            params={"name": name},
            auth=self.auth, verify=self.verify, cert=self.cert
        )
        return response.json()

    def list_canned_policies(self):
        """ ListCannedPolicies """
        response = requests.get(
            self.endpoint + "/list-canned-policies",
            auth=self.auth, verify=self.verify, cert=self.cert
        )
        return {key:json.loads(base64.b64decode(value)) for key, value in response.json().items()}

    def remove_canned_policy(self, name):
        """ RemoveCannedPolicy """
        requests.delete(
            self.endpoint + "/remove-canned-policy",
            params={"name": name},
            auth=self.auth, verify=self.verify, cert=self.cert
        )

    def add_canned_policy(self, name, policy):
        """ AddCannedPolicy """
        requests.put(
            self.endpoint + "/add-canned-policy",
            params={"name": name},
            data=json.dumps(policy),
            auth=self.auth, verify=self.verify, cert=self.cert
        )

    def set_policy(self, name, entity, group=False):
        """ SetPolicy """
        requests.put(
            self.endpoint + "/set-user-or-group-policy",
            params={
                "policyName": name,
                "userOrGroup": entity,
                "isGroup": "true" if group else "false"
            },
            auth=self.auth, verify=self.verify, cert=self.cert
        )

    #
    # config-commands
    #

    def get_config(self):
        """ GetConfig """
        response = requests.get(
            self.endpoint + "/config",
            auth=self.auth, verify=self.verify, cert=self.cert
        )
        return self.crypt.decrypt(response.content).decode()

    def set_config(self, config):
        """ SetConfig """
        requests.put(
            self.endpoint + "/config",
            data=self.crypt.encrypt(config.encode()),
            auth=self.auth, verify=self.verify, cert=self.cert
        )
