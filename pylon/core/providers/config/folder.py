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

""" ConfigProvider """

import os

# from pylon.core.tools import log

from . import ConfigProviderModel


class Provider(ConfigProviderModel):
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

    def config_data_exists(self, plugin_name):
        """ Check if custom plugin config exists """
        return os.path.exists(os.path.join(self.path, f"{plugin_name}.yml"))

    def get_config_data(self, plugin_name):
        """ Get custom plugin config """
        if not self.config_data_exists(plugin_name):
            return b""
        with open(os.path.join(self.path, f"{plugin_name}.yml"), "rb") as file:
            data = file.read()
        return data

    def add_config_data(self, plugin_name, config):
        """ Add custom plugin config """
        with open(os.path.join(self.path, f"{plugin_name}.yml"), "wb") as file:
            file.write(config)

    def delete_config_data(self, plugin_name):
        """ Delete custom plugin config """
        if self.config_data_exists(plugin_name):
            os.remove(os.path.join(self.path, f"{plugin_name}.yml"))
