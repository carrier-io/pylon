#!/usr/bin/python
# coding=utf-8
# pylint: disable=I0011

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

"""
    MinIO helper
"""

import minio  # pylint: disable=E0401
import urllib3  # pylint: disable=E0401

from .admin import MinIOAdmin


class MinIOHelper:  # pylint: disable=R0903
    """ MinIO helper """

    @staticmethod
    def get_client(config):
        """ Get configured MinIO client """
        http_client = None
        if not config.get("verify", False):
            http_client = urllib3.PoolManager(
                timeout=urllib3.Timeout.DEFAULT_TIMEOUT,
                cert_reqs="CERT_NONE",
                maxsize=10,
                retries=urllib3.Retry(
                    total=5,
                    backoff_factor=0.2,
                    status_forcelist=[500, 502, 503, 504]
                )
            )
        if isinstance(config.get("verify", False), str):
            http_client = urllib3.PoolManager(
                timeout=urllib3.Timeout.DEFAULT_TIMEOUT,
                cert_reqs="CERT_REQUIRED",
                ca_certs=config["verify"],
                maxsize=10,
                retries=urllib3.Retry(
                    total=5,
                    backoff_factor=0.2,
                    status_forcelist=[500, 502, 503, 504]
                )
            )
        client = minio.Minio(
            endpoint=config["endpoint"],
            access_key=config.get("access_key", None),
            secret_key=config.get("secret_key", None),
            secure=config.get("secure", True),
            region=config.get("region", None),
            http_client=http_client
        )
        return client

    @staticmethod
    def get_admin_client(config):
        """ Get configured MinIOAdmin client """
        if config["secure"]:
            endpoint = f"https://{config['endpoint']}"
        else:
            endpoint = f"http://{config['endpoint']}"
        return MinIOAdmin(
            endpoint=endpoint,
            access_key=config["access_key"],
            secret_key=config["secret_key"],
            verify=config["verify"]
        )
