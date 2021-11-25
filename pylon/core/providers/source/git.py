#!/usr/bin/python3
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

""" SourceProvider """

import os
import tempfile

from pylon.core.tools import git

from . import SourceProviderModel


class Provider(SourceProviderModel):  # pylint: disable=R0902
    """ Provider model """

    def __init__(self, context, settings):
        self.context = context
        self.settings = settings
        #
        self.source_url_template = self.settings["source_url_template"]
        #
        self.branch = self.settings.get("branch", "main")
        self.depth = self.settings.get("depth", 1)
        self.delete_git_dir = self.settings.get("delete_git_dir", True)
        self.username = self.settings.get("username", None)
        self.password = self.settings.get("password", None)
        self.key_filename = self.settings.get("key_filename", None)
        self.key_data = self.settings.get("key_data", None)


    def init(self):
        """ Initialize provider """

    def deinit(self):
        """ De-initialize provider """

    def get_source(self, target):
        """ Get plugin source """
        target_url = self.source_url_template.format(name=target["name"])
        #
        target_path = os.path.join(tempfile.mkdtemp(), target["name"])
        os.makedirs(target_path, exist_ok=True)
        self.context.module_manager.temporary_objects.append(target_path)
        #
        git.clone(
            target_url, target_path, self.branch, self.depth, self.delete_git_dir,
            self.username, self.password, self.key_filename, self.key_data,
        )
        #
        return target_path

    def get_multiple_source(self, targets):
        """ Get plugins source """
        result = list()
        #
        for target in targets:
            result.append(self.get_source(target))
        #
        return result
