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
    Storage tools
"""

from core.tools.minio import MinIOHelper


def list_modules(settings):
    """ List modules in storage """
    modules = list()
    minio = MinIOHelper.get_client(settings["storage"])
    for obj in minio.list_objects(settings["storage"]["buckets"]["module"]):
        obj_name = obj.object_name
        if obj_name.endswith(".zip"):
            modules.append(obj_name[:-4])
    return modules


def get_module(settings, name):
    """ Get module from storage """
    minio = MinIOHelper.get_client(settings["storage"])
    try:
        return minio.get_object(settings["storage"]["buckets"]["module"], f"{name}.zip").read()
    except:  # pylint: disable=W0702
        return None


def get_config(settings, name):
    """ Get config from storage """
    minio = MinIOHelper.get_client(settings["storage"])
    try:
        return minio.get_object(settings["storage"]["buckets"]["config"], f"{name}.yml").read()
    except:  # pylint: disable=W0702
        return None
