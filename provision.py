#!/usr/bin/python
# coding=utf-8

#   Copyright 2021 getcarrier.io
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

""" Provision local instance """

import io
import os
import zipfile

import dotenv  # pylint: disable=E0401
import minio  # pylint: disable=E0401


def main():  # pylint: disable=R0914
    """ Entry point """
    dotenv.load_dotenv()
    #
    storage = minio.Minio(
        endpoint="localhost",
        access_key=os.getenv("MINIO_ACCESS_KEY"),
        secret_key=os.getenv("MINIO_SECRET_KEY"),
        secure=False,
    )
    #
    buckets = [bucket.name for bucket in storage.list_buckets()]
    needed_buckets = ["module", "config"]
    for needed_bucket in needed_buckets:
        if needed_bucket not in buckets:
            print(f"Making bucket: {needed_bucket}")
            storage.make_bucket(needed_bucket)
    #
    plugin_root = os.path.abspath(os.path.join(os.getcwd(), "..", "pylon-demo"))
    #
    plugin_names = list()
    for item in os.listdir(plugin_root):
        if item.startswith("."):
            continue
        item_path = os.path.join(plugin_root, item)
        if os.path.isdir(item_path):
            plugin_names.append(item)
    #
    for plugin_name in plugin_names:
        plugin_directory = os.path.join(plugin_root, plugin_name)
        #
        result = io.BytesIO()
        with zipfile.ZipFile(result, mode="w", compression=zipfile.ZIP_DEFLATED) as zfile:
            os.chdir(plugin_directory)
            for root, _, files in os.walk("."):
                for name in files:
                    path = os.path.join(root, name)
                    zfile.write(path)
        result.seek(0)
        result_size = len(result.read())
        result.seek(0)
        #
        print(f"Uploading module: {plugin_name}")
        storage.put_object("module", f"{plugin_name}.zip", result, result_size)


if __name__ == "__main__":
    main()
