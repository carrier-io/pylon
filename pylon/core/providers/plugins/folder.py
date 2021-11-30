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

""" PluginsProvider """

import os
import json
import shutil

# from pylon.core.tools import log
from pylon.core.tools.module import LocalModuleLoader

from . import PluginsProviderModel


class Provider(PluginsProviderModel):
    """ Provider """

    def __init__(self, context, settings):
        self.context = context
        self.settings = settings
        #
        self.path = self.settings["path"]

    def init(self):
        """ Initialize provider """
        os.makedirs(self.path, exist_ok=True)

    def deinit(self):
        """ De-initialize provider """

    def plugin_exists(self, name):
        """ Check if plugin exists """
        return os.path.exists(os.path.join(self.path, name))

    def add_plugin(self, name, path):
        """ Add new plugin from path """
        if self.plugin_exists(name):
            self.delete_plugin(name)
        shutil.copytree(path, os.path.join(self.path, name))

    def delete_plugin(self, name):
        """ Delete existing plugin """
        shutil.rmtree(os.path.join(self.path, name))

    def list_plugins(self, exclude=None):
        """ Get existing plugin names """
        plugins = os.listdir(self.path)
        #
        if exclude is None:
            exclude = list()
        #
        for item in exclude:
            if item in plugins:
                plugins.remove(item)
        #
        plugins.sort()
        #
        return plugins

    def get_plugin_loader(self, name):
        """ Get loader for plugin """
        if not self.plugin_exists(name):
            return None
        return LocalModuleLoader(f"plugins.{name}", os.path.join(self.path, name))

    def get_plugin_metadata(self, name):
        """ Get metadata for plugin """
        if not self.plugin_exists(name):
            return None
        try:
            with open(os.path.join(self.path, name, "metadata.json"), "rb") as file:
                metadata = json.load(file)
            return metadata
        except:  # pylint: disable=W0702
            return dict()
